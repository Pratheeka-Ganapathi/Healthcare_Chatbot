"""booked: confirmation + prep instructions, then behaves like the router."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipecat.flows import ContextStrategyConfig

from clinic_bot.conversation.nodes.base import RESET_WITH_SUMMARY, BaseNode, patient_line
from clinic_bot.conversation.nodes.router import ROUTER_TASK

if TYPE_CHECKING:
    from clinic_bot.conversation.registry import HandlerContext
    from clinic_bot.conversation.state import FlowState


class BookedNode(BaseNode):
    name = "booked"
    functions = ("route_intent", "reschedule_appointment")

    async def prepare(self, ctx: HandlerContext) -> None:
        quote = ctx.state.quote
        if quote is not None:
            prep = await ctx.services.faq.prep_for(quote.doctor.specialty.label)
            ctx.state.notice_data["prep"] = prep or ""

    async def on_enter(self, ctx: HandlerContext) -> None:
        notice, data = ctx.state.take_notice()
        if notice == "booked":
            parts = [
                self._messages.get(
                    "booked.text", doctor=data["doctor"], date=data["date"], time=data["time"]
                )
            ]
            if data.get("prep"):
                parts.append(self._messages.get("booked.prep", prep=data["prep"]))
            parts.append(self._messages.get("booked.anything_else"))
            await ctx.io.say(" ".join(parts))
        ctx.state.reset_booking()

    def respond_immediately(self, state: FlowState) -> bool:
        return False

    def context_strategy(self, state: FlowState) -> ContextStrategyConfig | None:
        return RESET_WITH_SUMMARY

    def task(self, state: FlowState) -> str:
        return (
            f"{patient_line(state)}\nThe appointment is booked and the patient was asked if there "
            f"is anything else.\n{ROUTER_TASK}"
        )
