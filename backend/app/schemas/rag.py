from __future__ import annotations

from pydantic import BaseModel, Field


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    k: int = Field(default=5, ge=1, le=20)


class RagHit(BaseModel):
    chunk_id: str
    document: str
    title: str
    section: str | None
    text: str
    score: float
    dense_score: float
    lexical_score: float


class RagSearchResponse(BaseModel):
    query: str
    results: list[RagHit]
    took_ms: float


class KnowledgeDocument(BaseModel):
    file: str
    title: str
    category: str | None = None
    source_basis: str | None = None
    chunks: int


class KnowledgeIndexInfo(BaseModel):
    ready: bool
    embedding_model: str | None = None
    reranker_model: str | None = None
    built_at: str | None = None
    n_documents: int = 0
    n_chunks: int = 0
    documents: list[KnowledgeDocument] = Field(default_factory=list)
