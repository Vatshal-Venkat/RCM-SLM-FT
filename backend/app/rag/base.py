"""Retrieval contracts shared by the RAG pipeline and its consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Chunk:
    chunk_id: str
    document: str  # source file name, e.g. "era_eob.md"
    title: str  # document title
    section: str | None  # heading path within the document
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float  # final relevance score in [0, 1] (higher is better)
    dense_score: float = 0.0
    lexical_score: float = 0.0


class KnowledgeRetriever(Protocol):
    def retrieve(self, query: str, k: int = 4) -> list[RetrievedChunk]: ...

    def is_ready(self) -> bool: ...
