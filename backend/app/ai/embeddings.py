"""Sentence-transformer embedding and cross-encoder reranking models (CPU)."""

from __future__ import annotations

import logging
import math
import threading

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingModel:
    def __init__(self, model_name: str, query_prefix: str = "") -> None:
        self.model_name = model_name
        self.query_prefix = query_prefix
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading embedding model %s", self.model_name)
                self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    @property
    def dim(self) -> int:
        return self._load().get_sentence_embedding_dimension()

    def embed_documents(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        vecs = self._load().encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype="float32")

    def embed_query(self, text: str) -> np.ndarray:
        vec = self._load().encode([self.query_prefix + text], normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vec, dtype="float32")


class Reranker:
    """Cross-encoder that scores (query, passage) pairs; scores are mapped to [0, 1] with a sigmoid."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import CrossEncoder

                logger.info("Loading reranker %s", self.model_name)
                self._model = CrossEncoder(self.model_name, device="cpu")
        return self._model

    def warmup(self) -> None:
        self._load()

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        logits = self._load().predict([(query, p) for p in passages], show_progress_bar=False)
        return [1.0 / (1.0 + math.exp(-float(x))) for x in np.atleast_1d(logits)]
