"""Golden-style conversations: assert tool sequence and DB state, not wording (SPEC 12.3)."""

from __future__ import annotations

from typing import Any

from tests.fakes.llm import Call, Say, last_tool_result
from tests.fakes.ws_client import RtviClient
from tests.integration.conftest import LiveServer, appointments_of, query

ASHA = ("9000000001", "05/06/1990")
MEENA = ("9000000003", "14/02/1972")
SANJAY = ("9000000005", "03/03/1995")


async def verified(
    client: RtviClient,
    server: LiveServer,
    intent: str,
    who: tuple[str, str],
    complaint: str | None = None,
) -> None:
    await client.collect()
    args: dict[str, Any] = {"intent": intent}
    if complaint:
        args["complaint"] = complaint
    server.llm.extend(
        Call("route_intent", args), Say("Your mobile number and date of birth, please.")
    )
    await client.send_text(f"I want to {intent}")
    await client.collect()
    server.llm.extend(Call("verify_patient", {"phone": who[0], "dob": who[1]}))
    await client.send_text(f"{who[0]} {who[1]}")


def pick_first_slot(messages: list[dict[str, Any]]) -> Call:
    return Call(
        "select_slot", {"slot_id": last_tool_result(messages)["data"]["slots"][0]["slot_id"]}
    )


