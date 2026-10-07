"""OutputGate: holds the main LLM's text until the turn's guardrail verdict resolves.

On ``NONE`` the held frames are released (as fresh frames, so the RTVI observer reports
them from here and not from the LLM, which it ignores). On any other label they are
dropped and never reach the assistant aggregator, so they stay out of the context.
Fixed bot text (``emit_fixed``) is never gated.
"""

from __future__ import annotations

import asyncio

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from clinic_bot.conversation.state import FlowState
from clinic_bot.pipeline.processors.turn_metrics import TurnMetrics
from clinic_bot.services.guardrails.base import Verdict

_GATED = (LLMFullResponseStartFrame, LLMTextFrame, LLMFullResponseEndFrame)


class OutputGateProcessor(FrameProcessor):
    def __init__(self, state: FlowState, metrics: TurnMetrics) -> None:
        super().__init__(name="OutputGate")
        self._state, self._turn_metrics = state, metrics
        self._held: list[tuple[asyncio.Future[Verdict], Frame]] = []
        self._waiter: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._open_response = False
        self._text: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InterruptionFrame):
            self._held.clear()
            await self.push_frame(frame, direction)
        elif isinstance(frame, _GATED) and direction is FrameDirection.DOWNSTREAM:
            await self._gate(frame)
        else:
            await self.push_frame(frame, direction)

    async def emit_fixed(self, text: str) -> None:
        """Send fixed text as one complete bot response."""
        async with self._lock:
            await self._emit(LLMFullResponseStartFrame())
            await self._emit(LLMTextFrame(text))
            await self._emit(LLMFullResponseEndFrame())

    async def _gate(self, frame: Frame) -> None:
        verdict = self._state.verdict
        if verdict is None or (verdict.done() and not self._held):
            if verdict is None or not verdict.result().blocks:
                async with self._lock:
                    await self._emit(_fresh(frame))
            return
        # Each held frame keeps the verdict of the turn that produced it, so a later
        # turn's text is never released on an earlier turn's verdict.
        self._held.append((verdict, frame))
        if self._waiter is None or self._waiter.done():
            self._waiter = asyncio.create_task(self._release_in_order())

    async def _release_in_order(self) -> None:
        while self._held:
            verdict, frame = self._held[0]
            result = await asyncio.shield(verdict)
            async with self._lock:
                if self._held and self._held[0][1] is frame:
                    self._held.pop(0)
                    if not result.blocks:
                        await self._emit(_fresh(frame))

    async def _emit(self, frame: Frame) -> None:
        if isinstance(frame, LLMFullResponseStartFrame):
            self._open_response, self._text = True, []
        elif isinstance(frame, LLMTextFrame):
            if not self._open_response:
                return
            if not self._text:
                self._turn_metrics.first_text()
            self._text.append(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            if not self._open_response:
                return
            self._open_response = False
            spoken = "".join(self._text).strip()
            if spoken:
                self._state.add_turn("bot", spoken)
        await self.push_frame(frame, FrameDirection.DOWNSTREAM)


def _fresh(frame: Frame) -> Frame:
    if isinstance(frame, LLMTextFrame):
        return LLMTextFrame(frame.text)
    if isinstance(frame, LLMFullResponseStartFrame):
        return LLMFullResponseStartFrame()
    return LLMFullResponseEndFrame()
