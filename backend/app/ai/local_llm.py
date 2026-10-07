"""Local GGUF inference through llama.cpp (llama-cpp-python)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from pathlib import Path

from app.ai.llm_provider import (
    ChatMessage,
    GenerationParams,
    LLMProvider,
    LLMProviderError,
    LLMResult,
    ModelInfo,
)

logger = logging.getLogger(__name__)

IM_START, IM_END = "<|im_start|>", "<|im_end|>"


def render_qwen3_chatml(messages: list[ChatMessage], enable_thinking: bool) -> str:
    """Render messages with the Qwen3 ChatML template embedded in the GGUF.

    Rendered by hand (rather than via llama-cpp-python's Jinja formatter) so that the
    template's `enable_thinking=False` branch -- an empty <think></think> block -- is honoured.
    Prior assistant turns are emitted without reasoning, matching the template's behaviour.
    """
    parts = [f"{IM_START}{m.role}\n{m.content.strip()}{IM_END}\n" for m in messages]
    parts.append(f"{IM_START}assistant\n")
    if not enable_thinking:
        parts.append("<think>\n\n</think>\n\n")
    return "".join(parts)


def strip_reasoning(text: str) -> str:
    """Remove any <think>...</think> block the model emits."""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.replace("<think>", "").strip()


class LocalGGUFProvider(LLMProvider):
    def __init__(
        self,
        model_path: Path,
        display_name: str,
        n_ctx: int = 4096,
        n_threads: int = 4,
        n_batch: int = 512,
        n_gpu_layers: int = 0,
        enable_thinking: bool = False,
    ) -> None:
        self.model_path = Path(model_path)
        self.display_name = display_name
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.n_batch = n_batch
        self.n_gpu_layers = n_gpu_layers
        self.enable_thinking = enable_thinking
        self._llm = None
        self._metadata: dict = {}
        self._load_seconds: float | None = None
        # A llama.cpp context is not thread-safe: serialise all inference through one lock.
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle
    def load(self) -> None:
        with self._load_lock:
            if self._llm is not None:
                return
            if not self.model_path.is_file():
                raise LLMProviderError(f"GGUF model not found at {self.model_path}")
            try:
                from llama_cpp import Llama
            except ImportError as e:  # pragma: no cover
                raise LLMProviderError("llama-cpp-python is not installed") from e

            t0 = time.perf_counter()
            self._llm = Llama(
                model_path=str(self.model_path),
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_batch=self.n_batch,
                n_gpu_layers=self.n_gpu_layers,
                verbose=False,
            )
            self._load_seconds = time.perf_counter() - t0
            self._metadata = dict(self._llm.metadata)
            logger.info(
                "Loaded GGUF model %s in %.1fs (arch=%s, ctx=%d, threads=%d, gpu_layers=%d)",
                self.model_path.name, self._load_seconds,
                self._metadata.get("general.architecture"), self.n_ctx, self.n_threads, self.n_gpu_layers,
            )

    def is_ready(self) -> bool:
        return self._llm is not None

    def close(self) -> None:
        with self._lock:
            if self._llm is not None:
                self._llm.close()
                self._llm = None

    def info(self) -> ModelInfo:
        md = self._metadata
        return ModelInfo(
            provider="local_gguf (llama.cpp)",
            name=self.display_name,
            loaded=self.is_ready(),
            details={
                "file": self.model_path.name,
                "file_size_mb": round(self.model_path.stat().st_size / 2**20, 1) if self.model_path.exists() else None,
                "architecture": md.get("general.architecture"),
                "gguf_name": md.get("general.name"),
                "size_label": md.get("general.size_label"),
                "quantization": "Q4_K_M" if md.get("general.file_type") == "15" else md.get("general.file_type"),
                "context_length_trained": int(md["qwen3.context_length"]) if "qwen3.context_length" in md else None,
                "n_ctx": self.n_ctx,
                "n_threads": self.n_threads,
                "n_gpu_layers": self.n_gpu_layers,
                "thinking_enabled": self.enable_thinking,
                "load_seconds": round(self._load_seconds, 2) if self._load_seconds else None,
            },
        )

    # ------------------------------------------------------------------ inference
    def _require(self):
        if self._llm is None:
            raise LLMProviderError("Model is not loaded")
        return self._llm

    def count_tokens(self, text: str) -> int:
        llm = self._require()
        return len(llm.tokenize(text.encode("utf-8"), add_bos=False, special=True))

    def _completion_kwargs(self, messages: list[ChatMessage], params: GenerationParams) -> dict:
        prompt = render_qwen3_chatml(messages, self.enable_thinking)
        n_prompt = self.count_tokens(prompt)
        budget = self.n_ctx - n_prompt - 8
        if budget < 32:
            raise LLMProviderError(f"Prompt too long for context window ({n_prompt} tokens, n_ctx={self.n_ctx})")
        return dict(
            prompt=prompt,
            max_tokens=min(params.max_tokens, budget),
            temperature=params.temperature,
            top_p=params.top_p,
            top_k=params.top_k,
            repeat_penalty=params.repeat_penalty,
            stop=[IM_END, "<|endoftext|>", *params.stop],
        )

    def generate(self, messages: list[ChatMessage], params: GenerationParams) -> LLMResult:
        llm = self._require()
        with self._lock:
            kwargs = self._completion_kwargs(messages, params)
            t0 = time.perf_counter()
            out = llm.create_completion(**kwargs)
            latency_ms = (time.perf_counter() - t0) * 1000
        choice = out["choices"][0]
        return LLMResult(
            text=strip_reasoning(choice["text"]),
            prompt_tokens=out["usage"]["prompt_tokens"],
            completion_tokens=out["usage"]["completion_tokens"],
            finish_reason=choice.get("finish_reason") or "stop",
            latency_ms=latency_ms,
            model=self.display_name,
        )

    def stream(self, messages: list[ChatMessage], params: GenerationParams) -> Iterator[str]:
        llm = self._require()
        # The lock is held for the life of the generator and released when it is exhausted
        # or closed (e.g. client disconnect). threading.Lock may be released from any thread.
        self._lock.acquire()
        try:
            kwargs = self._completion_kwargs(messages, params)
            for chunk in llm.create_completion(stream=True, **kwargs):
                delta = chunk["choices"][0]["text"]
                if delta:
                    yield delta
        finally:
            self._lock.release()
