from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from clinic_bot.adapters.clock import IST
from clinic_bot.domain.day_resolver import DayResolver
from clinic_bot.domain.errors import ErrorCode, InvalidInput
from clinic_bot.domain.values import (
    DateOfBirth,
    DayToken,
    Money,
    PersonName,
    PhoneNumber,
    TimeWindow,
)

TODAY = date(2026, 10, 6)  # Tuesday
NOW = datetime(2026, 10, 6, 10, 0, tzinfo=IST)


@pytest.mark.parametrize("raw", ["9876543210", "+91 98765 43210", "098765-43210", "91 9876543210"])
def test_phone_normalises(raw: str) -> None:
    assert PhoneNumber.parse(raw).digits == "9876543210"


@pytest.mark.parametrize("raw", ["12345", "5876543210", "abc", "+1 415 555 0100"])
def test_phone_rejects(raw: str) -> None:
    with pytest.raises(InvalidInput) as exc:
        PhoneNumber.parse(raw)
    assert exc.value.code is ErrorCode.BAD_PHONE


def test_phone_masks_all_but_last_four() -> None:
    assert PhoneNumber.parse("9876543210").masked() == "******3210"


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Priya Sharma", "Priya Sharma"),
        ("  priya   sharma ", "priya sharma"),
        ("Anne-Marie D'Souza", "Anne-Marie D'Souza"),
        ("K. Ramesh", "K. Ramesh"),
        ("रमेश कुमार", "रमेश कुमार"),
    ],
)
def test_person_name_accepts(raw: str, clean: str) -> None:
    assert PersonName.parse(raw).value == clean


@pytest.mark.parametrize("raw", ["", "A", "Ravi 2", "<b>Ravi</b>", "Ravi_K", "x" * 81, "--"])
def test_person_name_rejects(raw: str) -> None:
    with pytest.raises(InvalidInput) as exc:
        PersonName.parse(raw)
    assert exc.value.code is ErrorCode.BAD_NAME


def test_person_name_compares_ignoring_case_and_spacing() -> None:
    assert PersonName.parse("sanjay joshi").same_as("Sanjay  Joshi")
    assert not PersonName.parse("Sanjay").same_as("Sanjay Joshi")


@pytest.mark.parametrize(
    "raw", ["05/06/1990", "5 June 1990", "5-6-90", "1990-06-05", "5th June 1990"]
)
def test_dob_is_day_first(raw: str) -> None:
    assert DateOfBirth.parse(raw, TODAY).value == date(1990, 6, 5)


@pytest.mark.parametrize("raw", ["yesterday", "31/02/1990", "5/6/2030", "hello"])
def test_dob_rejects(raw: str) -> None:
    with pytest.raises(InvalidInput):
        DateOfBirth.parse(raw, TODAY)


def test_age() -> None:
    assert DateOfBirth(date(2012, 8, 30)).age_on(TODAY) == 14
    assert DateOfBirth(date(1990, 10, 7)).age_on(TODAY) == 35


def test_money_is_integer_paise() -> None:
    assert Money.rupees(600).paise == 60000
    assert Money(60050).display() == "₹600.50"
    assert Money.rupees(1200).display() == "₹1,200"
    with pytest.raises(ValueError):
        Money(-1)


def test_time_window_overlap() -> None:
    a = TimeWindow(NOW, NOW + timedelta(minutes=15))
    assert a.overlaps(TimeWindow(NOW + timedelta(minutes=10), NOW + timedelta(minutes=25)))
    assert not a.overlaps(TimeWindow(NOW + timedelta(minutes=15), NOW + timedelta(minutes=30)))


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("today", (date(2026, 10, 6),)),
        ("tomorrow", (date(2026, 10, 7),)),
        ("day after tomorrow", (date(2026, 10, 8),)),
        ("Saturday", (date(2026, 10, 10),)),
        ("tuesday", (date(2026, 10, 6), date(2026, 10, 13))),
        ("2026-10-12", (date(2026, 10, 12),)),
    ],
)
def test_day_resolver(token: str, expected: tuple[date, ...]) -> None:
    assert DayResolver().resolve(DayToken.parse(token), NOW, 7) == expected


@pytest.mark.parametrize("token", ["2026-10-20", "2026-10-01"])
def test_day_resolver_outside_window(token: str) -> None:
    with pytest.raises(InvalidInput) as exc:
        DayResolver().resolve(DayToken.parse(token), NOW, 7)
    assert exc.value.code is ErrorCode.BAD_DAY
    assert exc.value.data == {"first": "2026-10-06", "last": "2026-10-13"}


@pytest.mark.parametrize("token", ["next week", "2026-02-31", "someday"])
def test_day_token_rejects(token: str) -> None:
    with pytest.raises(InvalidInput):
        DayToken.parse(token)
