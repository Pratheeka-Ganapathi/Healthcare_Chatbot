"""Button presses skip the Layer 2 classifier only for live, server-written button text."""

from __future__ import annotations

from clinic_bot.conversation.result import (
    AppointmentButtons,
    AppointmentChip,
    ConfirmationCard,
    DoctorCard,
    DoctorCards,
    Menu,
    MenuOption,
    QuickReplies,
    SlotButtons,
    SlotChip,
    SlotGroup,
    button_texts,
)
from clinic_bot.conversation.state import FlowState

MENU = Menu(options=[MenuOption(label="Book", text="I want to book an appointment")])


def test_every_interactive_payload_lists_what_a_click_sends() -> None:
    doctor = DoctorCard(name="Dr. Rao", specialty="x", days="Mon", hours="9-1", text="Dr. Rao")
    slots = SlotButtons(
        groups=[
            SlotGroup(
                date_label="Tue",
                doctor="Dr. Rao",
                slots=[SlotChip(label="6 PM", text="Tue 7 Oct, 6 PM")],
            )
        ]
    )
    appts = AppointmentButtons(appointments=[AppointmentChip(label="A-1", text="Cancel A-1")])
    assert button_texts(MENU) == {"I want to book an appointment"}
    assert button_texts(QuickReplies(options=["Confirm", "Change time"])) == {
        "Confirm",
        "Change time",
    }
    assert button_texts(DoctorCards(doctors=[doctor])) == {"Dr. Rao"}
    assert button_texts(slots) == {"Tue 7 Oct, 6 PM"}
    assert button_texts(appts) == {"Cancel A-1"}


def test_cards_without_buttons_offer_nothing() -> None:
    card = ConfirmationCard(
        doctor="Dr. Rao",
        specialty="x",
        date="Tue",
        time="6 PM",
        visit_type="new",
        appointment_ref="A-1",
    )
    assert button_texts(card) == frozenset()


def test_a_live_button_counts_once() -> None:
    state = FlowState(session_id="s")
    state.offer_buttons(MENU)
    assert state.take_button("I want to book an appointment")
    assert not state.take_button("I want to book an appointment")  # retired by the first send


def test_any_message_retires_the_buttons() -> None:
    state = FlowState(session_id="s")
    state.offer_buttons(MENU)
    assert not state.take_button("hello")
    assert not state.take_button("I want to book an appointment")


def test_buttons_shown_together_are_all_live() -> None:
    state = FlowState(session_id="s")
    state.offer_buttons(MENU)
    state.offer_buttons(QuickReplies(options=["Confirm"]))
    assert state.take_button("Confirm")
