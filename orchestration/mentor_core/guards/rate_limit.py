"""
Token-bucket rate limiting and bounded exponential-backoff retry for
asynchronous exchange calls.
"""

from __future__ import annotations

import asyncio
import time
from functools import wraps
from typing import Awaitable, Callable, Optional, Tuple, Type, TypeVar

from orchestration.config import RateLimitSettings

T = TypeVar("T")


class RateLimiter:
    """Continuous-refill token bucket. One instance per exchange connection."""

    def __init__(self, max_tokens: int = 100, period_sec: float = 60.0) -> None:
        self.max_tokens = float(max_tokens)
        self.refill_per_sec = float(max_tokens) / float(period_sec)
        self.tokens = float(max_tokens)
        self.last_refill = time.monotonic()
        self._lock: Optional[asyncio.Lock] = None

    def _refill(self) -> None:
        now = time.monotonic()
        self.tokens = min(self.max_tokens, self.tokens + (now - self.last_refill) * self.refill_per_sec)
        self.last_refill = now

    async def acquire(self, cost: float = 1.0) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            self._refill()
            if self.tokens < cost:
                await asyncio.sleep((cost - self.tokens) / self.refill_per_sec)
                self._refill()
            self.tokens -= cost


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    factor: float = 2.0,
    max_delay: float = 10.0,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Retry an awaitable a bounded number of times. Re-raises the last error."""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            delay = base_delay
            last_exc: Optional[BaseException] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_on as exc:  # noqa: PERF203
                    last_exc = exc
                    if attempt >= max_attempts:
                        raise
                    if delay > 0:
                        await asyncio.sleep(delay)
                    delay = min(delay * factor, max_delay)
            assert last_exc is not None  # pragma: no cover
            raise last_exc

        return wrapper

    return decorator


def limiter_from_settings(settings: Optional[RateLimitSettings] = None) -> RateLimiter:
    settings = settings or RateLimitSettings()
    return RateLimiter(settings.tokens, settings.period_sec)


def rate_limited(limiter=None, cost: float = 1.0):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if limiter is not None:
                await limiter.acquire(cost)
            elif len(args) > 0 and hasattr(args[0], "rate_limiter"):
                await args[0].rate_limiter.acquire(cost)
            return await func(*args, **kwargs)
        return wrapper
    return decorator
