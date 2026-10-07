"""Rate limiting abstraction.

`RateLimiter` is the interface; `InMemoryRateLimiter` is a sliding-window implementation
suitable for a single process. Swap in a Redis-backed implementation for multi-instance
deployments without touching the routes.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


class RateLimiter(ABC):
    @abstractmethod
    def hit(self, key: str, limit: int, window_s: float = 60.0) -> bool:
        """Record a request for `key`; return False if it exceeds `limit` per window."""


class InMemoryRateLimiter(RateLimiter):
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: float = 60.0) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


_limiter: RateLimiter = InMemoryRateLimiter()


def rate_limit(bucket: str, per_minute_setting: str):
    """FastAPI dependency factory: `Depends(rate_limit("chat", "rate_limit_chat_per_minute"))`."""

    def dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        client = request.client.host if request.client else "unknown"
        limit = getattr(settings, per_minute_setting)
        if not _limiter.hit(f"{bucket}:{client}", limit):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded. Try again shortly.")

    return dependency
