"""Model-agnostic LLM interface.

Application code depends only on `LLMProvider`; concrete backends (local GGUF via llama.cpp
today, possibly a llama-server/OpenAI-compatible endpoint later) live in their own modules
and are selected by `get_llm_provider()` from settings.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class GenerationParams:
    max_tokens: int = 512
    temperature: float = 0.3
    top_p: float = 0.8
    top_k: int = 20
    repeat_penalty: float = 1.1
    stop: tuple[str, ...] = ()


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str
    latency_ms: float
    model: str


@dataclass
class ModelInfo:
    provider: str
    name: str
    loaded: bool
    details: dict = field(default_factory=dict)


class LLMProviderError(RuntimeError):
    """Raised when the model is unavailable or generation fails."""


class LLMProvider(ABC):
    @abstractmethod
    def load(self) -> None:
        """Load model weights. Idempotent."""

    @abstractmethod
    def is_ready(self) -> bool: ...

    @abstractmethod
    def info(self) -> ModelInfo: ...

    @abstractmethod
    def generate(self, messages: list[ChatMessage], params: GenerationParams) -> LLMResult:
        """Blocking chat completion."""

    @abstractmethod
    def stream(self, messages: list[ChatMessage], params: GenerationParams) -> Iterator[str]:
        """Blocking iterator of text deltas."""

    @abstractmethod
    def count_tokens(self, text: str) -> int: ...

    def close(self) -> None:  # pragma: no cover - optional
        pass
