"""Out-of-pipeline LLM calls (classifier, mapper, chat summaries)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class StructuredLLM(Protocol):
    async def classify(self, system: str, user: str, labels: Sequence[str]) -> tuple[str, str]:
        """Return ``(label, reason)``; ``label`` is always one of ``labels``.

        Raises ``Unavailable`` on rate limit, timeout or unparseable output.
        """
        ...

    async def write(self, system: str, user: str) -> str:
        """Free text, e.g. a chat summary. Raises ``Unavailable`` like ``classify``."""
        ...
