"""confirm: fixed read-back from state, then a no-argument confirm_booking()."""

from __future__ import annotations

from typing import TYPE_CHECKING

from clinic_bot.conversation.nodes.base import BaseNode
from clinic_bot.conversation.views import visit_type_label
from clinic_bot.services.scheduling import day_label, time_label

if TYPE_CHECKING:
    from clinic_bot.conversation.registry import HandlerContext
    from clinic_bot.conversation.state import FlowState


class ConfirmNode(BaseNode):
    name = "confirm"
    functions = ("confirm_booking", "change_time", "change_doctor", "route_intent")

    async def prepare(self, ctx: HandlerContext) -> None:
        state = ctx.state
        state.quote = await ctx.services.booking.quote(
            state.require_verified(), state.require_selected_slot(), state.same_issue
        )

    async def on_enter(self, ctx: HandlerContext) -> None:
        quote = ctx.state.quote
        if quote is None:
            return
        await ctx.io.say(
            self._messages.get(
                "confirm.readback",
                doctor=quote.doctor.name,
                specialty=quote.doctor.specialty.label,
                date=day_label(quote.slot.day),
                time=time_label(quote.slot),
                visit_type=visit_type_label(quote.visit_type, self._messages),
            )
        )

    def respond_immediately(self, state: FlowState) -> bool:
        return False

    def task(self, state: FlowState) -> str:
        return (
            "The booking details have been read back to the patient. If they confirm, call "
            "confirm_booking. If they want a different time, call change_time. If they want a "
            "different doctor, call change_doctor. If confirm_booking is refused because they "
            "already have a booking with this doctor that day, an overlapping booking, or the "
            "limit of three upcoming bookings, explain that simply and offer to cancel an existing "
            "appointment; if they agree, call route_intent with intent cancel."
        )
