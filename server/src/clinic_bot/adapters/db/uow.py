"""SQLAlchemy Unit of Work: one AsyncSession per use case."""

from __future__ import annotations

from typing import Any, Self

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clinic_bot.adapters.db.engine import take_write_lock
from clinic_bot.adapters.db.record_repositories import (
    SqlCallbackRepo,
    SqlChatSummaryRepo,
    SqlFollowupRepo,
    SqlTranscriptRepo,
    SqlVerifyAttemptRepo,
)
from clinic_bot.adapters.db.repositories import (
    SqlAppointmentRepo,
    SqlClosureRepo,
    SqlDoctorRepo,
    SqlPatientRepo,
    SqlSlotRepo,
)
from clinic_bot.adapters.db.staff_repositories import (
    SqlClinicDocRepo,
    SqlConsultationRepo,
    SqlStaffSessionRepo,
    SqlStaffUserRepo,
)
from clinic_bot.domain.errors import ErrorCode, Unavailable
from clinic_bot.ports.clock import Clock


class SqlUnitOfWork:
    def __init__(
        self, factory: async_sessionmaker[AsyncSession], clock: Clock, *, write: bool
    ) -> None:
        self._factory, self._clock, self._write = factory, clock, write
        self._session: AsyncSession | None = None
        self._committed = False

    async def __aenter__(self) -> Self:
        session = self._factory()
        try:
            await session.connection()
            if self._write:
                await take_write_lock(session)
        except DBAPIError as exc:  # unreachable server, lock timeout
            await session.close()
            raise Unavailable(ErrorCode.BUSY, "database busy") from exc
        self._session = session
        self.patients = SqlPatientRepo(session)
        self.doctors = SqlDoctorRepo(session)
        self.slots = SqlSlotRepo(session)
        self.closures = SqlClosureRepo(session)
        self.appointments = SqlAppointmentRepo(session, self._clock)
        self.followups = SqlFollowupRepo(session)
        self.verify_attempts = SqlVerifyAttemptRepo(session)
        self.callbacks = SqlCallbackRepo(session)
        self.transcripts = SqlTranscriptRepo(session, self._clock)
        self.chat_summaries = SqlChatSummaryRepo(session)
        self.staff_users = SqlStaffUserRepo(session)
        self.staff_sessions = SqlStaffSessionRepo(session)
        self.consultations = SqlConsultationRepo(session)
        self.clinic_docs = SqlClinicDocRepo(session)
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._session is not None
        try:
            if not self._committed:
                await self._session.rollback()
        finally:
            await self._session.close()

    async def commit(self) -> None:
        assert self._session is not None
        try:
            await self._session.commit()
        except IntegrityError:
            raise
        except DBAPIError as exc:
            raise Unavailable(ErrorCode.BUSY, "database busy") from exc
        self._committed = True


class SqlUnitOfWorkFactory:
    def __init__(self, factory: async_sessionmaker[Any], clock: Clock) -> None:
        self._factory, self._clock = factory, clock

    def __call__(self, *, write: bool = False) -> SqlUnitOfWork:
        return SqlUnitOfWork(self._factory, self._clock, write=write)
