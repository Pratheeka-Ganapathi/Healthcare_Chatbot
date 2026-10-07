"""pre_talk: acknowledge the complaint, ask up to three checklist questions, submit intake."""

from __future__ import annotations

from typing import TYPE_CHECKING

from clinic_bot.conversation.nodes.base import BaseNode, patient_line
from clinic_bot.services.intake import MAX_FOLLOWUPS

if TYPE_CHECKING:
    from clinic_bot.conversation.registry import HandlerContext
    from clinic_bot.conversation.state import FlowState


class PreTalkNode(BaseNode):
    name = "pre_talk"
    functions = ("submit_intake",)

    async def prepare(self, ctx: HandlerContext) -> None:
        ctx.state.checklist = await ctx.services.checklists.for_complaint(ctx.state.initial_message)

    def task(self, state: FlowState) -> str:
        checklist = state.checklist
        questions = "; ".join(checklist.questions) if checklist else ""
        flags = "; ".join(checklist.red_flags) if checklist else ""
        opening = (
            f'The patient already said: "{state.initial_message}". Acknowledge it briefly; do not '
            "ask what brings them in again."
            if state.initial_message
            else "Ask briefly what brings them in today."
        )
        return (
            f"{patient_line(state)}\n{opening}\n"
            f"Then ask at most {MAX_FOLLOWUPS} short follow-up questions, one at a time, choosing "
            f"the most useful from this checklist: {questions}. You may ask about these warning "
            f"signs: {flags}. Skip questions already answered.\n"
            "If the patient asks what condition they have, reply exactly: "
            f'"{self._messages.get("diagnosis.refusal")}" and continue.\n'
            "When done, call submit_intake with the chief complaint, duration, severity (1-10) if "
            "given, each question and answer, and the warning signs you asked about. Do not "
            "suggest a doctor or specialty yourself."
        )
