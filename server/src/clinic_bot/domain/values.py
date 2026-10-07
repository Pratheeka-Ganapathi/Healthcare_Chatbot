"""Immutable value objects. Each validates once, at construction."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

import dateparser

from clinic_bot.domain.errors import ErrorCode, InvalidInput

_NON_DIGIT = re.compile(r"\D")
_INDIAN_MOBILE = re.compile(r"[6-9]\d{9}")
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_RELATIVE = ("today", "tomorrow", "day_after_tomorrow", "next_available")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NAME_PUNCTUATION = frozenset(" .'-")
_DOB_SETTINGS = {
    "DATE_ORDER": "DMY",
    "PREFER_DATES_FROM": "past",
    "STRICT_PARSING": True,
    "TIMEZONE": "Asia/Kolkata",
    "RETURN_AS_TIMEZONE_AWARE": False,
    "PARSERS": ["custom-formats", "absolute-time"],
}


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    digits: str

    @classmethod
    def parse(cls, raw: str) -> PhoneNumber:
        d = _NON_DIGIT.sub("", raw)
        if len(d) == 12 and d.startswith("91"):
            d = d[2:]
        elif len(d) == 11 and d.startswith("0"):
            d = d[1:]
        if not _INDIAN_MOBILE.fullmatch(d):
            raise InvalidInput(ErrorCode.BAD_PHONE)
        return cls(d)

    def masked(self) -> str:
        return f"******{self.digits[-4:]}"


@dataclass(frozen=True, slots=True)
class PersonName:
    value: str

    @classmethod
    def parse(cls, raw: str) -> PersonName:
        """Letters and marks in any script, plus space . ' -; 2 to 80 chars."""
        text = " ".join(raw.split())
        if not 2 <= len(text) <= 80 or not text[0].isalpha():
            raise InvalidInput(ErrorCode.BAD_NAME)
        if not all(c in _NAME_PUNCTUATION or unicodedata.category(c)[0] in "LM" for c in text):
            raise InvalidInput(ErrorCode.BAD_NAME)
        return cls(text)

    def same_as(self, other: str) -> bool:
        return self.value.casefold() == " ".join(other.split()).casefold()


@dataclass(frozen=True, slots=True)
class DateOfBirth:
    value: date

    @classmethod
    def parse(cls, raw: str, today: date) -> DateOfBirth:
        """Parse day-first (05/06/1990, 5 June 1990, 5-6-90). Rejects future dates."""
        text = raw.strip()
        if _ISO_DATE.fullmatch(text):
            try:
                value = date.fromisoformat(text)
            except ValueError as exc:
                raise InvalidInput(ErrorCode.BAD_DOB) from exc
        else:
            parsed = dateparser.parse(text, languages=["en"], settings=_DOB_SETTINGS)
            if parsed is None:
                raise InvalidInput(ErrorCode.BAD_DOB)
            value = parsed.date()
        if value > today or value.year < 1900:
            raise InvalidInput(ErrorCode.BAD_DOB)
        return cls(value)

    def age_on(self, today: date) -> int:
        had_birthday = (today.month, today.day) >= (self.value.month, self.value.day)
        return today.year - self.value.year - (0 if had_birthday else 1)


@dataclass(frozen=True, slots=True, order=True)
class Money:
    paise: int

    def __post_init__(self) -> None:
        if self.paise < 0:
            raise ValueError("Money cannot be negative")

    @classmethod
    def rupees(cls, amount: int) -> Money:
        return cls(amount * 100)

    def display(self) -> str:
        rupees, paise = divmod(self.paise, 100)
        return f"₹{rupees:,}" if paise == 0 else f"₹{rupees:,}.{paise:02d}"


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("TimeWindow end must be after start")

    def overlaps(self, other: TimeWindow) -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True, slots=True)
class DayToken:
    """A day as the LLM passes it. Resolved to a date only by ``DayResolver``."""

    value: str

    @classmethod
    def parse(cls, raw: str) -> DayToken:
        token = raw.strip().lower().replace("-", "_").replace(" ", "_")
        if _ISO_DATE.fullmatch(raw.strip()):
            try:
                date.fromisoformat(raw.strip())
            except ValueError as exc:
                raise InvalidInput(ErrorCode.BAD_DAY) from exc
            return cls(raw.strip())
        if token in _RELATIVE or token in _WEEKDAYS:
            return cls(token)
        raise InvalidInput(ErrorCode.BAD_DAY)

    @property
    def is_weekday(self) -> bool:
        return self.value in _WEEKDAYS

    @property
    def weekday_index(self) -> int:
        return _WEEKDAYS.index(self.value)

    @property
    def is_iso(self) -> bool:
        return bool(_ISO_DATE.fullmatch(self.value))
