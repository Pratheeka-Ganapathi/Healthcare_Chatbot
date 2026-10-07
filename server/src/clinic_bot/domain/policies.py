"""Business rules. Small stateless classes configured through the constructor."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from clinic_bot.domain.entities import Appointment, Doctor, FollowupGrant, Slot
from clinic_bot.domain.enums import Specialty, VisitType
from clinic_bot.domain.errors import BookingRejected, CutoffViolation, ErrorCode
from clinic_bot.domain.values import Money


class BookingPolicy:
    """Front-desk rules: cap on upcoming visits, one per doctor per day, no overlaps."""

    def __init__(self, max_upcoming: int = 3) -> None:
        self._max_upcoming = max_upcoming

    def check(self, slot: Slot, upcoming: Sequence[Appointment]) -> None:
        """Raise ``BookingRejected`` if ``slot`` breaks a rule against ``upcoming``."""
        if len(upcoming) >= self._max_upcoming:
            raise BookingRejected(ErrorCode.CAP_REACHED)
        for appt in upcoming:
            if appt.doctor_id == slot.doctor_id and appt.slot.day == slot.day:
                raise BookingRejected(ErrorCode.DUPLICATE_SAME_DAY)
            if appt.slot.window.overlaps(slot.window):
                raise BookingRejected(ErrorCode.OVERLAP)


class FeePolicy:
    """Follow-up fee only with an active grant and a same-issue answer of yes."""

    def price(
        self, doctor: Doctor, grant: FollowupGrant | None, same_issue: bool | None
    ) -> tuple[VisitType, Money]:
        if grant is not None and same_issue:
            return VisitType.FOLLOWUP, doctor.followup_fee
        return VisitType.NEW, doctor.fee


class CancellationPolicy:
    """Cancellation must happen at least ``cutoff_hours`` before the slot starts."""

    def __init__(self, cutoff_hours: int = 2) -> None:
        self._cutoff = timedelta(hours=cutoff_hours)

    @property
    def cutoff_hours(self) -> int:
        return int(self._cutoff.total_seconds() // 3600)

    def ensure_cancellable(self, start: datetime, now: datetime) -> None:
        if start - now < self._cutoff:
            raise CutoffViolation(ErrorCode.CUTOFF_VIOLATION, cutoff_hours=self.cutoff_hours)


class LockoutPolicy:
    """Per-phone lockout: ``max_failures`` within ``window`` locks for ``window``.

    The lock starts at the failure that reached the threshold and lasts ``window``.
    Only failures after the most recent success count.
    """

    def __init__(self, max_failures: int = 5, window_minutes: int = 15) -> None:
        self._max = max_failures
        self._window = timedelta(minutes=window_minutes)

    @property
    def lookback(self) -> timedelta:
        return self._window * 2

    def is_locked(self, failures: Sequence[datetime], now: datetime) -> bool:
        times = sorted(failures)
        for i in range(self._max - 1, len(times)):
            trigger = times[i]
            if trigger - times[i - self._max + 1] <= self._window and now < trigger + self._window:
                return True
        return False


class SlotTimingPolicy:
    """Which slots may be offered: not starting within ``min_lead_minutes`` of now."""

    MORNING_END_HOUR = 13
    EVENING_START_HOUR = 16

    def __init__(self, min_lead_minutes: int = 30, window_days: int = 7) -> None:
        self.min_lead = timedelta(minutes=min_lead_minutes)
        self.window_days = window_days

    def earliest_start(self, now: datetime) -> datetime:
        return now + self.min_lead


class SpecialtyRules:
    """The one hard code rule from SPEC 4.6: adults never go to paediatrics."""

    ADULT_AGE = 18

    def adjust(self, specialty: Specialty, age: int) -> Specialty:
        if specialty is Specialty.PAEDIATRICS and age >= self.ADULT_AGE:
            return Specialty.GENERAL_MEDICINE
        return specialty
