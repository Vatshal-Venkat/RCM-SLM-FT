"""FAISS vector store persisted to disk alongside chunk records and a manifest."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from app.rag.base import Chunk

INDEX_FILE = "faiss.index"
CHUNKS_FILE = "chunks.jsonl"
MANIFEST_FILE = "manifest.json"


class FaissVectorStore:
    """Exact inner-product search over L2-normalised embeddings (= cosine similarity).

    A flat index is the right choice for a knowledge base of thousands of chunks: exact results,
    no training, sub-millisecond search.
    """

    def __init__(self, index, chunks: list[Chunk], manifest: dict) -> None:
        self.index = index
        self.chunks = chunks
        self.manifest = manifest

    @classmethod
    def build(cls, embeddings: np.ndarray, chunks: list[Chunk], manifest: dict) -> "FaissVectorStore":
        import faiss

        if len(chunks) != embeddings.shape[0]:
            raise ValueError("embeddings and chunks length mismatch")
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)
        return cls(index, chunks, manifest)

    def search(self, query_vec: np.ndarray, k: int) -> list[tuple[int, float]]:
        k = min(k, len(self.chunks))
        if k == 0:
            return []
        scores, ids = self.index.search(query_vec, k)
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i >= 0]

    def save(self, directory: Path) -> None:
        import faiss

        directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(directory / INDEX_FILE))
        with open(directory / CHUNKS_FILE, "w", encoding="utf-8") as f:
            for c in self.chunks:
                f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
        (directory / MANIFEST_FILE).write_text(json.dumps(self.manifest, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, directory: Path) -> "FaissVectorStore":
        import faiss

        index = faiss.read_index(str(directory / INDEX_FILE))
        with open(directory / CHUNKS_FILE, encoding="utf-8") as f:
            chunks = [Chunk(**json.loads(line)) for line in f if line.strip()]
        manifest = json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8"))
        return cls(index, chunks, manifest)

    @staticmethod
    def exists(directory: Path) -> bool:
        return all((directory / f).is_file() for f in (INDEX_FILE, CHUNKS_FILE, MANIFEST_FILE))
