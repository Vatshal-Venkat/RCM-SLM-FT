"""Construct the configured LLM provider. The only place that knows concrete provider classes."""

from __future__ import annotations

from functools import lru_cache

from app.ai.llm_provider import LLMProvider
from app.core.config import get_settings


@lru_cache
def get_llm_provider() -> LLMProvider:
    s = get_settings()
    if s.llm_provider == "local_gguf":
        from app.ai.local_llm import LocalGGUFProvider

        return LocalGGUFProvider(
            model_path=s.model_path,
            display_name=s.model_display_name,
            n_ctx=s.llm_n_ctx,
            n_threads=s.llm_n_threads,
            n_batch=s.llm_n_batch,
            n_gpu_layers=s.llm_n_gpu_layers,
            enable_thinking=s.llm_enable_thinking,
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {s.llm_provider!r}")
