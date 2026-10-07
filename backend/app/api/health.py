from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from app.ai.factory import get_llm_provider
from app.api.deps import get_retriever
from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    llm = get_llm_provider()
    retriever = get_retriever()
    ready = llm.is_ready()
    return {
        "status": "ok" if ready else "degraded",
        "app": get_settings().app_name,
        "components": {
            "llm": {"ready": ready, "provider": llm.info().provider},
            "rag": {"ready": bool(retriever and retriever.is_ready())},
        },
    }


@router.get("/api/model")
def model_info() -> dict:
    return asdict(get_llm_provider().info())
