"""Knowledge ingestion: documents -> text extraction -> chunking -> embeddings -> FAISS index."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.ai.embeddings import EmbeddingModel
from app.core.config import Settings
from app.rag.chunker import chunk_document, embedding_text
from app.rag.loaders import SUPPORTED_SUFFIXES, load_document
from app.rag.vector_store import FaissVectorStore

logger = logging.getLogger(__name__)


def discover_documents(knowledge_dir: Path) -> list[Path]:
    return sorted(
        p for p in knowledge_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES and not p.name.startswith(("_", "."))
        and p.name.lower() != "readme.md"
    )


def build_index(settings: Settings, embedder: EmbeddingModel | None = None) -> FaissVectorStore:
    embedder = embedder or EmbeddingModel(settings.embedding_model, settings.embedding_query_prefix)
    paths = discover_documents(settings.knowledge_dir)
    if not paths:
        raise RuntimeError(f"No knowledge documents found in {settings.knowledge_dir}")

    all_chunks, doc_entries = [], []
    for path in paths:
        doc = load_document(path)
        chunks = chunk_document(doc, settings.rag_chunk_max_chars, settings.rag_chunk_overlap_chars)
        all_chunks.extend(chunks)
        doc_entries.append({
            "file": str(path.relative_to(settings.knowledge_dir)).replace("\\", "/"),
            "title": doc.title,
            "category": doc.metadata.get("category"),
            "source_basis": doc.metadata.get("source_basis"),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "chunks": len(chunks),
        })
        logger.info("Loaded %s: %d sections -> %d chunks", path.name, len(doc.sections), len(chunks))

    embeddings = embedder.embed_documents([embedding_text(c) for c in all_chunks])
    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "embedding_model": settings.embedding_model,
        "dimension": int(embeddings.shape[1]),
        "chunk_max_chars": settings.rag_chunk_max_chars,
        "n_documents": len(doc_entries),
        "n_chunks": len(all_chunks),
        "documents": doc_entries,
    }
    store = FaissVectorStore.build(embeddings, all_chunks, manifest)
    store.save(settings.index_dir)
    logger.info("Index built: %d documents, %d chunks -> %s", len(doc_entries), len(all_chunks), settings.index_dir)
    return store
