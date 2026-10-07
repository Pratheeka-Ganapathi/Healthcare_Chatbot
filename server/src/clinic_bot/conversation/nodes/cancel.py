"""cancel_list → cancel_confirm."""

from __future__ import annotations

from typing import TYPE_CHECKING

from clinic_bot.conversation.nodes.base import BaseNode, patient_line
from clinic_bot.conversation.views import appointment_buttons, appointment_label

if TYPE_CHECKING:
    from clinic_bot.conversation.registry import HandlerContext
    from clinic_bot.conversation.state import FlowState


class CancelListNode(BaseNode):
    name = "cancel_list"
    functions = (
        "list_appointments",
        "select_appointment",
        "reschedule_appointment",
        "route_intent",
    )

    async def prepare(self, ctx: HandlerContext) -> None:
        appts = await ctx.services.booking.upcoming(ctx.state.require_verified())
        directory = ctx.services.directory
        ctx.state.offered_appointments = {
            a.id: appointment_label(a, directory, ctx.messages) for a in appts if a.id is not None
        }
        ctx.state.entry_ui = appointment_buttons(appts, directory, ctx.messages) if appts else None

    async def on_enter(self, ctx: HandlerContext) -> None:
        if (payload := ctx.state.take_entry_ui()) is not None:
            await ctx.io.ui(payload)

    def task(self, state: FlowState) -> str:
        if not state.offered_appointments:
            listing = (
                "The patient has no upcoming appointments. Tell them, and ask if there is "
                "anything else (call route_intent if so)."
            )
        else:
            listing = "Upcoming appointments:\n" + "\n".join(
                f"appointment_id {i}: {label}" for i, label in state.offered_appointments.items()
            )
            listing += (
                "\nAsk which one they want to cancel; buttons are shown. When they pick one, call "
                "select_appointment with its appointment_id. If they want to book instead, call "
                "route_intent. If they want to reschedule, call reschedule_appointment."
            )
        return f"{patient_line(state)}\n{listing}"


class CancelConfirmNode(BaseNode):
    name = "cancel_confirm"
    functions = ("cancel_appointment", "select_appointment", "list_appointments")

    def task(self, state: FlowState) -> str:
        appt_id = state.selected_appointment_id
        label = state.offered_appointments.get(appt_id, "") if appt_id is not None else ""
        return (
            f"{patient_line(state)}\nThe patient picked appointment_id {appt_id}: {label}. Ask "
            f"them to confirm the cancellation in one sentence. If they confirm, call "
            f"cancel_appointment with that appointment_id. If it is refused because it is less "
            f"than two hours away, explain that appointments can only be cancelled up to two hours"
            f" before, and offer to have the front desk call them (call request_human if they "
            f"agree). If they pick a different appointment from the list, call select_appointment;"
            f" to show the list again, call list_appointments."
        )
