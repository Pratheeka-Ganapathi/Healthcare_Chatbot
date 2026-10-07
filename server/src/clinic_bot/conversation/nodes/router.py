"""router: "How can I help?" between tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipecat.flows import ContextStrategyConfig

from clinic_bot.conversation.nodes.base import RESET_WITH_SUMMARY, BaseNode, patient_line

if TYPE_CHECKING:
    from clinic_bot.conversation.registry import HandlerContext
    from clinic_bot.conversation.state import FlowState

ROUTER_TASK = (
    "Ask how you can help, unless you just asked. When the patient says what they want, call "
    "route_intent: book for a new appointment (pass any health complaint as complaint), cancel to "
    "cancel one, faq for clinic questions. If they ask to reschedule, call reschedule_appointment."
)


class RouterNode(BaseNode):
    name = "router"
    functions = ("route_intent", "reschedule_appointment")

    async def on_enter(self, ctx: HandlerContext) -> None:
        notice, data = ctx.state.take_notice()
        if notice == "cancelled":
            await ctx.io.say(self._messages.get("cancel.done", **data))

    def respond_immediately(self, state: FlowState) -> bool:
        return state.notice != "cancelled"

    def context_strategy(self, state: FlowState) -> ContextStrategyConfig | None:
        return RESET_WITH_SUMMARY if state.notice == "cancelled" else None

    def task(self, state: FlowState) -> str:
        return f"{patient_line(state)}\n{ROUTER_TASK}"
