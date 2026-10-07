"""Guardrail paths over a real WebSocket (SPEC 6)."""

from __future__ import annotations

import asyncio

from tests.fakes.llm import Call, Fail, Say
from tests.fakes.ws_client import RtviClient
from tests.integration.conftest import LiveServer


async def _verified(client: RtviClient, server: LiveServer) -> None:
    await client.collect()
    server.llm.extend(
        Call("route_intent", {"intent": "book"}),
        Say("Please share your mobile number and date of birth."),
        Call("verify_patient", {"phone": "9000000005", "dob": "03/03/1995"}),
        Say("What brings you in today?"),
    )
    await client.send_text("I want to book")
    await client.collect()
    await client.send_text("9000000005 3/3/1995")
    await client.collect()


EMERGENCY_NOTE = "If this is an emergency, please call 108 or 112"


async def test_layer1_emergency_adds_a_soft_note_and_the_chat_goes_on(
    live_server: LiveServer,
) -> None:
    async with RtviClient(live_server.url) as client:
        await _verified(client, live_server)
        live_server.llm.extend(Say("Sorry to hear that. How long have you had the cough?"))
        await client.send_text("no chest pain, just a cough for three days")
        turn = await client.collect()
        assert turn.texts[0].startswith(EMERGENCY_NOTE)
        assert "How long have you had the cough" in turn.texts[-1]
        assert not any(ui["type"] == "quick_replies" for ui in turn.ui)
        assert "submit_intake" in live_server.llm.tools_seen[-1]  # still in pre_talk


async def test_layer2_emergency_note_comes_before_the_reply(live_server: LiveServer) -> None:
    live_server.classifier.delay_s = 0.5  # the main LLM answers before the verdict
    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(Say("I can help you book a doctor."))
        await client.send_text("it feels like an elephant is sitting on me")
        turn = await client.collect(quiet_s=1.5)
        assert len(turn.texts) == 2
        assert turn.texts[0].startswith(EMERGENCY_NOTE)
        assert turn.texts[1] == "I can help you book a doctor."


async def test_both_layers_flagging_show_the_note_once(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(Say("I can help you book a doctor."))
        await client.send_text("chest pain, like an elephant is sitting on me")
        turn = await client.collect(quiet_s=1.0)
        assert sum(EMERGENCY_NOTE in t for t in turn.texts) == 1
        assert "I can help you book a doctor." in turn.text


async def test_emergency_with_a_medicine_question_is_still_refused(
    live_server: LiveServer,
) -> None:
    async with RtviClient(live_server.url) as client:
        await client.collect()
        await client.send_text("I have chest pain, can I take Dolo 650?")
        turn = await client.collect()
        assert EMERGENCY_NOTE in turn.text
        assert "not able to give any advice about medicines" in turn.text
        assert live_server.llm.calls == []


async def test_medication_question_refused_and_node_unchanged(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        await client.collect()
        await client.send_text("how many Dolo 650 tablets can I take?")
        turn = await client.collect()
        assert "not able to give any advice about medicines" in turn.text
        assert live_server.llm.calls == []
        live_server.llm.extend(Call("route_intent", {"intent": "faq"}), Say("Sure, ask away."))
        await client.send_text("ok, I have a question about the clinic")
        turn = await client.collect()
        assert "ask away" in turn.text


async def test_off_topic_code_request(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        await client.collect()
        await client.send_text("write python code to sort a list")
        turn = await client.collect()
        assert "appointments and questions about City Care Clinic" in turn.text


async def test_self_harm_adds_a_soft_helpline_note_and_the_chat_goes_on(
    live_server: LiveServer,
) -> None:
    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(Say("I'm here to help. Would you like to see a doctor?"))
        await client.send_text("I want to end my life")
        turn = await client.collect()
        assert "14416" in turn.texts[0] and "112" in turn.texts[0]
        assert "Would you like to see a doctor?" in turn.texts[-1]
        live_server.llm.extend(Call("route_intent", {"intent": "book"}), Say("Sure."))
        await client.send_text("yes please, book a doctor")
        turn = await client.collect()
        assert "Sure." in turn.text


async def test_faq_detour_keeps_node(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(
            Call("route_intent", {"intent": "faq"}),
            Call("answer_faq", {"question": "what are your opening hours on Saturday"}),
            Say("We are open Saturday 9 to 1 and 4 to 8:30."),
        )
        await client.send_text("what are your opening hours on Saturday")
        turn = await client.collect()
        assert "Saturday" in turn.text
        assert live_server.container  # node did not change beyond faq_only
        await asyncio.sleep(0)


async def test_classifier_crash_does_not_hang_the_turn(live_server: LiveServer) -> None:
    live_server.classifier.fail_with = ValueError("unexpected provider error")
    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(Say("Happy to help with that."))
        await client.send_text("hello there")
        turn = await client.collect()
        assert "Happy to help" in turn.text


async def test_main_llm_error_retries_once_then_busy(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(Fail(), Say("Recovered after one retry."))
        await client.send_text("hello")
        turn = await client.collect(quiet_s=2.5)
        assert "Recovered after one retry" in turn.text
        live_server.llm.extend(Fail(), Fail())
        await client.send_text("hello again")
        turn = await client.collect(quiet_s=2.5)
        assert "a little busy right now" in turn.text


async def test_a_button_click_skips_the_classifier(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        greeting = await client.collect()
        book = greeting.ui[0]["options"][0]["text"]  # the menu's "book" button
        live_server.llm.extend(
            Call("route_intent", {"intent": "book"}),
            Say("Please share your mobile number and date of birth."),
        )
        await client.send_text(book)
        await client.collect()
        assert live_server.classifier.calls == []
        await client.send_text("9000000005 3/3/1995")  # typed: classified as always
        await client.collect()
        assert len(live_server.classifier.calls) == 1


async def test_typing_a_retired_button_text_is_classified(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        greeting = await client.collect()
        book = greeting.ui[0]["options"][0]["text"]
        live_server.llm.extend(Say("How can I help?"), Say("Sure."))
        await client.send_text("hello")  # retires the menu buttons
        await client.collect()
        await client.send_text(book)
        await client.collect()
        assert len(live_server.classifier.calls) == 2
