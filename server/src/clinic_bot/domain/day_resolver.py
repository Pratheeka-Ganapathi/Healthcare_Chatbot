"""Resolve a ``DayToken`` to candidate dates. Pure; the caller supplies ``now``."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from clinic_bot.domain.errors import ErrorCode, InvalidInput
from clinic_bot.domain.values import DayToken


class DayResolver:
    """Turns ``tomorrow`` / ``saturday`` / ``2026-10-09`` into dates inside the window.

    The window is ``today`` through ``today + window_days`` inclusive. Candidates are
    returned in order; the scheduler takes the first one that still has slots. A
    weekday equal to today yields today first, then the same weekday next week.
    ``next_available`` yields every date in the window.
    """

    def resolve(self, token: DayToken, now: datetime, window_days: int) -> tuple[date, ...]:
        today = now.date()
        last = today + timedelta(days=window_days)
        candidates = self._candidates(token, today, window_days)
        in_window = tuple(d for d in candidates if today <= d <= last)
        if not in_window:
            raise InvalidInput(ErrorCode.BAD_DAY, first=today.isoformat(), last=last.isoformat())
        return in_window

    def _candidates(self, token: DayToken, today: date, window_days: int) -> tuple[date, ...]:
        if token.value == "today":
            return (today,)
        if token.value == "tomorrow":
            return (today + timedelta(days=1),)
        if token.value == "day_after_tomorrow":
            return (today + timedelta(days=2),)
        if token.value == "next_available":
            return tuple(today + timedelta(days=i) for i in range(window_days + 1))
        if token.is_iso:
            return (date.fromisoformat(token.value),)
        ahead = (token.weekday_index - today.weekday()) % 7
        first = today + timedelta(days=ahead)
        return (first, first + timedelta(days=7)) if ahead == 0 else (first,)
