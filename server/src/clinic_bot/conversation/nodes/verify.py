"""verify: phone + DOB, or new-patient registration, before any patient data is touched."""

from __future__ import annotations

from typing import TYPE_CHECKING

from clinic_bot.conversation.nodes.base import BaseNode

if TYPE_CHECKING:
    from clinic_bot.conversation.state import FlowState


class VerifyNode(BaseNode):
    name = "verify"
    functions = ("verify_patient", "register_patient")

    def task(self, state: FlowState) -> str:
        why = {
            "book": "book an appointment",
            "cancel": "cancel an appointment",
        }.get(state.initial_intent.value if state.initial_intent else "", "help them")
        return (
            f"The patient wants to {why}. Before that, ask for their registered mobile number and "
            "date of birth in one short message, and mention that new patients can register here. "
            "For a returning patient, call verify_patient when you have both. If the patient says "
            "they are new or have not visited before, collect their full name, mobile number, date "
            "of birth and sex (female, male or other), asking only for what is missing, then call "
            "register_patient. If a tool says the name, phone number or date could not be read, "
            "ask again for just that item. Never repeat the date of birth back. If the details "
            "don't match, a fixed message is already shown; simply let them try again or register. "
            "After registration, welcome them to the clinic by name in one short sentence."
        )
