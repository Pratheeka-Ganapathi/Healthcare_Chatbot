"""When a verified patient's chat ends, summarise it and keep it on their record.

Runs off the turn path: the session submits on disconnect, a background task calls the
summary LLM and writes one ``chat_summaries`` row. If the LLM is unavailable a plain
fallback is stored, so every verified chat leaves a row.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence

import structlog

from clinic_bot.domain.entities import ChatSummary, TranscriptRecord
from clinic_bot.domain.errors import DomainError, Unavailable
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.llm import StructuredLLM
from clinic_bot.ports.unit_of_work import UnitOfWorkFactory

log = structlog.get_logger(__name__)

SUMMARY_PROMPT = (
    "You write short notes for a clinic front desk's patient records. Summarise this chat "
    "between a patient and the City Care Clinic front-desk assistant in 3 to 5 plain "
    "sentences: why the patient got in touch, the symptoms or concerns they shared, what "
    "was done (appointment booked or cancelled with doctor, day and time; questions "
    "answered; callback requested; safety notes shown) and anything left open. Use only "
    "facts stated in the chat. Leave out phone numbers and dates of birth. No markdown."
)
FALLBACK_REPLIES = 3
CLOSE_TIMEOUT_S = 10.0
_SPEAKER = {"user": "Patient", "bot": "Assistant"}


def fallback_summary(record: TranscriptRecord) -> str:
    """Used when the LLM is unavailable. Bot replies only, so no typed phone or DOB."""
    replies = [t["text"] for t in record.turns if t.get("role") == "bot"][-FALLBACK_REPLIES:]
    head = f"Automatic summary unavailable; full chat in transcripts, session {record.session_id}."
    return " ".join([head, *(f"Assistant: {r}" for r in replies)])


def _transcript(turns: Sequence[Mapping[str, str]]) -> str:
    return "\n".join(f"{_SPEAKER.get(t['role'], t['role'])}: {t['text']}" for t in turns)


class ChatSummaryService:
    def __init__(self, llm: StructuredLLM, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._llm, self._uow, self._clock = llm, uow, clock
        self._pending: set[asyncio.Task[None]] = set()

    def submit(self, record: TranscriptRecord) -> None:
        """Called when a chat ends. Chats that never verified a patient are skipped."""
        if record.patient_id is None or not record.turns:
            return
        task = asyncio.create_task(self._run(record), name=f"chat-summary-{record.session_id}")
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def store(self, record: TranscriptRecord) -> ChatSummary:
        if record.patient_id is None:
            raise ValueError("only verified chats are summarised")
        summary = ChatSummary(
            id=None,
            patient_id=record.patient_id,
            session_id=record.session_id,
            summary=await self._summarise(record),
            created_at=record.created_at or self._clock.now(),
        )
        async with self._uow(write=True) as uow:
            saved = await uow.chat_summaries.add(summary)
            await uow.commit()
        return saved

    async def aclose(self) -> None:
        """Give in-flight summaries a short grace period, then drop them."""
        if not self._pending:
            return
        _, late = await asyncio.wait(self._pending, timeout=CLOSE_TIMEOUT_S)
        for task in late:
            task.cancel()

    async def _run(self, record: TranscriptRecord) -> None:
        try:
            saved = await self.store(record)
        except DomainError:
            log.exception("chat_summary_failed", session_id=record.session_id)
            return
        log.info("chat_summary_saved", session_id=record.session_id, summary_id=saved.id)

    async def _summarise(self, record: TranscriptRecord) -> str:
        try:
            text = await self._llm.write(SUMMARY_PROMPT, _transcript(record.turns))
        except Unavailable:
            log.warning("chat_summary_fallback", session_id=record.session_id)
            return fallback_summary(record)
        return text.strip() or fallback_summary(record)
