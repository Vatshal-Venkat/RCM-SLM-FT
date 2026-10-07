"""Hybrid retrieval: dense (FAISS) + lexical (BM25), fused with reciprocal rank fusion,
then reranked by a cross-encoder."""

from __future__ import annotations

import logging
import re
import threading
from functools import lru_cache

from app.ai.embeddings import EmbeddingModel, Reranker
from app.core.config import Settings, get_settings
from app.rag.base import RetrievedChunk
from app.rag.chunker import embedding_text
from app.rag.lexical import BM25Index
from app.rag.vector_store import FaissVectorStore

logger = logging.getLogger(__name__)

RRF_K = 60

# Every document in the corpus is about RCM, so "... in revenue cycle management" carries no
# discriminating signal and pulls generic overview chunks above the specific answer.
_DOMAIN_CONTEXT_RE = re.compile(
    r"\b(?:in|within|for|of|under)\s+(?:the\s+)?(?:context\s+of\s+)?(?:us\s+)?(?:healthcare\s+)?"
    r"(?:revenue\s+cycle\s+management|revenue\s+cycle|rcm|medical\s+billing|healthcare\s+billing|healthcare)\b",
    re.IGNORECASE,
)


def normalize_query(query: str) -> str:
    stripped = _DOMAIN_CONTEXT_RE.sub(" ", query)
    stripped = re.sub(r"\s+", " ", stripped).strip(" ?.!,")
    return stripped if len(stripped) >= 3 else query


class HybridRetriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.embedder = EmbeddingModel(settings.embedding_model, settings.embedding_query_prefix)
        self.reranker = Reranker(settings.reranker_model) if settings.rerank_enabled else None
        self.store: FaissVectorStore | None = None
        self.bm25: BM25Index | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle
    def load(self) -> bool:
        """Load the persisted index and models. Returns False if no index has been built."""
        with self._lock:
            if self.store is not None:
                return True
            if not FaissVectorStore.exists(self.settings.index_dir):
                logger.warning("No RAG index at %s; run scripts/ingest_knowledge.py", self.settings.index_dir)
                return False
            store = FaissVectorStore.load(self.settings.index_dir)
            if store.manifest.get("embedding_model") != self.settings.embedding_model:
                logger.error("Index was built with %s but EMBEDDING_MODEL is %s; rebuild the index",
                             store.manifest.get("embedding_model"), self.settings.embedding_model)
                return False
            self.embedder.embed_query("warmup")
            if self.reranker:
                self.reranker.warmup()
            self.bm25 = BM25Index([embedding_text(c) for c in store.chunks])
            self.store = store
            logger.info("RAG index loaded: %d chunks from %d documents",
                        store.manifest["n_chunks"], store.manifest["n_documents"])
            return True

    def reload(self) -> bool:
        with self._lock:
            self.store, self.bm25 = None, None
        return self.load()

    def is_ready(self) -> bool:
        return self.store is not None

    @property
    def manifest(self) -> dict:
        return self.store.manifest if self.store else {}

    # ------------------------------------------------------------------ retrieval
    def retrieve(self, query: str, k: int | None = None) -> list[RetrievedChunk]:
        if self.store is None or self.bm25 is None:
            return []
        k = k or self.settings.rag_top_k
        n_cand = max(self.settings.rag_candidates, k)
        query = normalize_query(query)

        dense = self.store.search(self.embedder.embed_query(query), n_cand)
        dense_score = dict(dense)
        lex_all = self.bm25.scores(query)
        lex_ranked = sorted(range(len(lex_all)), key=lambda i: lex_all[i], reverse=True)[:n_cand]
        lex_ranked = [i for i in lex_ranked if lex_all[i] > 0]
        lex_max = max((lex_all[i] for i in lex_ranked), default=0.0) or 1.0

        # Reciprocal rank fusion: robust to the very different score scales of BM25 and cosine.
        fused: dict[int, float] = {}
        for rank, (i, _) in enumerate(dense):
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, i in enumerate(lex_ranked):
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
        candidates = sorted(fused, key=fused.get, reverse=True)[:n_cand]

        results = [
            RetrievedChunk(
                chunk=self.store.chunks[i],
                score=0.0,
                dense_score=dense_score.get(i, 0.0),
                lexical_score=lex_all[i] / lex_max,
            )
            for i in candidates
        ]
        if self.reranker:
            rr = self.reranker.score(query, [embedding_text(r.chunk) for r in results])
            for r, s in zip(results, rr):
                r.score = s
        else:
            for r in results:
                r.score = 0.7 * r.dense_score + 0.3 * r.lexical_score
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]


@lru_cache
def get_retriever() -> HybridRetriever:
    return HybridRetriever(get_settings())
