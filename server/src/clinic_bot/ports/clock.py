"""Clock port. All time in the system comes from here."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Timezone-aware current time in Asia/Kolkata."""
        ...

    def today(self) -> date: ...
