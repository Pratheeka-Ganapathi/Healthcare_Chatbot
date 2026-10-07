"""Health-topic provider stand-in."""

from __future__ import annotations

from clinic_bot.ports.health_info import HealthTopic


class FakeHealthInfo:
    def __init__(self, topics: dict[str, HealthTopic] | None = None) -> None:
        self.topics = topics or {}
        self.queries: list[str] = []

    async def search(self, query: str) -> HealthTopic | None:
        self.queries.append(query)
        lowered = query.lower()
        return next((t for k, t in self.topics.items() if k in lowered), None)
