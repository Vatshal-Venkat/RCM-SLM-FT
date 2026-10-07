from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_retriever
from app.core.rate_limit import rate_limit
from app.schemas.rag import KnowledgeIndexInfo, RagHit, RagSearchRequest, RagSearchResponse

router = APIRouter(prefix="/api/rag", tags=["rag"], dependencies=[Depends(rate_limit("rag", "rate_limit_default_per_minute"))])


def _ready_retriever():
    r = get_retriever()
    if r is None or not r.is_ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Knowledge index is not built. Run scripts/ingest_knowledge.py.")
    return r


@router.post("/search", response_model=RagSearchResponse)
async def search(req: RagSearchRequest, retriever=Depends(_ready_retriever)) -> RagSearchResponse:
    t0 = time.perf_counter()
    results = await run_in_threadpool(retriever.retrieve, req.query, req.k)
    return RagSearchResponse(
        query=req.query,
        results=[
            RagHit(chunk_id=r.chunk.chunk_id, document=r.chunk.document, title=r.chunk.title,
                   section=r.chunk.section, text=r.chunk.text, score=round(r.score, 4),
                   dense_score=round(r.dense_score, 4), lexical_score=round(r.lexical_score, 4))
            for r in results
        ],
        took_ms=round((time.perf_counter() - t0) * 1000, 1),
    )


@router.get("/documents", response_model=KnowledgeIndexInfo)
def documents() -> KnowledgeIndexInfo:
    r = get_retriever()
    if r is None or not r.is_ready():
        return KnowledgeIndexInfo(ready=False)
    m = r.manifest
    return KnowledgeIndexInfo(
        ready=True,
        embedding_model=m.get("embedding_model"),
        reranker_model=r.settings.reranker_model if r.reranker else None,
        built_at=m.get("built_at"),
        n_documents=m.get("n_documents", 0),
        n_chunks=m.get("n_chunks", 0),
        documents=m.get("documents", []),
    )
