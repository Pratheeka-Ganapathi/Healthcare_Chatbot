"""Layer 1: precompiled, case-insensitive pattern sets, checked in priority order."""

from __future__ import annotations

import re
from collections.abc import Sequence

from clinic_bot.domain.enums import GuardrailLabel
from clinic_bot.services.guardrails import patterns
from clinic_bot.services.guardrails.base import BLOCKING_LABELS, Guard, GuardContext, Verdict


def _compile(parts: Sequence[str]) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in parts), re.IGNORECASE)


class RegexGuard(Guard):
    _ORDER: tuple[tuple[GuardrailLabel, re.Pattern[str]], ...] = (
        (GuardrailLabel.SELF_HARM, _compile(patterns.SELF_HARM)),
        (GuardrailLabel.EMERGENCY, _compile(patterns.EMERGENCY)),
        (GuardrailLabel.MEDICATION, _compile(patterns.MEDICATION)),
        (GuardrailLabel.OFF_TOPIC, _compile(patterns.OFF_TOPIC)),
    )

    def precheck(self, text: str) -> Verdict:
        for label, pattern in self._ORDER:
            if match := pattern.search(text):
                return Verdict(label, "regex", match.group(0))
        return Verdict.none("regex")

    async def check(self, text: str, ctx: GuardContext) -> Verdict:
        return self.precheck(text)

    def blocking(self, text: str) -> Verdict:
        """Medication and off-topic only; used after an advisory match, which never blocks."""
        for label, pattern in self._ORDER:
            if label in BLOCKING_LABELS and (match := pattern.search(text)):
                return Verdict(label, "regex", match.group(0))
        return Verdict.none("regex")
