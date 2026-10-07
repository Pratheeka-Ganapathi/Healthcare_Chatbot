"""Clock adapters."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(IST)  # the only real-time read in the codebase

    def today(self) -> date:
        return self.now().date()


class FrozenClock:
    """Fixed time for tests and golden runs (``CLINIC_NOW``)."""

    def __init__(self, at: datetime) -> None:
        self._now = at if at.tzinfo else at.replace(tzinfo=IST)
        self._now = self._now.astimezone(IST)

    def now(self) -> datetime:
        return self._now

    def today(self) -> date:
        return self._now.date()

    def advance(self, delta: timedelta) -> None:
        self._now += delta
