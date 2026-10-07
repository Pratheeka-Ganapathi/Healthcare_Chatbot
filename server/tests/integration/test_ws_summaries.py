"""A verified chat leaves a summary on the patient's record once the socket closes."""

from __future__ import annotations

import asyncio

from tests.fakes.llm import Call, Say
from tests.fakes.ws_client import RtviClient
from tests.integration.conftest import LiveServer, query


async def _summaries(server: LiveServer) -> list[tuple[int, str, str]]:
    rows = await query(server, "SELECT patient_id, session_id, summary FROM chat_summaries")
    return [(r["patient_id"], r["session_id"], r["summary"]) for r in rows]


async def test_chat_summary_is_saved_for_the_patient_after_the_chat(
    live_server: LiveServer,
) -> None:
    live_server.summarizer.written = "Sanjay asked to book for a rash."
    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(
            Call("route_intent", {"intent": "book", "complaint": "rash"}),
            Say("Please share your mobile number and date of birth."),
        )
        await client.send_text("I want to book for a rash")
        await client.collect()
        live_server.llm.extend(
            Call("verify_patient", {"phone": "9000000005", "dob": "03/03/1995"}),
            Say("Thanks Sanjay. Is the rash spreading?"),
        )
        await client.send_text("9000000005, 3 March 1995")
        await client.collect()

    for _ in range(100):
        rows = await _summaries(live_server)
        if rows:
            break
        await asyncio.sleep(0.05)
    assert [(r[0], r[2]) for r in rows] == [(5, "Sanjay asked to book for a rash.")]
    transcript = live_server.summarizer.calls[-1]
    assert "Patient: I want to book for a rash" in transcript
    assert "Assistant: Thanks Sanjay. Is the rash spreading?" in transcript


async def test_unverified_chat_leaves_no_summary(live_server: LiveServer) -> None:
    async with RtviClient(live_server.url) as client:
        await client.collect()
        live_server.llm.extend(Say("Our clinic opens at 9 am."))
        await client.send_text("hi")
        await client.collect()
    await asyncio.sleep(0.3)
    assert await _summaries(live_server) == []
    assert live_server.summarizer.calls == []
