"""Application settings, loaded from environment variables / .env (never from source)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


def _default_threads() -> int:
    # Measured on an 8-thread Ryzen 5 7235HS: 6 threads gave the best generation speed
    # (22 tok/s vs 14 at 4 and 16 at 8). Leave two logical cores for the API and embeddings.
    return max(1, (os.cpu_count() or 4) - 2)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "RCM AI Platform"
    environment: str = Field(default="development", pattern="^(development|staging|production|test)$")
    log_level: str = "INFO"

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # --- Rate limiting (per client, per minute) ---
    rate_limit_enabled: bool = True
    rate_limit_chat_per_minute: int = 20
    rate_limit_default_per_minute: int = 120

    # --- LLM (local GGUF via llama.cpp) ---
    llm_provider: str = "local_gguf"
    model_path: Path = BACKEND_DIR / "models" / "rcm_qwen3_1.7b_q4_k_m.gguf"
    model_display_name: str = "RCM-Qwen3-1.7B (QLoRA, Q4_K_M)"
    llm_load_on_startup: bool = True
    llm_n_ctx: int = 4096
    llm_n_threads: int = Field(default_factory=_default_threads)
    llm_n_batch: int = 512
    llm_n_gpu_layers: int = 0  # >0 only with a CUDA/Vulkan build of llama.cpp
    llm_max_tokens: int = 512
    llm_temperature: float = 0.3
    llm_top_p: float = 0.8
    llm_top_k: int = 20
    llm_repeat_penalty: float = 1.1
    llm_enable_thinking: bool = False

    # --- Chat ---
    chat_max_message_chars: int = 2000
    chat_max_history_turns: int = 6

    # --- RAG ---
    knowledge_dir: Path = REPO_ROOT / "knowledge"
    index_dir: Path = BACKEND_DIR / "data" / "index"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # BGE models retrieve better when short queries carry this instruction prefix.
    embedding_query_prefix: str = "Represent this sentence for searching relevant passages: "
    rerank_enabled: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rag_load_on_startup: bool = True
    rag_top_k: int = 4
    rag_candidates: int = 12
    rag_chunk_max_chars: int = 1000
    rag_chunk_overlap_chars: int = 150

    # --- Database ---
    # SQLite by default for zero-setup local runs; set DATABASE_URL for PostgreSQL / Neon, e.g.
    # postgresql+psycopg://user:pass@host/db?sslmode=require
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'rcm.db').as_posix()}"
    database_echo: bool = False

    @field_validator("model_path", "knowledge_dir", "index_dir", mode="before")
    @classmethod
    def _resolve_model_path(cls, v: str | Path) -> Path:
        p = Path(v)
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
