"""handoff: terminal; front desk number and callback ticket."""

from __future__ import annotations

from typing import TYPE_CHECKING

from clinic_bot.conversation.nodes.base import BaseNode
from clinic_bot.conversation.result import HandoffCard

if TYPE_CHECKING:
    from clinic_bot.conversation.registry import HandlerContext
    from clinic_bot.conversation.state import FlowState


class HandoffNode(BaseNode):
    name = "handoff"
    include_globals = False

    async def on_enter(self, ctx: HandlerContext) -> None:
        ticket = ctx.state.handoff_ticket
        if ticket:
            await ctx.io.say(self._messages.get("handoff.text", ticket=ticket))
        else:
            await ctx.io.say(self._messages.get("handoff.no_ticket"))
        await ctx.io.ui(
            HandoffCard(desk_number=self._messages.get("handoff.desk_number"), ticket_id=ticket)
        )

    def respond_immediately(self, state: FlowState) -> bool:
        return False

    def task(self, state: FlowState) -> str:
        return "The patient has been handed to the front desk. Do not respond."
