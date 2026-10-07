"""pick_slot: day + morning/evening → free slots → select one."""

from __future__ import annotations

from typing import TYPE_CHECKING

from clinic_bot.conversation.nodes.base import BaseNode, patient_line
from clinic_bot.conversation.views import doctor_line

if TYPE_CHECKING:
    from clinic_bot.conversation.prompts import PromptLibrary
    from clinic_bot.conversation.registry import FunctionRegistry, HandlerContext
    from clinic_bot.conversation.state import FlowState
    from clinic_bot.ports.messages import MessageCatalog
    from clinic_bot.services.directory import DoctorDirectory

SLOT_TASK = (
    "Ask which day suits them and whether they prefer morning or evening, unless they already "
    "said. Then call get_free_slots with day as a token: today, tomorrow, day_after_tomorrow, a "
    "weekday name such as saturday, a date as YYYY-MM-DD, or next_available; and time_pref as "
    "morning, evening or any. Never work out dates yourself; use the date label the tool returns. "
    "Offer the returned times briefly; the buttons show them. If there are no slots, call "
    "find_alternatives and offer those. If the clinic is closed that day, give the reason and ask "
    "for another day. When the patient picks a time, call select_slot with the matching slot_id."
)


class PickSlotNode(BaseNode):
    name = "pick_slot"
    functions = ("get_free_slots", "find_alternatives", "select_slot")

    def __init__(
        self,
        prompts: PromptLibrary,
        registry: FunctionRegistry,
        messages: MessageCatalog,
        directory: DoctorDirectory,
    ) -> None:
        super().__init__(prompts, registry, messages)
        self._directory = directory

    async def on_enter(self, ctx: HandlerContext) -> None:
        if ctx.state.notice == "slot_taken":
            ctx.state.take_notice()

    def task(self, state: FlowState) -> str:
        doctor = (
            doctor_line(self._directory.get(state.selected_doctor_id))
            if state.selected_doctor_id
            else "not chosen"
        )
        lines = [patient_line(state), f"Chosen doctor: {doctor}.", SLOT_TASK]
        if state.notice == "slot_taken":
            lines.append(
                "The time the patient chose was just booked by someone else. Apologise in one "
                "sentence and call get_free_slots again for the same day."
            )
        return "\n".join(lines)
