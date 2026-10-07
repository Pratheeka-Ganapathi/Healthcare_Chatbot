"""get_free_slots, find_alternatives, select_slot."""

from __future__ import annotations

from pydantic import BaseModel, Field

from clinic_bot.conversation.registry import HandlerContext, llm_function
from clinic_bot.conversation.result import QuickReplies, ToolResult
from clinic_bot.conversation.views import slot_buttons, slot_data
from clinic_bot.domain.enums import TimePref
from clinic_bot.services.scheduling import SlotOffer


class FreeSlotsArgs(BaseModel):
    day: str = Field(
        description=(
            "today, tomorrow, day_after_tomorrow, a weekday name like saturday, "
            "a date as YYYY-MM-DD, or next_available"
        )
    )
    time_pref: TimePref = Field(default=TimePref.ANY, description="morning, evening or any")


def _remember(ctx: HandlerContext, offers: list[SlotOffer]) -> None:
    for offer in offers:
        for slot in offer.slots:
            ctx.state.offered_slots[slot.id] = offer.doctor_id


@llm_function(
    name="get_free_slots",
    description=(
        "Up to three free slots with the chosen doctor on a day. The server resolves the date."
    ),
    args=FreeSlotsArgs,
)
async def get_free_slots(args: FreeSlotsArgs, ctx: HandlerContext) -> ToolResult:
    doctor_id = ctx.state.require_selected_doctor()
    ctx.state.last_day, ctx.state.last_time_pref = args.day, args.time_pref
    offer = await ctx.services.scheduling.free_slots(doctor_id, args.day, args.time_pref)
    _remember(ctx, [offer])
    directory = ctx.services.directory
    return ToolResult.success(
        slot_data([offer], directory)[0],
        ui=slot_buttons([offer], directory, doctor_id, ctx.messages),
    )


@llm_function(
    name="find_alternatives",
    description="When the requested day has no slots: next two days with this doctor, and other "
    "doctors of the same specialty on the requested day.",
)
async def find_alternatives(_args: BaseModel, ctx: HandlerContext) -> ToolResult:
    doctor_id = ctx.state.require_selected_doctor()
    day = ctx.state.last_day or "next_available"
    offers = await ctx.services.scheduling.alternatives(doctor_id, day, ctx.state.last_time_pref)
    _remember(ctx, offers)
    directory = ctx.services.directory
    return ToolResult.success(
        {"options": slot_data(offers, directory)},
        ui=slot_buttons(offers, directory, doctor_id, ctx.messages),
    )


class SelectSlotArgs(BaseModel):
    slot_id: int = Field(description="slot_id of one of the slots just offered")


@llm_function(
    name="select_slot",
    description="Select one of the slots just offered to the patient.",
    args=SelectSlotArgs,
    transition=lambda r, _s: "confirm" if r.ok else None,
)
async def select_slot(args: SelectSlotArgs, ctx: HandlerContext) -> ToolResult:
    doctor_id = ctx.state.require_offered_slot(args.slot_id)
    ctx.state.select_doctor(doctor_id)
    ctx.state.selected_slot_id = args.slot_id
    return ToolResult.success(ui=QuickReplies.confirm(ctx.messages))
