"""Free slots and alternatives. Dates are resolved here, never by the LLM."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from clinic_bot.domain.day_resolver import DayResolver
from clinic_bot.domain.entities import Slot
from clinic_bot.domain.enums import TimePref
from clinic_bot.domain.errors import ErrorCode, NotFound
from clinic_bot.domain.policies import SlotTimingPolicy
from clinic_bot.domain.values import DayToken
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from clinic_bot.services.directory import DoctorDirectory

MAX_OFFERED = 3


def day_label(d: date) -> str:
    """``Tue 7 Oct``"""
    return f"{d:%a} {d.day} {d:%b}"


def time_label(slot: Slot) -> str:
    """``6:15 PM``"""
    return slot.start.strftime("%I:%M %p").lstrip("0")


@dataclass(frozen=True, slots=True)
class SlotOffer:
    doctor_id: int
    resolved_date: date
    slots: tuple[Slot, ...]

    @property
    def label(self) -> str:
        return day_label(self.resolved_date)


class SchedulingService:
    def __init__(
        self,
        uow: UnitOfWorkFactory,
        clock: Clock,
        resolver: DayResolver,
        timing: SlotTimingPolicy,
        directory: DoctorDirectory,
    ) -> None:
        self._uow, self._clock, self._resolver = uow, clock, resolver
        self._timing, self._directory = timing, directory

    async def free_slots(self, doctor_id: int, day: str, time_pref: TimePref) -> SlotOffer:
        """Up to three free slots on the first matching day.

        Raises ``InvalidInput(BAD_DAY)``, ``NotFound(CLOSED)`` or ``NotFound(NO_SLOTS)``.
        """
        now = self._clock.now()
        dates = self._resolver.resolve(DayToken.parse(day), now, self._timing.window_days)
        closed_reason: str | None = None
        async with self._uow() as uow:
            for d in dates:
                closure = await uow.closures.on(d)
                if closure is not None:
                    closed_reason = closed_reason or closure.reason
                    continue
                slots = await self._free(uow, doctor_id, d, time_pref)
                if slots:
                    return SlotOffer(doctor_id, d, slots)
        if closed_reason is not None and len(dates) == 1:
            raise NotFound(ErrorCode.CLOSED, reason=closed_reason, date=day_label(dates[0]))
        raise NotFound(ErrorCode.NO_SLOTS, date=day_label(dates[0]))

    async def alternatives(self, doctor_id: int, day: str, time_pref: TimePref) -> list[SlotOffer]:
        """Same doctor on the next two available days, then same-specialty doctors on ``day``.

        Raises ``NotFound(NONE)`` when nothing is free.
        """
        now = self._clock.now()
        window = self._resolver.resolve(
            DayToken.parse("next_available"), now, self._timing.window_days
        )
        requested = self._resolver.resolve(DayToken.parse(day), now, self._timing.window_days)[0]
        doctor = self._directory.get(doctor_id)
        offers: list[SlotOffer] = []
        async with self._uow() as uow:
            for d in (d for d in window if d > requested):
                if len(offers) == 2:
                    break
                if await uow.closures.on(d) is None and (
                    slots := await self._free(uow, doctor_id, d, time_pref)
                ):
                    offers.append(SlotOffer(doctor_id, d, slots))
            if await uow.closures.on(requested) is None:
                for other in self._directory.in_specialty(doctor.specialty):
                    if other.id != doctor_id and (
                        slots := await self._free(uow, other.id, requested, time_pref)
                    ):
                        offers.append(SlotOffer(other.id, requested, slots))
        if not offers:
            raise NotFound(ErrorCode.NONE)
        return offers

    async def _free(
        self, uow: UnitOfWork, doctor_id: int, d: date, time_pref: TimePref
    ) -> tuple[Slot, ...]:
        not_before = self._timing.earliest_start(self._clock.now())
        return tuple(await uow.slots.free(doctor_id, d, time_pref, not_before, MAX_OFFERED))
