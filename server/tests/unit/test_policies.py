from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from clinic_bot.adapters.clock import IST
from clinic_bot.domain.entities import Appointment, Doctor, FollowupGrant, Slot
from clinic_bot.domain.enums import Specialty, VisitType
from clinic_bot.domain.errors import BookingRejected, CutoffViolation, ErrorCode
from clinic_bot.domain.policies import (
    BookingPolicy,
    CancellationPolicy,
    FeePolicy,
    LockoutPolicy,
    SpecialtyRules,
)
from clinic_bot.domain.values import Money, TimeWindow

T0 = datetime(2026, 10, 7, 17, 0, tzinfo=IST)


def slot(slot_id: int, doctor_id: int, start: datetime) -> Slot:
    return Slot(slot_id, doctor_id, TimeWindow(start, start + timedelta(minutes=15)))


def appt(s: Slot) -> Appointment:
    return Appointment.book(1, s, VisitType.NEW, Money.rupees(600), None)


DOCTOR = Doctor(
    1, "Dr. Rao", Specialty.GENERAL_MEDICINE, "", (0,), "", Money.rupees(600), Money.rupees(300)
)


def test_cap_reached() -> None:
    upcoming = [appt(slot(i, 10 + i, T0 + timedelta(days=i))) for i in range(3)]
    with pytest.raises(BookingRejected) as exc:
        BookingPolicy(max_upcoming=3).check(slot(9, 99, T0 + timedelta(days=5)), upcoming)
    assert exc.value.code is ErrorCode.CAP_REACHED


def test_duplicate_same_doctor_same_day() -> None:
    with pytest.raises(BookingRejected) as exc:
        BookingPolicy().check(slot(2, 1, T0 + timedelta(hours=1)), [appt(slot(1, 1, T0))])
    assert exc.value.code is ErrorCode.DUPLICATE_SAME_DAY


def test_overlap_across_doctors() -> None:
    with pytest.raises(BookingRejected) as exc:
        BookingPolicy().check(slot(2, 2, T0 + timedelta(minutes=5)), [appt(slot(1, 1, T0))])
    assert exc.value.code is ErrorCode.OVERLAP


def test_different_doctor_same_day_without_overlap_is_fine() -> None:
    BookingPolicy().check(slot(2, 2, T0 + timedelta(minutes=15)), [appt(slot(1, 1, T0))])


def test_followup_fee_needs_grant_and_same_issue() -> None:
    grant = FollowupGrant(1, 1, 1, None, date(2026, 10, 20), "Dr. Rao")
    fees = FeePolicy()
    assert fees.price(DOCTOR, grant, True) == (VisitType.FOLLOWUP, Money.rupees(300))
    assert fees.price(DOCTOR, grant, False) == (VisitType.NEW, Money.rupees(600))
    assert fees.price(DOCTOR, grant, None) == (VisitType.NEW, Money.rupees(600))
    assert fees.price(DOCTOR, None, True) == (VisitType.NEW, Money.rupees(600))


def test_cancellation_cutoff_is_two_hours() -> None:
    policy = CancellationPolicy()
    policy.ensure_cancellable(T0, T0 - timedelta(hours=2))
    with pytest.raises(CutoffViolation):
        policy.ensure_cancellable(T0, T0 - timedelta(hours=1, minutes=59))


def test_lockout_after_five_failures_for_fifteen_minutes() -> None:
    lockout = LockoutPolicy()
    fails = [T0 + timedelta(minutes=i) for i in range(5)]
    assert not lockout.is_locked(fails[:4], T0 + timedelta(minutes=4))
    assert lockout.is_locked(fails, T0 + timedelta(minutes=5))
    assert lockout.is_locked(fails, T0 + timedelta(minutes=18))
    assert not lockout.is_locked(fails, T0 + timedelta(minutes=19, seconds=1))


def test_spread_out_failures_do_not_lock() -> None:
    fails = [T0 + timedelta(minutes=5 * i) for i in range(5)]  # 20 minutes apart end to end
    assert not LockoutPolicy().is_locked(fails, T0 + timedelta(minutes=21))


def test_adults_never_go_to_paediatrics() -> None:
    rules = SpecialtyRules()
    assert rules.adjust(Specialty.PAEDIATRICS, 18) is Specialty.GENERAL_MEDICINE
    assert rules.adjust(Specialty.PAEDIATRICS, 17) is Specialty.PAEDIATRICS
    assert rules.adjust(Specialty.GYNAECOLOGY, 40) is Specialty.GYNAECOLOGY
