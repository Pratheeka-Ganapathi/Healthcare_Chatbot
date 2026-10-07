"""Per-session flow state. Key facts live here, not in the LLM context."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from clinic_bot.conversation.result import UIPayload, button_texts
from clinic_bot.domain.entities import IntakeSummary
from clinic_bot.domain.enums import Intent, Sex, Specialty, TimePref
from clinic_bot.domain.errors import ErrorCode, InvalidChoice, NotVerified
from clinic_bot.services.booking import Quote
from clinic_bot.services.guardrails.base import Verdict
from clinic_bot.services.intake import Checklist

MAX_TURNS_KEPT = 40


@dataclass(frozen=True, slots=True)
class PatientInfo:
    name: str
    age: int
    sex: Sex


@dataclass(slots=True)
class FlowState:
    session_id: str
    verified_patient_id: int | None = None
    patient: PatientInfo | None = None
    initial_intent: Intent | None = None
    initial_message: str | None = None
    verify_failures: int = 0
    intake: IntakeSummary | None = None
    checklist: Checklist | None = None
    specialty_hint: Specialty | None = None
    listed_doctor_ids: list[int] = field(default_factory=list)
    selected_doctor_id: int | None = None
    offered_slots: dict[int, int] = field(default_factory=dict)  # slot_id → doctor_id
    selected_slot_id: int | None = None
    last_day: str | None = None
    last_time_pref: TimePref = TimePref.ANY
    followup_grant_id: int | None = None
    same_issue: bool | None = None
    quote: Quote | None = None
    offered_appointments: dict[int, str] = field(default_factory=dict)  # id → label
    selected_appointment_id: int | None = None
    notice: str | None = None  # one-shot hint for the next node: slot_taken | cancelled
    notice_data: dict[str, str] = field(default_factory=dict)
    handoff_ticket: str | None = None
    entry_ui: UIPayload | None = None  # shown when the next node becomes active
    active_buttons: set[str] = field(default_factory=set)  # sent since the last user message
    verdict: asyncio.Future[Verdict] | None = None
    current_node: str = "greet"
    turns: list[dict[str, str]] = field(default_factory=list)
    guardrail_events: list[dict[str, str]] = field(default_factory=list)

    @property
    def offered_slot_ids(self) -> list[int]:
        return list(self.offered_slots)

    def require_verified(self) -> int:
        if self.verified_patient_id is None:
            raise NotVerified(ErrorCode.NOT_VERIFIED)
        return self.verified_patient_id

    def require_listed_doctor(self, doctor_id: int) -> None:
        if doctor_id not in self.listed_doctor_ids:
            raise InvalidChoice(ErrorCode.INVALID_CHOICE)

    def require_selected_doctor(self) -> int:
        if self.selected_doctor_id is None:
            raise InvalidChoice(ErrorCode.INVALID_CHOICE, "no doctor selected")
        return self.selected_doctor_id

    def require_offered_slot(self, slot_id: int) -> int:
        """Returns the doctor id the slot belongs to."""
        if slot_id not in self.offered_slots:
            raise InvalidChoice(ErrorCode.INVALID_CHOICE)
        return self.offered_slots[slot_id]

    def require_selected_slot(self) -> int:
        if self.selected_slot_id is None:
            raise InvalidChoice(ErrorCode.INVALID_CHOICE, "no slot selected")
        return self.selected_slot_id

    def require_offered_appointment(self, appointment_id: int) -> None:
        if appointment_id not in self.offered_appointments:
            raise InvalidChoice(ErrorCode.INVALID_CHOICE)

    def select_doctor(self, doctor_id: int) -> None:
        if doctor_id != self.selected_doctor_id:
            self.followup_grant_id, self.same_issue = None, None
        self.selected_doctor_id = doctor_id

    def clear_doctor(self) -> None:
        self.selected_doctor_id, self.selected_slot_id = None, None
        self.followup_grant_id, self.same_issue = None, None

    def reset_booking(self) -> None:
        """After a booking or cancellation, start the next task clean."""
        self.intake, self.checklist, self.specialty_hint = None, None, None
        self.listed_doctor_ids.clear()
        self.selected_doctor_id, self.selected_slot_id, self.quote = None, None, None
        self.offered_slots.clear()
        self.offered_appointments.clear()
        self.selected_appointment_id = None
        self.followup_grant_id, self.same_issue = None, None
        self.initial_intent, self.initial_message = None, None

    def take_notice(self) -> tuple[str | None, dict[str, str]]:
        notice, data = self.notice, dict(self.notice_data)
        self.notice, self.notice_data = None, {}
        return notice, data

    def take_entry_ui(self) -> UIPayload | None:
        payload, self.entry_ui = self.entry_ui, None
        return payload

    def offer_buttons(self, payload: UIPayload) -> None:
        """Every UI payload passes here. Like the widget, buttons stay live until the
        patient sends the next message."""
        self.active_buttons |= button_texts(payload)

    def take_button(self, text: str) -> bool:
        """True if ``text`` is one of the live buttons. Called once per user message;
        any message, clicked or typed, retires the current buttons."""
        pressed = text in self.active_buttons
        self.active_buttons.clear()
        return pressed

    def add_turn(self, role: str, text: str) -> None:
        self.turns.append({"role": role, "text": text})
        if len(self.turns) > MAX_TURNS_KEPT:
            del self.turns[0]

    def last_bot_message(self) -> str:
        return next((t["text"] for t in reversed(self.turns) if t["role"] == "bot"), "")
