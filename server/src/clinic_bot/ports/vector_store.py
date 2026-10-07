"""Vector store port over authored clinic documents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    text: str
    doc: str
    section: str
    kind: str  # faq | specialty | intake | prep


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    chunk: Chunk
    score: float  # cosine similarity, higher is closer


class VectorStore(Protocol):
    async def query(
        self, embedding: Sequence[float], k: int, kinds: Sequence[str]
    ) -> list[ScoredChunk]: ...

    async def count(self) -> int: ...


class DocIndexer(Protocol):
    """Rebuilds the clinic-doc chunks from the editable documents (SPEC 17.3)."""

    async def rebuild(self, docs: Mapping[str, str]) -> int:
        """Re-embed and swap every chunk; returns the chunk count. Queries keep working."""
        ...

    async def ensure_current(self, docs: Mapping[str, str]) -> bool:
        """Rebuild only if ``docs`` differ from what was last indexed. True if rebuilt."""
        ...
