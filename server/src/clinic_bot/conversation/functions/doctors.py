"""submit_intake, list_doctors, choose_doctor, check_followup, set_same_issue."""

from __future__ import annotations

from pydantic import BaseModel, Field

from clinic_bot.conversation.registry import HandlerContext, llm_function
from clinic_bot.conversation.result import ToolResult
from clinic_bot.conversation.views import doctor_cards, doctor_data
from clinic_bot.domain.entities import IntakeAnswer, IntakeSummary
from clinic_bot.domain.enums import Specialty


class QA(BaseModel):
    q: str = Field(description="Question you asked")
    a: str = Field(description="Patient's answer")


class SubmitIntakeArgs(BaseModel):
    chief_complaint: str = Field(description="Main complaint in the patient's words")
    duration: str | None = Field(default=None, description="How long, e.g. '3 days'")
    severity: int | None = Field(default=None, ge=1, le=10, description="1 to 10, if given")
    answers: list[QA] = Field(default_factory=list, description="Questions asked and answers")
    red_flags_checked: list[str] = Field(
        default_factory=list, description="Warning signs you asked about"
    )


@llm_function(
    name="submit_intake",
    description="Save the pre-talk summary once the follow-up questions are done.",
    args=SubmitIntakeArgs,
    transition=lambda r, _s: "suggest_doctor" if r.ok else None,
)
async def submit_intake(args: SubmitIntakeArgs, ctx: HandlerContext) -> ToolResult:
    ctx.state.require_verified()
    ctx.state.intake = IntakeSummary(
        chief_complaint=args.chief_complaint,
        duration=args.duration,
        severity=args.severity,
        answers=tuple(IntakeAnswer(x.q, x.a) for x in args.answers),
        red_flags_checked=tuple(args.red_flags_checked),
    )
    return ToolResult.success({"saved": True})


class ListDoctorsArgs(BaseModel):
    specialty: Specialty | None = Field(default=None, description="Filter by specialty")
    name: str | None = Field(default=None, description="Doctor name the patient mentioned")


@llm_function(
    name="list_doctors",
    description="List clinic doctors with days and hours, by specialty and/or name.",
    args=ListDoctorsArgs,
)
async def list_doctors(args: ListDoctorsArgs, ctx: HandlerContext) -> ToolResult:
    found = ctx.services.directory.search(args.specialty, args.name)
    ctx.state.listed_doctor_ids.extend(
        d.id for d in found if d.id not in ctx.state.listed_doctor_ids
    )
    hint = ctx.state.specialty_hint
    data = {
        "doctors": [doctor_data(d) for d in found],
        "suggested_specialty": hint.label if hint else None,
    }
    return ToolResult.success(data, ui=doctor_cards(found, ctx.messages))


class ChooseDoctorArgs(BaseModel):
    doctor_id: int = Field(description="doctor_id of a doctor already listed to the patient")


@llm_function(
    name="choose_doctor",
    description="Record the doctor the patient chose. Then call check_followup.",
    args=ChooseDoctorArgs,
)
async def choose_doctor(args: ChooseDoctorArgs, ctx: HandlerContext) -> ToolResult:
    ctx.state.require_listed_doctor(args.doctor_id)
    ctx.state.select_doctor(args.doctor_id)
    doctor = ctx.services.directory.get(args.doctor_id)
    return ToolResult.success({"doctor": doctor.name, "next": "call check_followup"})


@llm_function(
    name="check_followup",
    description="Check whether the chosen doctor has marked this patient for a follow-up visit.",
    transition=lambda r, _s: (
        "pick_slot" if r.ok and not (r.data or {}).get("active_followup") else None
    ),
)
async def check_followup(_args: BaseModel, ctx: HandlerContext) -> ToolResult:
    patient_id = ctx.state.require_verified()
    doctor_id = ctx.state.require_selected_doctor()
    grant = await ctx.services.booking.active_grant(patient_id, doctor_id)
    ctx.state.followup_grant_id = grant.id if grant else None
    return ToolResult.success({"active_followup": grant is not None})


class SameIssueArgs(BaseModel):
    same: bool = Field(description="True if this visit is about the same issue as the last visit")


@llm_function(
    name="set_same_issue",
    description="Record whether this visit is about the same issue as the last visit.",
    args=SameIssueArgs,
    transition=lambda r, _s: "pick_slot" if r.ok else None,
)
async def set_same_issue(args: SameIssueArgs, ctx: HandlerContext) -> ToolResult:
    ctx.state.same_issue = args.same
    return ToolResult.success({"same_issue": args.same})
