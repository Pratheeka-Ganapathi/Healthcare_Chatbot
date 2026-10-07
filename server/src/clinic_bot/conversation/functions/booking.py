"""confirm_booking, change_time, change_doctor, list/select/cancel appointment, reschedule stub."""

from __future__ import annotations

from pydantic import BaseModel, Field

from clinic_bot.conversation.registry import HandlerContext, llm_function
from clinic_bot.conversation.result import ToolResult
from clinic_bot.conversation.state import FlowState
from clinic_bot.conversation.views import appointment_buttons, appointment_label, confirmation_card
from clinic_bot.domain.errors import ErrorCode, InvalidChoice
from clinic_bot.services.booking import CancelAppointment, ConfirmBooking
from clinic_bot.services.scheduling import day_label, time_label


def _after_confirm(result: ToolResult, state: FlowState) -> str | None:
    if result.ok:
        return "booked"
    if result.error is ErrorCode.SLOT_TAKEN:
        state.notice, state.selected_slot_id = "slot_taken", None
        return "pick_slot"
    return None


@llm_function(
    name="confirm_booking",
    description="Book the appointment exactly as read back. Takes no arguments.",
    transition=_after_confirm,
)
async def confirm_booking(_args: BaseModel, ctx: HandlerContext) -> ToolResult:
    state = ctx.state
    cmd = ConfirmBooking(
        session_id=state.session_id,
        patient_id=state.require_verified(),
        slot_id=state.require_selected_slot(),
        intake=state.intake,
        same_issue=state.same_issue,
    )
    appt = await ctx.services.booking.confirm(cmd)
    doctor = ctx.services.directory.get(appt.doctor_id)
    state.notice = "booked"
    state.notice_data = {
        "doctor": doctor.name,
        "date": day_label(appt.slot.day),
        "time": time_label(appt.slot),
    }
    return ToolResult.success({"booked": True}, ui=confirmation_card(appt, doctor, ctx.messages))


@llm_function(
    name="change_time",
    description="The patient wants a different time with the same doctor.",
    transition=lambda _r, _s: "pick_slot",
)
async def change_time(_args: BaseModel, ctx: HandlerContext) -> ToolResult:
    ctx.state.selected_slot_id = None
    return ToolResult.success()


@llm_function(
    name="change_doctor",
    description="The patient wants a different doctor.",
    transition=lambda _r, _s: "suggest_doctor",
)
async def change_doctor(_args: BaseModel, ctx: HandlerContext) -> ToolResult:
    ctx.state.clear_doctor()
    return ToolResult.success()


@llm_function(
    name="list_appointments",
    description="List the patient's upcoming booked appointments again.",
)
async def list_appointments(_args: BaseModel, ctx: HandlerContext) -> ToolResult:
    appts = await ctx.services.booking.upcoming(ctx.state.require_verified())
    directory = ctx.services.directory
    ctx.state.offered_appointments = {
        a.id: appointment_label(a, directory, ctx.messages) for a in appts if a.id is not None
    }
    ui = appointment_buttons(appts, directory, ctx.messages) if appts else None
    return ToolResult.success({"count": len(appts)}, ui=ui)


class AppointmentArgs(BaseModel):
    appointment_id: int = Field(description="appointment_id from the list shown to the patient")


@llm_function(
    name="select_appointment",
    description="Record which listed appointment the patient wants to cancel.",
    args=AppointmentArgs,
    transition=lambda r, _s: "cancel_confirm" if r.ok else None,
)
async def select_appointment(args: AppointmentArgs, ctx: HandlerContext) -> ToolResult:
    ctx.state.require_offered_appointment(args.appointment_id)
    ctx.state.selected_appointment_id = args.appointment_id
    return ToolResult.success({"appointment": ctx.state.offered_appointments[args.appointment_id]})


def _after_cancel(result: ToolResult, state: FlowState) -> str | None:
    return "router" if result.ok else None


@llm_function(
    name="cancel_appointment",
    description="Cancel the appointment the patient confirmed.",
    args=AppointmentArgs,
    transition=_after_cancel,
)
async def cancel_appointment(args: AppointmentArgs, ctx: HandlerContext) -> ToolResult:
    state = ctx.state
    state.require_offered_appointment(args.appointment_id)
    if args.appointment_id != state.selected_appointment_id:
        raise InvalidChoice(ErrorCode.INVALID_CHOICE)
    cmd = CancelAppointment(patient_id=state.require_verified(), appointment_id=args.appointment_id)
    appt = await ctx.services.booking.cancel(cmd)
    doctor = ctx.services.directory.get(appt.doctor_id)
    state.reset_booking()
    state.notice = "cancelled"
    state.notice_data = {
        "doctor": doctor.name,
        "date": day_label(appt.slot.day),
        "time": time_label(appt.slot),
    }
    return ToolResult.success({"cancelled": True})


@llm_function(
    name="reschedule_appointment",
    description="Reschedule an appointment (not available yet).",
)
async def reschedule_appointment(_args: BaseModel, _ctx: HandlerContext) -> ToolResult:
    return ToolResult.failure(
        ErrorCode.NOT_IMPLEMENTED,
        {"hint": "Offer to cancel the old appointment and book a new one."},
    )
