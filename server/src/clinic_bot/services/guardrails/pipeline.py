"""Per-turn guard orchestration: sync regex precheck, async classifier task."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from clinic_bot.domain.errors import Unavailable
from clinic_bot.services.guardrails.base import Guard, GuardContext, Verdict
from clinic_bot.services.guardrails.regex_guard import RegexGuard

ClassifierFailureHook = Callable[[str], None]


class GuardPipeline:
    def __init__(self, regex: RegexGuard, classifier: Guard, timeout_s: float) -> None:
        self._regex, self._classifier, self._timeout = regex, classifier, timeout_s

    @property
    def regex(self) -> RegexGuard:
        return self._regex

    def precheck(self, text: str) -> Verdict:
        return self._regex.precheck(text)

    def blocking(self, text: str) -> Verdict:
        return self._regex.blocking(text)

    def start_classifier(
        self, text: str, ctx: GuardContext, on_failure: ClassifierFailureHook | None = None
    ) -> asyncio.Task[Verdict]:
        """The task never raises: timeout, 429 after retry or bad output → NONE (default)."""
        return asyncio.create_task(self._classify(text, ctx, on_failure), name="guard-classifier")

    async def _classify(
        self, text: str, ctx: GuardContext, on_failure: ClassifierFailureHook | None
    ) -> Verdict:
        started = time.perf_counter()
        try:
            return await asyncio.wait_for(self._classifier.check(text, ctx), self._timeout)
        except (TimeoutError, Unavailable) as exc:
            if on_failure is not None:
                on_failure(f"{type(exc).__name__} after {time.perf_counter() - started:.2f}s")
            return Verdict.none("default")
