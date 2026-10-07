"""Dependency wiring. Routes receive services from here; nothing else constructs them."""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException, status

from app.ai.factory import get_llm_provider
from app.ai.llm_provider import LLMProvider
from app.core.config import get_settings
from app.rag.retriever import HybridRetriever
from app.rag.retriever import get_retriever as _get_retriever
from app.services.chat_service import ChatService
from app.services.claim_analysis import ClaimAnalysisService
from app.services.copilot_context import AnalyticsContextProvider


def ensure_llm_ready() -> LLMProvider:
    """Called inside handlers (after request validation) so bad input gets 422, not 503."""
    llm = get_llm_provider()
    if not llm.is_ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Model is not loaded yet.")
    return llm


def get_retriever() -> HybridRetriever:
    return _get_retriever()


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(
        llm=get_llm_provider(), settings=get_settings(), retriever=get_retriever(),
        data_provider=AnalyticsContextProvider(),
    )


@lru_cache
def get_claim_analysis_service() -> ClaimAnalysisService:
    return ClaimAnalysisService(llm=get_llm_provider(), settings=get_settings(), retriever=get_retriever())
