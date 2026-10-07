"""Per-model RAG cut-offs (SPEC 7) and batching for hosted embedders."""

from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any, cast

import pytest

from clinic_bot.adapters.embeddings import litellm_embedder
from clinic_bot.adapters.embeddings.litellm_embedder import MAX_BATCH, LiteLLMEmbedder
from clinic_bot.config import SERVER_ROOT, Settings
from clinic_bot.domain.errors import NotFound
from clinic_bot.ports.vector_store import Chunk, ScoredChunk
from clinic_bot.services.directory import DoctorDirectory
from clinic_bot.services.faq import FaqService
from clinic_bot.services.intake import Checklist, ChecklistRetriever
from tests.fakes.health import FakeHealthInfo


class OneHitStore:
    """Returns one chunk of the requested kind with a fixed score."""

    def __init__(self, score: float, text: str) -> None:
        self.score, self.text = score, text

    async def query(
        self, embedding: Sequence[float], k: int, kinds: Sequence[str]
    ) -> list[ScoredChunk]:
        return [ScoredChunk(Chunk("c", self.text, "doc.md", "Section", kinds[0]), self.score)]

    async def count(self) -> int:
        return 1


class ZeroEmbedder:
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_each_embedding_model_has_its_own_cutoffs() -> None:
    assert (_settings().faq_cutoff, _settings().checklist_cutoff) == (0.35, 0.35)
    gemini = _settings(embed_backend="gemini", embed_model="gemini-embedding-001")
    assert (gemini.faq_cutoff, gemini.checklist_cutoff) == (0.60, 0.60)


def test_env_overrides_the_model_default() -> None:
    s = _settings(embed_backend="gemini", faq_threshold=0.7, checklist_threshold=0.5)
    assert (s.faq_cutoff, s.checklist_cutoff) == (0.7, 0.5)


def test_embeddings_use_their_own_key_when_set() -> None:
    shared = _settings(embed_backend="gemini", google_api_key="chat-key", embed_api_key=None)
    assert shared.embedding_key() == "chat-key"
    own = _settings(embed_backend="gemini", google_api_key="chat-key", embed_api_key="embed-key")
    assert own.embedding_key() == "embed-key"
    assert own.api_key("google") == "chat-key"


async def test_faq_uses_its_cutoff() -> None:
    def faq(threshold: float) -> FaqService:
        store = OneHitStore(0.5, "Two-wheeler parking is in the basement.")
        directory = cast(DoctorDirectory, object())  # not reached: no doctor question
        return FaqService(ZeroEmbedder(), store, FakeHealthInfo(), directory, threshold)

    answer = await faq(0.35).answer("is parking available", health_topics_allowed=False)
    assert answer.passages == ("Two-wheeler parking is in the basement.",)
    with pytest.raises(NotFound):  # the same score is a miss under Gemini's cut-off
        await faq(0.60).answer("is parking available", health_topics_allowed=False)


async def test_checklist_uses_its_cutoff() -> None:
    general = Checklist.parse(
        (SERVER_ROOT / "data/docs/intake/general.md").read_text(encoding="utf-8")
    )
    skin = (SERVER_ROOT / "data/docs/intake/skin.md").read_text(encoding="utf-8")
    store = OneHitStore(0.55, skin)
    assert (
        await ChecklistRetriever(ZeroEmbedder(), store, general, 0.35).for_complaint("rash")
        != general
    )
    assert (
        await ChecklistRetriever(ZeroEmbedder(), store, general, 0.60).for_complaint("rash")
        == general
    )


async def test_hosted_embedder_sends_at_most_100_texts_per_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batches: list[int] = []

    async def fake_aembedding(*, model: str, input: list[str], api_key: str) -> Any:
        batches.append(len(input))
        return SimpleNamespace(data=[{"embedding": [1.0]} for _ in input])

    monkeypatch.setattr(litellm_embedder.litellm, "aembedding", fake_aembedding)
    vectors = await LiteLLMEmbedder("gemini", "gemini-embedding-001", "k").embed(["t"] * 230)
    assert batches == [MAX_BATCH, MAX_BATCH, 30] and len(vectors) == 230
