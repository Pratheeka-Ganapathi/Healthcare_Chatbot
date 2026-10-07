"""Chat summaries: LLM summary for verified chats, fallback when the LLM is down."""

from __future__ import annotations

from datetime import timedelta

from clinic_bot.adapters.clock import FrozenClock
from clinic_bot.domain.entities import TranscriptRecord
from clinic_bot.domain.errors import ErrorCode, Unavailable
from clinic_bot.services.chat_summaries import ChatSummaryService
from tests.fakes.llm import FakeStructuredLLM
from tests.fakes.repos import InMemoryUnitOfWorkFactory

TURNS = (
    {"role": "user", "text": "9000000005, 3 March 1995"},
    {"role": "bot", "text": "Thanks Sanjay. Is the rash spreading?"},
    {"role": "user", "text": "a little"},
    {"role": "bot", "text": "Your visit with Dr. Kavya Shetty on Wed 7 Oct is booked."},
)


def record(clock: FrozenClock, patient_id: int | None = 5) -> TranscriptRecord:
    return TranscriptRecord("s1", patient_id, TURNS, (), clock.now())


async def test_stores_the_llm_summary_on_the_patient(clock: FrozenClock) -> None:
    uow, llm = InMemoryUnitOfWorkFactory(), FakeStructuredLLM()
    llm.written = "Sanjay booked dermatology for a spreading rash."
    saved = await ChatSummaryService(llm, uow, clock).store(record(clock))
    assert saved.summary == "Sanjay booked dermatology for a spreading rash."
    assert (saved.patient_id, saved.session_id, saved.created_at) == (5, "s1", clock.now())
    assert llm.calls == [
        "\n".join(
            f"{who}: {t['text']}"
            for who, t in zip(["Patient", "Assistant", "Patient", "Assistant"], TURNS, strict=True)
        )
    ]
    async with uow() as u:
        assert await u.chat_summaries.for_patient(5) == [saved]


async def test_falls_back_to_bot_replies_when_the_llm_is_down(clock: FrozenClock) -> None:
    uow, llm = InMemoryUnitOfWorkFactory(), FakeStructuredLLM()
    llm.fail_with = Unavailable(ErrorCode.BUSY, "rate limited", retryable=True)
    saved = await ChatSummaryService(llm, uow, clock).store(record(clock))
    assert saved.summary.startswith("Automatic summary unavailable")
    assert "session s1" in saved.summary and "Dr. Kavya Shetty" in saved.summary
    assert "9000000005" not in saved.summary  # patient text (phone, DOB) never in the fallback


async def test_submit_skips_unverified_chats(clock: FrozenClock) -> None:
    uow, llm = InMemoryUnitOfWorkFactory(), FakeStructuredLLM()
    service = ChatSummaryService(llm, uow, clock)
    service.submit(record(clock, patient_id=None))
    service.submit(record(clock))
    later = TranscriptRecord("s2", 5, TURNS, (), clock.now() + timedelta(hours=1))
    service.submit(later)
    await service.aclose()
    assert llm.calls and len(llm.calls) == 2
    async with uow() as u:
        rows = await u.chat_summaries.for_patient(5)
    assert [r.session_id for r in rows] == ["s2", "s1"]  # newest first
