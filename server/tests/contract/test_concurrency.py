"""Two sessions confirm the same slot at once on real PostgreSQL: exactly one wins."""

from __future__ import annotations

import asyncio
from datetime import date

from clinic_bot.adapters.clock import FrozenClock
from clinic_bot.domain.enums import TimePref
from clinic_bot.domain.errors import SlotTaken
from clinic_bot.domain.policies import BookingPolicy, CancellationPolicy, FeePolicy
from clinic_bot.services.booking import BookingService, ConfirmBooking
from tests.fakes.data import seeded_sql


async def test_concurrent_confirm_single_winner(clock: FrozenClock) -> None:
    uow = await seeded_sql(clock)
    async with uow() as u:
        [slot] = await u.slots.free(3, date(2026, 10, 8), TimePref.ANY, clock.now(), 1)
    service = BookingService(uow, clock, BookingPolicy(), FeePolicy(), CancellationPolicy())
    results = await asyncio.gather(
        service.confirm(ConfirmBooking("tab-1", 5, slot.id, None, None)),
        service.confirm(ConfirmBooking("tab-2", 1, slot.id, None, None)),
        return_exceptions=True,
    )
    winners = [r for r in results if not isinstance(r, BaseException)]
    losers = [r for r in results if isinstance(r, SlotTaken)]
    assert len(winners) == 1 and len(losers) == 1
