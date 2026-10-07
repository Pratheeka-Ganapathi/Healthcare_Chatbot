"""Text embedding port."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Embedder(Protocol):
    @property
    def key(self) -> str:
        """Backend + model identifier; the vector index is keyed by it."""
        ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
