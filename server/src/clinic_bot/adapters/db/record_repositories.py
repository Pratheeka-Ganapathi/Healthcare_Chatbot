"""SQL repositories for records around bookings: follow-up grants, verify attempts,
callbacks, chat summaries and transcripts."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from clinic_bot.adapters.db import mappers
from clinic_bot.adapters.db.mappers import from_db_time, to_db_time
from clinic_bot.adapters.db.orm import (
    CallbackRow,
    ChatSummaryRow,
    FollowupGrantRow,
    TranscriptRow,
    VerifyAttemptRow,
)
from clinic_bot.domain.entities import (
    Callback,
    ChatSummary,
    FollowupGrant,
    TranscriptRecord,
    VerifyAttempt,
)
from clinic_bot.domain.errors import ErrorCode, NotFound
from clinic_bot.ports.clock import Clock


class SqlFollowupRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def active(self, patient_id: int, doctor_id: int, today: date) -> FollowupGrant | None:
        stmt = select(FollowupGrantRow).where(
            FollowupGrantRow.patient_id == patient_id,
            FollowupGrantRow.doctor_id == doctor_id,
            FollowupGrantRow.valid_until >= today,
            FollowupGrantRow.used_appointment_id.is_(None),
        )
        row = await self._s.scalar(stmt.order_by(FollowupGrantRow.valid_until.desc()))
        return mappers.grant(row) if row else None

    async def get(self, grant_id: int) -> FollowupGrant | None:
        row = await self._s.get(FollowupGrantRow, grant_id)
        return mappers.grant(row) if row else None

    async def save(self, grant: FollowupGrant) -> None:
        row = await self._s.get(FollowupGrantRow, grant.id)
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND)
        row.valid_until = grant.valid_until
        row.used_appointment_id = grant.used_appointment_id
        await self._s.flush()

    async def add(
        self,
        patient_id: int,
        doctor_id: int,
        source_appointment_id: int,
        valid_until: date,
        created_by: str,
    ) -> FollowupGrant:
        row = FollowupGrantRow(
            patient_id=patient_id,
            doctor_id=doctor_id,
            source_appointment_id=source_appointment_id,
            valid_until=valid_until,
            created_by=created_by,
        )
        self._s.add(row)
        await self._s.flush()
        return mappers.grant(row)

    async def delete(self, grant_id: int) -> None:
        await self._s.execute(delete(FollowupGrantRow).where(FollowupGrantRow.id == grant_id))


class SqlVerifyAttemptRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, attempt: VerifyAttempt) -> None:
        self._s.add(
            VerifyAttemptRow(
                phone_norm=attempt.phone_norm, ts=to_db_time(attempt.ts), success=attempt.success
            )
        )
        await self._s.flush()

    async def since(self, phone_norm: str, since: datetime) -> list[VerifyAttempt]:
        stmt = select(VerifyAttemptRow).where(
            VerifyAttemptRow.phone_norm == phone_norm, VerifyAttemptRow.ts >= to_db_time(since)
        )
        rows = await self._s.scalars(stmt.order_by(VerifyAttemptRow.ts))
        return [VerifyAttempt(r.phone_norm, from_db_time(r.ts), r.success) for r in rows]


class SqlCallbackRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, callback: Callback) -> Callback:
        row = CallbackRow(
            patient_id=callback.patient_id,
            reason=callback.reason,
            summary=callback.summary,
            priority=callback.priority.value,
            created_at=to_db_time(callback.created_at),
        )
        self._s.add(row)
        await self._s.flush()
        return callback.with_id(row.id)


class SqlChatSummaryRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, summary: ChatSummary) -> ChatSummary:
        row = ChatSummaryRow(
            patient_id=summary.patient_id,
            session_id=summary.session_id,
            summary=summary.summary,
            created_at=to_db_time(summary.created_at),
        )
        self._s.add(row)
        await self._s.flush()
        return summary.with_id(row.id)

    async def for_patient(self, patient_id: int) -> list[ChatSummary]:
        stmt = select(ChatSummaryRow).where(ChatSummaryRow.patient_id == patient_id)
        newest = stmt.order_by(ChatSummaryRow.created_at.desc(), ChatSummaryRow.id.desc())
        return [
            ChatSummary(r.id, r.patient_id, r.session_id, r.summary, from_db_time(r.created_at))
            for r in await self._s.scalars(newest)
        ]


class SqlTranscriptRepo:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self._s, self._clock = session, clock

    async def add_many(self, records: Sequence[TranscriptRecord]) -> None:
        now = to_db_time(self._clock.now())
        self._s.add_all(
            TranscriptRow(
                session_id=r.session_id,
                patient_id=r.patient_id,
                turns=[dict(t) for t in r.turns],
                guardrail_events=[dict(e) for e in r.guardrail_events],
                created_at=to_db_time(r.created_at) if r.created_at else now,
            )
            for r in records
        )
        await self._s.flush()
