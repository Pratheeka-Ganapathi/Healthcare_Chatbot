"""Hosted embeddings (OpenAI or Gemini) through LiteLLM. Selected with EMBED_BACKEND."""

from __future__ import annotations

from collections.abc import Sequence

import litellm
import openai

from clinic_bot.domain.errors import ErrorCode, Unavailable

_PREFIX = {"openai": "openai/", "gemini": "gemini/"}
MAX_BATCH = 100  # Gemini rejects a batch of more than 100 texts; OpenAI allows more


class LiteLLMEmbedder:
    def __init__(self, backend: str, model: str, api_key: str) -> None:
        self._backend, self._name, self._api_key = backend, model, api_key

    @property
    def key(self) -> str:
        return f"{self._backend}:{self._name}"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """In batches of ``MAX_BATCH`` (an index rebuild embeds every chunk at once)."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH):
            vectors += await self._embed_batch(texts[start : start + MAX_BATCH])
        return vectors

    async def _embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            response = await litellm.aembedding(
                model=_PREFIX[self._backend] + self._name, input=list(texts), api_key=self._api_key
            )
        except openai.OpenAIError as exc:  # base of every LiteLLM API exception
            raise Unavailable(ErrorCode.BUSY, type(exc).__name__) from exc
        return [list(item["embedding"]) for item in response.data]
