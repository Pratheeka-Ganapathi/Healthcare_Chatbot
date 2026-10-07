"""Local ONNX embeddings (no torch)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from fastembed import TextEmbedding


class FastEmbedEmbedder:
    def __init__(self, model: str, cache_dir: str | None = None) -> None:
        self._name = model
        self._model = TextEmbedding(model_name=model, cache_dir=cache_dir)

    @property
    def key(self) -> str:
        return f"fastembed:{self._name}"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed_sync, list(texts))

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]
