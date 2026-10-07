"""GuardrailInput: every user message passes here before the LLM.

Layer 1 (regex) runs synchronously. A medication or off-topic hit never reaches the LLM.
An emergency or self-harm hit adds a soft safety line and the message carries on. The
message then goes to the LLM while Layer 2 (classifier) runs in parallel; the OutputGate
and the function handlers wait for its verdict. A click on a button the server offered
(its exact text) skips Layer 2: that text is server-written, so classifying it only spends
rate limit.
"""

from __future__ import annotations

import asyncio
import hashlib
import time

import structlog
from pipecat.frames.frames import ErrorFrame, Frame, LLMMessagesAppendFrame, LLMRunFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from clinic_bot.conversation.functions.safety import apply_verdict, handle_terminal_input
from clinic_bot.conversation.nodes.factory import TERMINAL_NODES
from clinic_bot.conversation.registry import HandlerContext
from clinic_bot.domain.enums import GuardrailLabel
from clinic_bot.pipeline.processors.turn_metrics import TurnMetrics
from clinic_bot.services.guardrails.base import GuardContext, Verdict
from clinic_bot.services.guardrails.pipeline import GuardPipeline

log = structlog.get_logger(__name__)
LLM_RETRY_BACKOFF_S = 1.5


class TrustedContextFrame(LLMMessagesAppendFrame):
    """Context the server adds itself (e.g. replaying a held message); never re-guarded."""


def _is_user_message(frame: Frame) -> bool:
    return (
        type(frame) is LLMMessagesAppendFrame
        and len(frame.messages) == 1
        and isinstance(frame.messages[0], dict)
        and frame.messages[0].get("role") == "user"
    )


class GuardrailInputProcessor(FrameProcessor):
    def __init__(
        self, ctx: HandlerContext, guards: GuardPipeline, max_chars: int, metrics: TurnMetrics
    ) -> None:
        super().__init__(name="GuardrailInput")
        self._ctx, self._guards, self._max, self._turn_metrics = ctx, guards, max_chars, metrics
        self._tasks: set[asyncio.Task[None]] = set()
        self._retried = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction is FrameDirection.DOWNSTREAM and _is_user_message(frame):
            assert isinstance(frame, LLMMessagesAppendFrame)
            await self._on_user_message(frame)
            return
        if (
            isinstance(frame, ErrorFrame)
            and direction is FrameDirection.UPSTREAM
            and not frame.fatal
        ):
            self._on_llm_error(frame)
        await self.push_frame(frame, direction)

    def _on_llm_error(self, frame: ErrorFrame) -> None:
        """SPEC 1, rate limits: one retry with backoff, then the fixed "busy" message."""
        log.warning("llm_error", error=frame.error[:200], retried=self._retried)
        task = asyncio.create_task(self._retry_or_busy(retry=not self._retried))
        self._retried = True
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _retry_or_busy(self, retry: bool) -> None:
        if retry:
            await asyncio.sleep(LLM_RETRY_BACKOFF_S)
            await self.push_frame(LLMRunFrame(), FrameDirection.DOWNSTREAM)
        else:
            await self._ctx.io.say(self._ctx.messages.get("busy"))

    async def _on_user_message(self, frame: LLMMessagesAppendFrame) -> None:
        state, ctx = self._ctx.state, self._ctx
        text = str(frame.messages[0].get("content", "")).strip()
        if not text:
            return
        self._turn_metrics.user_turn()
        self._retried = False
        if len(text) > self._max:
            text = text[: self._max]
            await ctx.io.say(ctx.messages.get("input_truncated"))
        state.add_turn("user", text)
        pressed = state.take_button(text)
        log.info("user_message", node=state.current_node, text_hash=_hash(text), button=pressed)
        if state.current_node in TERMINAL_NODES:
            state.verdict = _resolved(Verdict.none("default"))
            await handle_terminal_input(ctx)
            return
        started = time.perf_counter()
        verdict = self._guards.precheck(text)
        advised = verdict.label if verdict.advisory else None
        if advised is not None:
            log.info("guardrail", label=verdict.label, source="regex", node=state.current_node)
            await apply_verdict(ctx, verdict)
            verdict = self._guards.blocking(text)
        self._turn_metrics.record("regex", (time.perf_counter() - started) * 1000)
        if verdict.blocks:
            state.verdict = _resolved(verdict)
            log.info("guardrail", label=verdict.label, source="regex", node=state.current_node)
            await apply_verdict(ctx, verdict)
            return
        if pressed and advised is None:
            state.verdict = _resolved(Verdict.none("button"))
            frame.messages = [{"role": "user", "content": text}]
            await self.push_frame(frame, FrameDirection.DOWNSTREAM)
            return
        await self._run_with_classifier(frame, text, advised)

    async def _run_with_classifier(
        self, frame: LLMMessagesAppendFrame, text: str, advised: GuardrailLabel | None
    ) -> None:
        state = self._ctx.state
        future: asyncio.Future[Verdict] = asyncio.get_running_loop().create_future()
        state.verdict = future
        guard_ctx = GuardContext(state.current_node, _previous_bot_message(state.turns))
        started = time.perf_counter()
        classifier = self._guards.start_classifier(
            text, guard_ctx, on_failure=lambda why: log.warning("classifier_failed", reason=why)
        )
        frame.messages = [{"role": "user", "content": text}]
        await self.push_frame(frame, FrameDirection.DOWNSTREAM)
        task = asyncio.create_task(self._settle(future, classifier, started, advised))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _settle(
        self,
        future: asyncio.Future[Verdict],
        classifier: asyncio.Task[Verdict],
        started: float,
        advised: GuardrailLabel | None,
    ) -> None:
        verdict = Verdict.none("default")
        try:
            verdict = await classifier
            if verdict.advisory and verdict.label is not advised:
                # Before the verdict resolves, so the soft line comes ahead of the reply.
                self._log_verdict(verdict)
                await apply_verdict(self._ctx, verdict)
        finally:  # whatever happens, the turn's waiters must not hang
            self._turn_metrics.record("classifier", (time.perf_counter() - started) * 1000)
            self._turn_metrics.classifier_done()
            if not future.done():
                future.set_result(verdict)
        if verdict.blocks:
            self._log_verdict(verdict)
            await self.broadcast_interruption()
            await apply_verdict(self._ctx, verdict)

    def _log_verdict(self, verdict: Verdict) -> None:
        node = self._ctx.state.current_node
        log.info("guardrail", label=verdict.label, source="classifier", node=node)

    async def cleanup(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await super().cleanup()


def _resolved(verdict: Verdict) -> asyncio.Future[Verdict]:
    future: asyncio.Future[Verdict] = asyncio.get_running_loop().create_future()
    future.set_result(verdict)
    return future


def _previous_bot_message(turns: list[dict[str, str]]) -> str:
    """The bot message before the user message just added."""
    return next((t["text"] for t in reversed(turns[:-1]) if t["role"] == "bot"), "")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]
