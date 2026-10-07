"""What a doctor writes after a visit: outcome, visit details, consultation, follow-up
(SPEC 17.2). Ticking follow-up creates the grant the chatbot reads (SPEC 4.7)."""

from __future__ import annotations

from clinic_bot.domain.entities import Appointment
from clinic_bot.domain.enums import AppointmentStatus, StaffRole
from clinic_bot.domain.errors import ErrorCode, Forbidden
from clinic_bot.domain.staff import Consultation, ConsultationNote, StaffUser
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from clinic_bot.services.directory import DoctorDirectory
from clinic_bot.services.staff.records import owned_appointment


def _doctor_id(user: StaffUser) -> int:
    if user.role is not StaffRole.DOCTOR or user.doctor_id is None or user.id is None:
        raise Forbidden(ErrorCode.FORBIDDEN)
    return user.doctor_id


class ConsultationService:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock, directory: DoctorDirectory) -> None:
        self._uow, self._clock, self._directory = uow, clock, directory

    async def update_visit(
        self,
        user: StaffUser,
        appointment_id: int,
        *,
        status: AppointmentStatus | None = None,
        chief_complaint: str | None = None,
        duration: str | None = None,
        severity: int | None = None,
    ) -> None:
        """Outcome and/or visit details. ``chief_complaint`` None leaves the details alone.

        Raises ``Forbidden``, ``NotFound``, ``Conflict(NOT_RECORDABLE)``, ``InvalidInput``,
        ``SlotTaken`` (back to booked while another booking holds the slot)."""
        doctor_id, today = _doctor_id(user), self._clock.today()
        async with self._uow(write=True) as uow:
            appt = await owned_appointment(uow, appointment_id, doctor_id)
            if chief_complaint is not None:
                appt.revise_intake(chief_complaint, duration, severity, today)
            if status is not None:
                appt.record_outcome(status, today)
            await uow.appointments.save(appt)
            await uow.commit()

    async def submit(self, user: StaffUser, appointment_id: int, note: ConsultationNote) -> None:
        """Save (or replace) the consultation and mark the visit completed.

        Raises ``Forbidden``, ``NotFound``, ``Conflict(NOT_RECORDABLE)``."""
        doctor_id, now = _doctor_id(user), self._clock.now()
        assert user.id is not None
        async with self._uow(write=True) as uow:
            appt = await owned_appointment(uow, appointment_id, doctor_id)
            appt.ensure_recordable(now.date())
            existing = await uow.consultations.for_appointment(appointment_id)
            grant_id = await self._sync_grant(
                uow, appt, note, existing.followup_grant_id if existing else None
            )
            if existing is None:
                await uow.consultations.add(
                    Consultation(
                        id=None,
                        appointment_id=appointment_id,
                        doctor_id=appt.doctor_id,
                        patient_id=appt.patient_id,
                        note=note,
                        followup_grant_id=grant_id,
                        submitted_by=user.id,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                await uow.consultations.save(existing.revised(note, grant_id, user.id, now))
            appt.record_outcome(AppointmentStatus.COMPLETED, now.date())
            await uow.appointments.save(appt)
            await uow.commit()

    async def _sync_grant(
        self, uow: UnitOfWork, appt: Appointment, note: ConsultationNote, grant_id: int | None
    ) -> int | None:
        """Create, move or remove this visit's follow-up grant. A grant the patient has
        already booked with stays as it is."""
        grant = await uow.followups.get(grant_id) if grant_id else None
        if grant is not None and grant.used:
            return grant.id
        until = note.followup_until(appt.slot.day)
        if until is None:
            if grant is not None:
                await uow.followups.delete(grant.id)
            return None
        if grant is None:
            assert appt.id is not None
            doctor = self._directory.get(appt.doctor_id).name
            added = await uow.followups.add(appt.patient_id, appt.doctor_id, appt.id, until, doctor)
            return added.id
        grant.valid_until = until
        await uow.followups.save(grant)
        return grant.id
