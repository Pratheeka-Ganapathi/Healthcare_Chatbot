"""OutputGate releases each turn's text only on that turn's own verdict."""

from __future__ import annotations

import asyncio

from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from clinic_bot.conversation.state import FlowState
from clinic_bot.domain.enums import GuardrailLabel
from clinic_bot.pipeline.processors.output_gate import OutputGateProcessor
from clinic_bot.pipeline.processors.turn_metrics import TurnMetrics
from clinic_bot.services.guardrails.base import Verdict


class CapturingGate(OutputGateProcessor):
    def __init__(self, state: FlowState) -> None:
        super().__init__(state, TurnMetrics())
        self.out: list[str] = []

    async def push_frame(
        self, frame: Frame, direction: FrameDirection = FrameDirection.DOWNSTREAM
    ) -> None:
        if isinstance(frame, LLMTextFrame):
            self.out.append(frame.text)


async def respond(gate: CapturingGate, text: str) -> None:
    for frame in (LLMFullResponseStartFrame(), LLMTextFrame(text), LLMFullResponseEndFrame()):
        await gate._gate(frame)


async def test_each_turn_waits_for_its_own_verdict() -> None:
    state = FlowState("s")
    gate = CapturingGate(state)
    loop = asyncio.get_running_loop()
    first: asyncio.Future[Verdict] = loop.create_future()
    second: asyncio.Future[Verdict] = loop.create_future()
    state.verdict = first
    await respond(gate, "turn one")
    state.verdict = second
    await respond(gate, "turn two")
    first.set_result(Verdict.none("classifier"))
    await asyncio.sleep(0.05)
    assert gate.out == ["turn one"]
    second.set_result(Verdict(GuardrailLabel.MEDICATION, "classifier"))
    await asyncio.sleep(0.05)
    assert gate.out == ["turn one"]


async def test_advisory_verdict_releases_the_reply() -> None:
    state = FlowState("s")
    gate = CapturingGate(state)
    state.verdict = asyncio.get_running_loop().create_future()
    await respond(gate, "Dr. Rao is free tomorrow.")
    assert gate.out == []
    state.verdict.set_result(Verdict(GuardrailLabel.EMERGENCY, "classifier"))
    await asyncio.sleep(0.05)
    assert gate.out == ["Dr. Rao is free tomorrow."]


async def test_fixed_text_is_never_gated() -> None:
    state = FlowState("s")
    state.verdict = asyncio.get_running_loop().create_future()
    gate = CapturingGate(state)
    await gate.emit_fixed("Call 108")
    assert gate.out == ["Call 108"]
