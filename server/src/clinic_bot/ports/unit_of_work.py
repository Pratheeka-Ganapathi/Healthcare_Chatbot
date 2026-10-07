"""Unit of Work port: one transaction per use case."""

from __future__ import annotations

from typing import Protocol, Self

from clinic_bot.ports.repositories import (
    AppointmentRepo,
    CallbackRepo,
    ChatSummaryRepo,
    ClosureRepo,
    DoctorRepo,
    FollowupRepo,
    PatientRepo,
    SlotRepo,
    TranscriptRepo,
    VerifyAttemptRepo,
)
from clinic_bot.ports.staff import (
    ClinicDocRepo,
    ConsultationRepo,
    StaffSessionRepo,
    StaffUserRepo,
)


class UnitOfWork(Protocol):
    patients: PatientRepo
    doctors: DoctorRepo
    slots: SlotRepo
    closures: ClosureRepo
    appointments: AppointmentRepo
    followups: FollowupRepo
    verify_attempts: VerifyAttemptRepo
    callbacks: CallbackRepo
    transcripts: TranscriptRepo
    chat_summaries: ChatSummaryRepo
    staff_users: StaffUserRepo
    staff_sessions: StaffSessionRepo
    consultations: ConsultationRepo
    clinic_docs: ClinicDocRepo

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *exc: object) -> None:
        """Roll back if not committed."""
        ...

    async def commit(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self, *, write: bool = False) -> UnitOfWork:
        """``write=True`` takes the write lock up front (one advisory lock for all writers)."""
        ...
