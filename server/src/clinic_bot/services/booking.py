"""Booking use cases: quote, confirm, list upcoming, cancel."""

from __future__ import annotations

from dataclasses import dataclass

from clinic_bot.domain.entities import Appointment, Doctor, FollowupGrant, IntakeSummary, Slot
from clinic_bot.domain.enums import VisitType
from clinic_bot.domain.errors import ErrorCode, NotFound
from clinic_bot.domain.policies import BookingPolicy, CancellationPolicy, FeePolicy
from clinic_bot.domain.values import Money
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.unit_of_work import UnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class ConfirmBooking:
    session_id: str
    patient_id: int
    slot_id: int
    intake: IntakeSummary | None
    same_issue: bool | None


@dataclass(frozen=True, slots=True)
class CancelAppointment:
    patient_id: int
    appointment_id: int


@dataclass(frozen=True, slots=True)
class Quote:
    doctor: Doctor
    slot: Slot
    visit_type: VisitType
    fee: Money


class BookingService:
    def __init__(
        self,
        uow: UnitOfWorkFactory,
        clock: Clock,
        booking: BookingPolicy,
        fees: FeePolicy,
        cancellation: CancellationPolicy,
    ) -> None:
        self._uow, self._clock = uow, clock
        self._booking, self._fees, self._cancellation = booking, fees, cancellation

    async def quote(self, patient_id: int, slot_id: int, same_issue: bool | None) -> Quote:
        """Read-only price for the read-back. Fee comes only from the doctors table."""
        async with self._uow() as uow:
            slot = await uow.slots.require(slot_id)
            doctor = await uow.doctors.require(slot.doctor_id)
            grant = await uow.followups.active(patient_id, doctor.id, self._clock.today())
        visit_type, fee = self._fees.price(doctor, grant, same_issue)
        return Quote(doctor, slot, visit_type, fee)

    async def active_grant(self, patient_id: int, doctor_id: int) -> FollowupGrant | None:
        """The follow-up grant a doctor gave this patient, if still valid and unused."""
        async with self._uow() as uow:
            return await uow.followups.active(patient_id, doctor_id, self._clock.today())

    async def confirm(self, cmd: ConfirmBooking) -> Appointment:
        """Book the slot. Idempotent on ``(session_id, slot_id)``.

        Raises ``BookingRejected`` (CAP_REACHED, DUPLICATE_SAME_DAY, OVERLAP) or ``SlotTaken``.
        """
        async with self._uow(write=True) as uow:
            if existing := await uow.appointments.by_session_slot(cmd.session_id, cmd.slot_id):
                return existing
            slot = await uow.slots.require(cmd.slot_id)
            upcoming = await uow.appointments.upcoming_for_patient(
                cmd.patient_id, self._clock.now()
            )
            self._booking.check(slot, upcoming)
            doctor = await uow.doctors.require(slot.doctor_id)
            grant = await uow.followups.active(cmd.patient_id, doctor.id, self._clock.today())
            visit_type, fee = self._fees.price(doctor, grant, cmd.same_issue)
            grant_id = grant.id if grant and visit_type is VisitType.FOLLOWUP else None
            appt = await uow.appointments.add(
                Appointment.book(cmd.patient_id, slot, visit_type, fee, cmd.intake, grant_id),
                cmd.session_id,
            )
            if grant is not None and grant_id is not None and appt.id is not None:
                grant.mark_used(appt.id)
                await uow.followups.save(grant)
            await uow.commit()
            return appt

    async def upcoming(self, patient_id: int) -> list[Appointment]:
        async with self._uow() as uow:
            return await uow.appointments.upcoming_for_patient(patient_id, self._clock.now())

    async def cancel(self, cmd: CancelAppointment) -> Appointment:
        """Raises ``NotFound``, ``NotOwner`` or ``CutoffViolation``."""
        async with self._uow(write=True) as uow:
            appt = await uow.appointments.get(cmd.appointment_id)
            if appt is None:
                raise NotFound(ErrorCode.NOT_FOUND)
            appt.ensure_owner(cmd.patient_id)
            appt.cancel(self._clock.now(), self._cancellation)
            await uow.appointments.save(appt)
            await uow.commit()
            return appt