async def test_followup_grant_path(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        await verified(client, live_server, "book", ASHA, "fever again")
        live_server.llm.extend(
            Say("Sorry to hear that. How many days?"),
            Call("submit_intake", {"chief_complaint": "fever again", "duration": "2 days"}),
            Say("I suggest Dr. Rao."),
        )
        await client.collect()
        await client.send_text("2 days")
        await client.collect()
        live_server.llm.extend(
            Call("choose_doctor", {"doctor_id": 1}),
            Call("check_followup"),
            Say("Is this about the same issue as your last visit?"),
        )
        await client.send_text("Dr. Rao please")
        turn = await client.collect()
        assert "same issue" in turn.text
        live_server.llm.extend(
            Call("set_same_issue", {"same": True}),
            Say("Which day?"),
            Call("get_free_slots", {"day": "wednesday", "time_pref": "evening"}),
            Say("Here you go."),
            pick_first_slot,
        )
        await client.send_text("yes, same fever")
        await client.collect()
        await client.send_text("wednesday evening")
        await client.collect()
        await client.send_text("the first one")
        turn = await client.collect()
        assert "This is a follow-up visit. Shall I confirm it?" in turn.text
        assert "₹" not in turn.text
        live_server.llm.extend(Call("confirm_booking"))
        await client.send_text("Confirm")
        await client.collect()
    rows = await appointments_of(live_server, patient_id=1)
    new = [r for r in rows if r["session_id"] != "seed"]
    assert len(new) == 1 and new[0]["visit_type"] == "followup" and new[0]["fee"] == 30000


async def test_cancel_inside_cutoff_is_refused(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        await verified(client, live_server, "cancel", MEENA)
        live_server.llm.extend(Say("Which appointment would you like to cancel?"))
        turn = await client.collect()
        buttons = next(ui for ui in turn.ui if ui["type"] == "appointment_buttons")
        assert buttons["appointments"][0]["text"].startswith("Cancel my appointment with Dr. Rao")
        rows = await appointments_of(live_server, patient_id=3)
        soon = next(
            r
            for r in rows
            if r["status"] == "booked" and r["session_id"] == "seed" and r["doctor_id"] == 1
        )
        appt_id = soon["id"]
        live_server.llm.extend(
            Call("select_appointment", {"appointment_id": appt_id}),
            Say("Shall I cancel it?"),
            Call("cancel_appointment", {"appointment_id": appt_id}),
            Say("Sorry, it is less than two hours away."),
        )
        await client.send_text(buttons["appointments"][0]["text"])
        await client.collect()
        await client.send_text("yes")
        turn = await client.collect()
        assert "two hours" in turn.text
    rows = await appointments_of(live_server, patient_id=3)
    assert next(r for r in rows if r["id"] == appt_id)["status"] == "booked"
    assert live_server.llm.calls[-1] == "cancel_appointment"


async def test_two_tabs_same_slot(live_server: LiveServer) -> None:
    """SPEC 12.4: second tab gets SLOT_TAKEN and a re-offer."""
    async with RtviClient(live_server.url) as tab1, RtviClient(live_server.url) as tab2:
        tabs = [(tab1, SANJAY), (tab2, ASHA)]
        for tab, _ in tabs:
            await tab.collect()
        assert len(live_server.llms) == 2
        slot_holder: dict[str, int] = {}

        def same_slot(messages: list[dict[str, Any]]) -> Call:
            slot_holder.setdefault("id", last_tool_result(messages)["data"]["slots"][0]["slot_id"])
            return Call("select_slot", {"slot_id": slot_holder["id"]})

        for (tab, who), llm in zip(tabs, live_server.llms, strict=True):
            llm.extend(
                Call("route_intent", {"intent": "book", "complaint": "cough"}),
                Call("verify_patient", {"phone": who[0], "dob": who[1]}),
                Call("submit_intake", {"chief_complaint": "cough"}),
                Call("choose_doctor", {"doctor_id": 3}),
                Call("check_followup"),
                Call("get_free_slots", {"day": "thursday", "time_pref": "morning"}),
                same_slot,
            )
            await tab.send_text("book for cough")
            await tab.collect(quiet_s=1.5)
        for llm in live_server.llms:
            llm.extend(Call("confirm_booking"), Say("Let me find other times."))
        await tab1.send_text("Confirm")
        await tab1.collect()
        await tab2.send_text("Confirm")
        turn = await tab2.collect()
        assert "Let me find other times" in turn.text
        assert live_server.llms[1].tools_seen[-1][:3] == [
            "get_free_slots",
            "find_alternatives",
            "select_slot",
        ]
    sanjay = await appointments_of(live_server, 5)
    asha = [r for r in await appointments_of(live_server, 1) if r["session_id"] != "seed"]
    assert len(sanjay) == 1 and asha == []


async def test_three_failed_verifications_hand_off(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(
            Call("route_intent", {"intent": "book"}), Say("Number and date of birth?")
        )
        await client.send_text("book")
        await client.collect()
        for attempt in range(3):
            live_server.llm.extend(
                Call("verify_patient", {"phone": "9000000005", "dob": "01/01/2001"})
            )
            await client.send_text("9000000005 01/01/2001")
            turn = await client.collect()
            if attempt < 2:
                assert "don't match our records" in turn.text
        assert "Please call the front desk" in turn.text
        assert any(ui["type"] == "handoff_card" for ui in turn.ui)


async def test_new_patient_registers_and_goes_straight_to_pre_talk(
    live_server: LiveServer,
) -> None:
    seen: dict[str, Any] = {}

    def welcome(messages: list[dict[str, Any]]) -> Say:
        seen.update(last_tool_result(messages))
        return Say("Welcome to City Care, Priya. How long have you had the rash?")

    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(
            Call("route_intent", {"intent": "book", "complaint": "skin rash"}),
            Say("Your registered mobile number and date of birth, or are you new?"),
        )
        await client.send_text("I want to book, I have a skin rash")
        await client.collect()
        live_server.llm.extend(
            Call(
                "register_patient",
                {
                    "name": "Priya Sharma",
                    "phone": "9888800001",
                    "dob": "12/04/1988",
                    "sex": "female",
                },
            ),
            welcome,
        )
        await client.send_text("I'm new. Priya Sharma, 9888800001, 12/04/1988, female")
        turn = await client.collect()
        assert "Welcome to City Care, Priya" in turn.text
        assert seen["data"] == {"verified": True, "name": "Priya Sharma", "new": True}
        assert "submit_intake" in live_server.llm.tools_seen[-1]  # pre_talk
    rows = await query(live_server, "SELECT name, sex FROM patients WHERE phone = '9888800001'")
    assert rows == [{"name": "Priya Sharma", "sex": "female"}]


async def test_registering_an_existing_number_with_other_details_fails(
    live_server: LiveServer,
) -> None:
    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(Call("route_intent", {"intent": "book"}), Say("Are you new?"))
        await client.send_text("book")
        await client.collect()
        live_server.llm.extend(
            Call(
                "register_patient",
                {"name": "Not Sanjay", "phone": SANJAY[0], "dob": SANJAY[1], "sex": "male"},
            )
        )
        await client.send_text("new patient: Not Sanjay, 9000000005, 03/03/1995, male")
        turn = await client.collect()
        assert "couldn't register you" in turn.text


async def test_fee_question_before_verification_uses_the_doctor_table(
    live_server: LiveServer,
) -> None:
    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(
            Call("route_intent", {"intent": "faq"}),
            Call("answer_faq", {"question": "how much is a dermatology consultation fee"}),
            lambda messages: Say(
                f"The fee is {last_tool_result(messages)['data']['doctors'][0]['fee']}."
            ),
        )
        await client.send_text("how much is a dermatology consultation fee")
        turn = await client.collect()
        assert "₹800" in turn.text


async def test_doctor_question_without_cost_gets_no_fees(live_server: LiveServer) -> None:
    seen: dict[str, Any] = {}

    def reply(messages: list[dict[str, Any]]) -> Say:
        seen.update(last_tool_result(messages))
        return Say("Our dermatologist sees patients on weekdays.")

    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(
            Call("route_intent", {"intent": "faq"}),
            Call("answer_faq", {"question": "which days does the dermatologist work"}),
            reply,
        )
        await client.send_text("which days does the dermatologist work")
        await client.collect()
    doctors = seen["data"]["doctors"]
    assert doctors and all("fee" not in d and "followup_fee" not in d for d in doctors)


async def test_unknown_faq_gets_fixed_reply(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(
            Call("route_intent", {"intent": "faq"}),
            Call("answer_faq", {"question": "do you sell gift vouchers for spa treatments"}),
        )
        await client.send_text("do you sell gift vouchers for spa treatments")
        turn = await client.collect()
        assert "I don't have that information" in turn.text
