"""End to end over a real WebSocket: greet, verify, pre-talk, doctor, slot, confirm, booked."""

from __future__ import annotations

from typing import Any

from tests.fakes.llm import Call, Say, last_tool_result
from tests.fakes.ws_client import RtviClient
from tests.integration.conftest import LiveServer, appointments_of


def _first_slot(messages: list[dict[str, Any]]) -> Call:
    result = last_tool_result(messages)
    return Call("select_slot", {"slot_id": result["data"]["slots"][0]["slot_id"]})


async def test_happy_booking_over_websocket(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        greet = await client.collect()
        llm = live_server.llm
        assert "welcome to City Care Clinic" in greet.text
        [menu] = [ui for ui in greet.ui if ui["type"] == "menu"]
        assert [o["text"] for o in menu["options"]] == [
            "I want to book an appointment",
            "I want to cancel an appointment",
            "I have a question about the clinic",
        ]

        llm.extend(
            Call(
                "route_intent", {"intent": "book", "complaint": "itchy rash on my arm for a week"}
            ),
            Say("Sure. Please share your registered mobile number and date of birth."),
        )
        await client.send_text("I want to book, I have an itchy rash on my arm for a week")
        turn = await client.collect()
        assert "mobile number" in turn.text

        llm.extend(
            Call("verify_patient", {"phone": "90000 00005", "dob": "03/03/1995"}),
            Say("Thanks Sanjay. Is the rash spreading?"),
        )
        await client.send_text("9000000005, 3 March 1995")
        turn = await client.collect()
        assert "Is the rash spreading" in turn.text

        llm.extend(
            Call(
                "submit_intake",
                {
                    "chief_complaint": "itchy rash on arm",
                    "duration": "1 week",
                    "severity": 4,
                    "answers": [{"q": "Is it spreading?", "a": "a little"}],
                    "red_flags_checked": ["lip swelling"],
                },
            ),
            Say("I suggest Dr. Kavya Shetty, our dermatologist."),
        )
        await client.send_text("a little, maybe 4 out of 10")
        turn = await client.collect()
        assert "Kavya Shetty" in turn.text
        cards = next(ui for ui in turn.ui if ui["type"] == "doctor_cards")
        assert cards["doctors"] and all("fee" not in d for d in cards["doctors"])
        derm = live_server.container.services.directory.search(None, "Kavya Shetty")[0]

        llm.extend(
            Call("choose_doctor", {"doctor_id": derm.id}),
            Call("check_followup"),
            Say("Which day works for you, and morning or evening?"),
        )
        await client.send_text("Yes, Dr. Shetty is fine")
        turn = await client.collect()
        assert "Which day" in turn.text

        llm.extend(
            Call("get_free_slots", {"day": "wednesday", "time_pref": "evening"}),
            Say("Here are the times."),
        )
        await client.send_text("Wednesday evening")
        turn = await client.collect()
        slot_ui = next(ui for ui in turn.ui if ui["type"] == "slot_buttons")
        chip = slot_ui["groups"][0]["slots"][0]
        assert chip["text"].startswith("Wed 7 Oct, ")

        llm.extend(_first_slot)
        await client.send_text(chip["text"])
        turn = await client.collect()
        assert "Please check your booking: Dr. Kavya Shetty" in turn.text
        assert "This is a new visit. Shall I confirm it?" in turn.text and "₹" not in turn.text
        assert any(ui["type"] == "quick_replies" for ui in turn.ui)

        llm.extend(Call("confirm_booking"))
        await client.send_text("Confirm")
        turn = await client.collect()
        assert "is booked" in turn.text
        assert "Avoid applying creams" in turn.text  # dermatology prep sheet
        card = next(ui for ui in turn.ui if ui["type"] == "confirmation_card")
        assert "fee" not in card and card["visit_type"] == "new"
        assert "₹" not in turn.text

    assert llm.calls == [
        "route_intent",
        "verify_patient",
        "submit_intake",
        "choose_doctor",
        "check_followup",
        "get_free_slots",
        "select_slot",
        "confirm_booking",
    ]
    await _assert_booked(live_server, derm.id)


async def _assert_booked(live_server: LiveServer, doctor_id: int) -> None:
    rows = await appointments_of(live_server, patient_id=5)
    assert len(rows) == 1
    row = rows[0]
    assert row["doctor_id"] == doctor_id and row["status"] == "booked" and row["fee"] == 80000
    assert row["intake_summary"]["chief_complaint"] == "itchy rash on arm"
