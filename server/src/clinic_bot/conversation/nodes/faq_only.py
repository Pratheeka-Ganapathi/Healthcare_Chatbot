"""faq_only: answer clinic questions in a loop; offer booking after each answer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from clinic_bot.conversation.nodes.base import BaseNode

if TYPE_CHECKING:
    from clinic_bot.conversation.state import FlowState


class FaqOnlyNode(BaseNode):
    name = "faq_only"
    functions = ("route_intent",)

    def task(self, state: FlowState) -> str:
        return (
            "Answer the patient's questions about the clinic. For every question, call answer_faq"
            " and answer only from its result in two or three sentences; if it has no answer, a "
            "fixed message is already shown. After each answer, offer to book an appointment. If "
            "they want to book or cancel, call route_intent with that intent and any health "
            "complaint."
        )
