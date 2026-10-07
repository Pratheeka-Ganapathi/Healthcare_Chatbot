"""route_intent, verify_patient, register_patient."""

from __future__ import annotations

from pydantic import BaseModel, Field

from clinic_bot.conversation.registry import HandlerContext, llm_function
from clinic_bot.conversation.result import ToolResult
from clinic_bot.conversation.state import FlowState, PatientInfo
from clinic_bot.domain.entities import Patient
from clinic_bot.domain.enums import Intent, Sex
from clinic_bot.domain.errors import ErrorCode, Locked, NotFound

MAX_SESSION_FAILURES = 3
_VERIFIED_TARGET = {Intent.BOOK: "pre_talk", Intent.CANCEL: "cancel_list", Intent.FAQ: "faq_only"}


class RouteIntentArgs(BaseModel):
    intent: Intent = Field(description="book, cancel or faq")
    complaint: str | None = Field(
        default=None, description="The patient's health complaint in their own words, if given"
    )


def _after_intent(result: ToolResult, state: FlowState) -> str | None:
    if not result.ok or state.initial_intent is None:
        return None
    if state.verified_patient_id is None:
        return "faq_only" if state.initial_intent is Intent.FAQ else "verify"
    return _VERIFIED_TARGET[state.initial_intent]


@llm_function(
    name="route_intent",
    description="Record what the patient wants: book, cancel, or ask a clinic question (faq).",
    args=RouteIntentArgs,
    transition=_after_intent,
)
async def route_intent(args: RouteIntentArgs, ctx: HandlerContext) -> ToolResult:
    ctx.state.initial_intent = args.intent
    if args.complaint:
        ctx.state.initial_message = args.complaint.strip()
    return ToolResult.success({"intent": args.intent.value})


class VerifyPatientArgs(BaseModel):
    phone: str = Field(description="The patient's registered mobile number as they typed it")
    dob: str = Field(description="The patient's date of birth as they typed it")


def _after_verify(result: ToolResult, state: FlowState) -> str | None:
    if result.ok:
        intent = state.initial_intent
        return _VERIFIED_TARGET[intent] if intent in (Intent.BOOK, Intent.CANCEL) else "router"
    if result.error is ErrorCode.LOCKED or state.verify_failures >= MAX_SESSION_FAILURES:
        return "handoff"
    return None


@llm_function(
    name="verify_patient",
    description="Check a returning patient's registered mobile number and date of birth.",
    args=VerifyPatientArgs,
    transition=_after_verify,
)
async def verify_patient(args: VerifyPatientArgs, ctx: HandlerContext) -> ToolResult:
    try:
        patient = await ctx.services.verification.verify(args.phone, args.dob)
    except (Locked, NotFound) as exc:
        return await _identity_failed(exc, "verify.no_match", ctx)
    return _signed_in(patient, ctx, registered=False)


class RegisterPatientArgs(BaseModel):
    name: str = Field(description="The patient's full name as they typed it")
    phone: str = Field(description="The patient's mobile number as they typed it")
    dob: str = Field(description="The patient's date of birth as they typed it")
    sex: Sex = Field(description="female, male or other, as the patient said")


@llm_function(
    name="register_patient",
    description="Register a new patient who has not visited the clinic before.",
    args=RegisterPatientArgs,
    transition=_after_verify,
)
async def register_patient(args: RegisterPatientArgs, ctx: HandlerContext) -> ToolResult:
    service = ctx.services.verification
    try:
        patient = await service.register(args.name, args.phone, args.dob, args.sex)
    except (Locked, NotFound) as exc:
        return await _identity_failed(exc, "register.no_match", ctx)
    return _signed_in(patient, ctx, registered=True)


async def _identity_failed(exc: Locked | NotFound, message: str, ctx: HandlerContext) -> ToolResult:
    if isinstance(exc, Locked):
        await ctx.io.say(ctx.messages.get("verify.locked"))
        return ToolResult.failure(ErrorCode.LOCKED, silent=True)
    ctx.state.verify_failures += 1
    if ctx.state.verify_failures < MAX_SESSION_FAILURES:
        await ctx.io.say(ctx.messages.get(message))
    return ToolResult.failure(ErrorCode.NO_MATCH, silent=True)


def _signed_in(patient: Patient, ctx: HandlerContext, registered: bool) -> ToolResult:
    ctx.state.verified_patient_id = patient.id
    age = ctx.services.verification.age_of(patient)
    ctx.state.patient = PatientInfo(patient.name, age, patient.sex)
    return ToolResult.success({"verified": True, "name": patient.name, "new": registered})
