"""General health-topic information (MedlinePlus in v1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class HealthTopic:
    title: str
    summary: str
    url: str


class HealthInfoProvider(Protocol):
    async def search(self, query: str) -> HealthTopic | None: ...
