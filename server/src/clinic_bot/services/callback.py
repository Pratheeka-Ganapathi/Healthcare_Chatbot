"""Human handoff: create a callback ticket for the front desk."""

from __future__ import annotations

from clinic_bot.domain.entities import Callback
from clinic_bot.domain.enums import CallbackPriority
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.unit_of_work import UnitOfWorkFactory


class CallbackService:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def create(
        self, patient_id: int | None, reason: str, summary: str, priority: CallbackPriority
    ) -> Callback:
        """Persist a callback request and return it with its ticket id."""
        callback = Callback(None, patient_id, reason, summary, priority, self._clock.now())
        async with self._uow(write=True) as uow:
            saved = await uow.callbacks.add(callback)
            await uow.commit()
        return saved
