"""suggest_doctor: server-side specialty mapping, then propose one doctor."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from clinic_bot.conversation.nodes.base import BaseNode, patient_line
from clinic_bot.conversation.views import doctor_cards, doctor_line
from clinic_bot.domain.enums import Specialty

if TYPE_CHECKING:
    from clinic_bot.conversation.prompts import PromptLibrary
    from clinic_bot.conversation.registry import FunctionRegistry, HandlerContext
    from clinic_bot.conversation.state import FlowState
    from clinic_bot.ports.messages import MessageCatalog
    from clinic_bot.services.directory import DoctorDirectory


class SuggestDoctorNode(BaseNode):
    name = "suggest_doctor"
    functions = ("list_doctors", "choose_doctor", "check_followup", "set_same_issue")

    def __init__(
        self,
        prompts: PromptLibrary,
        registry: FunctionRegistry,
        messages: MessageCatalog,
        directory: DoctorDirectory,
    ) -> None:
        super().__init__(prompts, registry, messages)
        self._directory = directory

    async def prepare(self, ctx: HandlerContext) -> None:
        state = ctx.state
        if state.intake is not None and state.patient is not None:
            started = time.perf_counter()
            state.specialty_hint = await ctx.services.mapper.map(
                state.intake, state.patient.age, state.patient.sex
            )
            ctx.record_span("mapper", (time.perf_counter() - started) * 1000)
        hint = state.specialty_hint or Specialty.GENERAL_MEDICINE
        for doctor in ctx.services.directory.in_specialty(hint):
            if doctor.id not in state.listed_doctor_ids:
                state.listed_doctor_ids.append(doctor.id)

    async def on_enter(self, ctx: HandlerContext) -> None:
        hint = ctx.state.specialty_hint or Specialty.GENERAL_MEDICINE
        await ctx.io.ui(doctor_cards(ctx.services.directory.in_specialty(hint), ctx.messages))

    def task(self, state: FlowState) -> str:
        hint = state.specialty_hint or Specialty.GENERAL_MEDICINE
        complaint = state.intake.chief_complaint if state.intake else "not recorded"
        return (
            f"{patient_line(state)} Complaint: {complaint}.\n"
            f"Suggested specialty (a hint, not a diagnosis): {hint.label}.\n"
            "Doctors in this specialty:\n" + "\n".join(self._doctor_lines(state)) + "\n"
            "Propose one doctor in one or two sentences, with their days. Do not mention fees; "
            "if the patient asks about cost, call answer_faq. If the specialty is General "
            "Medicine or might not fully fit, mention the doctor can refer onward.\n"
            "If the patient names a doctor, call list_doctors with that name. If that doctor's "
            "specialty differs from the suggested one, say so once, offer both, and let the "
            "patient decide. If several doctors match the name, ask which one.\n"
            "When the patient agrees on a doctor, call choose_doctor with its doctor_id, then call "
            "check_followup. If check_followup reports an active follow-up, ask whether this visit "
            "is about the same issue as their last visit, then call set_same_issue."
        )

    def _doctor_lines(self, state: FlowState) -> list[str]:
        hint = state.specialty_hint or Specialty.GENERAL_MEDICINE
        return [doctor_line(d) for d in self._directory.in_specialty(hint)]
