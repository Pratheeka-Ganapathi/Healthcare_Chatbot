"""Tool results and the structured UI payloads the widget renders.

The LLM never writes UI JSON; handlers attach a typed payload. ``web/src/ui/types.ts``
is generated from ``ui_schema()`` (``make types``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from clinic_bot.domain.errors import ErrorCode
from clinic_bot.ports.messages import MessageCatalog


class QuickReplies(BaseModel):
    type: Literal["quick_replies"] = "quick_replies"
    options: list[str] = Field(max_length=3)

    @classmethod
    def confirm(cls, messages: MessageCatalog) -> QuickReplies:
        return cls(
            options=[
                messages.get("confirm.reply_confirm"),
                messages.get("confirm.reply_change_time"),
                messages.get("confirm.reply_change_doctor"),
            ]
        )


class MenuOption(BaseModel):
    label: str  # what the button shows
    text: str  # what a click sends


class Menu(BaseModel):
    """Stacked full-width options under the greeting."""

    type: Literal["menu"] = "menu"
    options: list[MenuOption] = Field(max_length=4)

    @classmethod
    def start(cls, messages: MessageCatalog) -> Menu:
        return cls(
            options=[
                MenuOption(
                    label=messages.get(f"menu.{key}.label"), text=messages.get(f"menu.{key}.text")
                )
                for key in MENU_KEYS
            ]
        )


MENU_KEYS = ("book", "cancel", "question")


class DoctorCard(BaseModel):
    name: str
    specialty: str
    days: str
    hours: str
    text: str  # what a click sends


class DoctorCards(BaseModel):
    type: Literal["doctor_cards"] = "doctor_cards"
    doctors: list[DoctorCard]


class SlotChip(BaseModel):
    label: str  # "6:15 PM"
    text: str  # "Tue 7 Oct, 6:15 PM"


class SlotGroup(BaseModel):
    date_label: str
    doctor: str
    slots: list[SlotChip]


class SlotButtons(BaseModel):
    type: Literal["slot_buttons"] = "slot_buttons"
    groups: list[SlotGroup]


class AppointmentChip(BaseModel):
    label: str
    text: str


class AppointmentButtons(BaseModel):
    type: Literal["appointment_buttons"] = "appointment_buttons"
    appointments: list[AppointmentChip]


class ConfirmationCard(BaseModel):
    type: Literal["confirmation_card"] = "confirmation_card"
    doctor: str
    specialty: str
    date: str
    time: str
    visit_type: str
    appointment_ref: str


class HandoffCard(BaseModel):
    type: Literal["handoff_card"] = "handoff_card"
    desk_number: str
    ticket_id: str | None = None


UIPayload = Annotated[
    QuickReplies
    | Menu
    | DoctorCards
    | SlotButtons
    | AppointmentButtons
    | ConfirmationCard
    | HandoffCard,
    Field(discriminator="type"),
]

_UI_ADAPTER: TypeAdapter[UIPayload] = TypeAdapter(UIPayload)


def button_texts(payload: UIPayload) -> frozenset[str]:
    """What a click on this payload can send. All of it is server-written text, which is
    why a message equal to one of these skips the Layer 2 classifier (SPEC 6.1)."""
    match payload:
        case QuickReplies():
            return frozenset(payload.options)
        case Menu():
            return frozenset(o.text for o in payload.options)
        case DoctorCards():
            return frozenset(d.text for d in payload.doctors)
        case SlotButtons():
            return frozenset(s.text for g in payload.groups for s in g.slots)
        case AppointmentButtons():
            return frozenset(a.text for a in payload.appointments)
        case _:
            return frozenset()


def ui_to_json(payload: UIPayload) -> dict[str, object]:
    dumped: dict[str, object] = _UI_ADAPTER.dump_python(payload, mode="json")
    return dumped


def ui_schema() -> dict[str, Any]:
    """JSON schema for the widget. ``type`` is marked required so TS unions narrow on it."""
    schema: dict[str, Any] = _UI_ADAPTER.json_schema(mode="serialization")
    schema["title"] = "UIPayload"
    for definition in schema.get("$defs", {}).values():
        if "type" in definition.get("properties", {}):
            required = definition.setdefault("required", [])
            if "type" not in required:
                required.insert(0, "type")
    return schema


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, object] | None = None
    error: ErrorCode | None = None
    ui: UIPayload | None = None
    silent: bool = False  # a fixed message was already sent; don't run the LLM

    @classmethod
    def success(
        cls, data: Mapping[str, object] | None = None, ui: UIPayload | None = None
    ) -> ToolResult:
        return cls(ok=True, data=dict(data) if data is not None else None, ui=ui)

    @classmethod
    def failure(
        cls, code: ErrorCode, data: Mapping[str, object] | None = None, *, silent: bool = False
    ) -> ToolResult:
        payload = dict(data) if data is not None else None
        return cls(ok=False, error=code, data=payload, silent=silent)

    def for_llm(self) -> dict[str, object]:
        out: dict[str, object] = {"ok": self.ok}
        if self.data:
            out["data"] = self.data
        if self.error is not None:
            out["error"] = self.error.value
        return out


if __name__ == "__main__":
    print(json.dumps(ui_schema(), indent=2))
