"""greet: fixed greeting with an options menu, then find out what the patient wants."""

from __future__ import annotations

from typing import TYPE_CHECKING

from clinic_bot.conversation.nodes.base import BaseNode
from clinic_bot.conversation.result import Menu

if TYPE_CHECKING:
    from clinic_bot.conversation.registry import HandlerContext
    from clinic_bot.conversation.state import FlowState


class GreetNode(BaseNode):
    name = "greet"
    functions = ("route_intent",)

    async def on_enter(self, ctx: HandlerContext) -> None:
        await ctx.io.say(self._messages.get("greet"))
        await ctx.io.ui(Menu.start(self._messages))

    def respond_immediately(self, state: FlowState) -> bool:
        return False

    def task(self, state: FlowState) -> str:
        return (
            "You have already greeted the patient. Find out whether they want to book an "
            "appointment, cancel an appointment, or ask a question about the clinic. As soon as "
            "you know, call route_intent with the intent. If they mention a health complaint, pass "
            "it word for word as complaint. Do not ask for their phone number or date of birth "
            "here."
        )
