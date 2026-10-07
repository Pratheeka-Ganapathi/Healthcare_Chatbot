"""Decorator: retry with backoff on a rate-limited StructuredLLM call."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from clinic_bot.domain.errors import Unavailable
from clinic_bot.ports.llm import StructuredLLM


class RetryingLLM:
    def __init__(self, inner: StructuredLLM, retries: int = 1, backoff_s: float = 1.0) -> None:
        self._inner, self._retries, self._backoff = inner, retries, backoff_s

    async def classify(self, system: str, user: str, labels: Sequence[str]) -> tuple[str, str]:
        return await self._call(lambda: self._inner.classify(system, user, labels))

    async def write(self, system: str, user: str) -> str:
        return await self._call(lambda: self._inner.write(system, user))

    async def _call[T](self, call: Callable[[], Awaitable[T]]) -> T:
        attempt = 0
        while True:
            try:
                return await call()
            except Unavailable as exc:
                if not exc.data.get("retryable") or attempt >= self._retries:
                    raise
                attempt += 1
                await asyncio.sleep(self._backoff * attempt)
