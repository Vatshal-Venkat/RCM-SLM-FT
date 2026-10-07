"""FastAPI application entrypoint: `uvicorn app.main:app` from the backend/ directory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.ai.factory import get_llm_provider
from app.ai.llm_provider import LLMProviderError
from app.api import analytics, chat, claims, health, rag
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.rag.retriever import get_retriever

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    llm = get_llm_provider()
    if settings.llm_load_on_startup:
        try:
            await run_in_threadpool(llm.load)
        except LLMProviderError:
            # Keep serving (health reports "degraded") so the problem is visible, not a crash loop.
            logger.exception("Failed to load the LLM at startup")
    if settings.rag_load_on_startup:
        try:
            await run_in_threadpool(get_retriever().load)
        except Exception:
            logger.exception("Failed to load the RAG index at startup")
    yield
    llm.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        # Return field locations and messages only -- never echo the submitted input back.
        errors = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(rag.router)
    app.include_router(analytics.router)
    app.include_router(claims.router)
    return app


app = create_app()
