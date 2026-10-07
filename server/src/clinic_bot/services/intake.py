"""Pre-talk checklist retrieval from the authored intake/*.md files."""

from __future__ import annotations

import re
from dataclasses import dataclass

from clinic_bot.ports.embeddings import Embedder
from clinic_bot.ports.vector_store import VectorStore

CHECKLIST_THRESHOLD = 0.35  # for the default fastembed model; config sets it per model
MAX_FOLLOWUPS = 3
_SECTION = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_LIST_ITEM = re.compile(r"^\s*(?:\d+\.|-)\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Checklist:
    symptom: str
    questions: tuple[str, ...]
    red_flags: tuple[str, ...]
    likely_specialty: str

    @classmethod
    def parse(cls, text: str) -> Checklist:
        """Parse ``# title`` + ``## Matches / Questions / Red flags / Likely specialty``."""
        title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), "General")
        sections = _sections(text)
        return cls(
            symptom=title,
            questions=tuple(_LIST_ITEM.findall(sections.get("questions", ""))),
            red_flags=tuple(_LIST_ITEM.findall(sections.get("red flags", ""))),
            likely_specialty=sections.get("likely specialty", "").strip(),
        )


def _sections(text: str) -> dict[str, str]:
    parts = _SECTION.split(text)
    return {parts[i].strip().lower(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


class ChecklistRetriever:
    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        general: Checklist,
        threshold: float = CHECKLIST_THRESHOLD,
    ) -> None:
        self._embedder, self._store, self._general = embedder, store, general
        self._threshold = threshold

    async def for_complaint(self, complaint: str | None) -> Checklist:
        """Best-matching checklist, or the general one below the similarity threshold."""
        if not complaint:
            return self._general
        [vector] = await self._embedder.embed([complaint])
        hits = await self._store.query(vector, k=1, kinds=["intake"])
        if not hits or hits[0].score < self._threshold:
            return self._general
        return Checklist.parse(hits[0].chunk.text)
