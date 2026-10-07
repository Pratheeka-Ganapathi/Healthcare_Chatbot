"""Decorator: in-memory LRU in front of a disk cache, keyed by normalised query."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import OrderedDict
from pathlib import Path

from clinic_bot.ports.health_info import HealthInfoProvider, HealthTopic

LRU_SIZE = 256
DEMO_QUERIES = (
    "what is an hba1c test",
    "what is a thyroid test",
    "what is a lipid profile",
    "what is an ecg",
)


def normalise(query: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", query.lower())).strip()


class CachedHealthInfo:
    def __init__(self, inner: HealthInfoProvider, cache_dir: Path, size: int = LRU_SIZE) -> None:
        self._inner, self._dir, self._size = inner, cache_dir, size
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lru: OrderedDict[str, HealthTopic | None] = OrderedDict()

    async def search(self, query: str) -> HealthTopic | None:
        key = normalise(query)
        if key in self._lru:
            self._lru.move_to_end(key)
            return self._lru[key]
        found, topic = await asyncio.to_thread(self._read_disk, key)
        if not found:
            topic = await self._inner.search(query)
            if topic is not None:
                await asyncio.to_thread(self._write_disk, key, topic)
        self._remember(key, topic)
        return topic

    def _path(self, key: str) -> Path:
        return self._dir / f"{hashlib.sha256(key.encode()).hexdigest()[:32]}.json"

    def _read_disk(self, key: str) -> tuple[bool, HealthTopic | None]:
        path = self._path(key)
        if not path.exists():
            return False, None
        data = json.loads(path.read_text(encoding="utf-8"))
        return True, HealthTopic(data["title"], data["summary"], data["url"])

    def _write_disk(self, key: str, topic: HealthTopic) -> None:
        payload = {"title": topic.title, "summary": topic.summary, "url": topic.url}
        self._path(key).write_text(json.dumps(payload), encoding="utf-8")

    def _remember(self, key: str, topic: HealthTopic | None) -> None:
        self._lru[key] = topic
        if len(self._lru) > self._size:
            self._lru.popitem(last=False)


async def prewarm(provider: CachedHealthInfo) -> int:
    hits = [await provider.search(q) for q in DEMO_QUERIES]
    return sum(1 for h in hits if h is not None)
