"""Scripted LLMs: a Pipecat LLM service for the pipeline, and a StructuredLLM for side calls."""

from __future__ import annotations

import asyncio
import itertools
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pipecat.frames.frames import (
    Frame,
    FunctionCallFromLLM,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService
from pipecat.services.settings import LLMSettings

from clinic_bot.domain.errors import ErrorCode, Unavailable


@dataclass(frozen=True)
class Say:
    text: str


@dataclass(frozen=True)
class Call:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Fail:
    """The provider errors (e.g. a 429) instead of answering."""

    error: str = "429 rate limited"


Step = Say | Call | Fail | Callable[[list[dict[str, Any]]], "Say | Call | Fail"]


class ScriptedLLMService(LLMService):
    """Each inference consumes the next scripted step and records what it saw."""

    def __init__(self, steps: Sequence[Step] = (), *, delay_s: float = 0.0) -> None:
        super().__init__(
            settings=LLMSettings(
                model="scripted",
                system_instruction=None,
                temperature=None,
                max_tokens=None,
                top_p=None,
                top_k=None,
                frequency_penalty=None,
                presence_penalty=None,
                seed=None,
                filter_incomplete_user_turns=False,
                user_turn_completion_config=None,
            )
        )
        self.steps = list(steps)
        self.calls: list[str] = []
        self.tools_seen: list[list[str]] = []
        self.delay_s = delay_s
        self.summaries = 0
        self._ids = itertools.count(1)

    def extend(self, *steps: Step) -> None:
        self.steps.extend(steps)

    async def run_inference(
        self,
        context: Any,
        max_tokens: int | None = None,
        system_instruction: str | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> str | None:
        """Used by Flows for RESET_WITH_SUMMARY."""
        self.summaries += 1
        return "The patient finished a task with the front desk assistant."

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if not isinstance(frame, LLMContextFrame):
            await self.push_frame(frame, direction)
            return
        messages = list(frame.context.get_messages())
        tools = frame.context.tools
        self.tools_seen.append([t.name for t in getattr(tools, "standard_tools", [])])
        await self.push_frame(LLMFullResponseStartFrame())
        if self.steps:
            step = self.steps.pop(0)
            action = step(messages) if callable(step) else step
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            if isinstance(action, Fail):
                await self.push_error(error_msg=action.error)
            elif isinstance(action, Say):
                await self.push_frame(LLMTextFrame(action.text))
            else:
                self.calls.append(action.name)
                call = FunctionCallFromLLM(
                    function_name=action.name,
                    tool_call_id=f"call_{next(self._ids)}",
                    arguments=action.args,
                    context=frame.context,
                )
                await self.run_function_calls([call])
        await self.push_frame(LLMFullResponseEndFrame())


def last_tool_result(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("role") == "tool":
            content = message.get("content")
            return json.loads(content) if isinstance(content, str) else dict(content or {})
    return {}


class FakeStructuredLLM:
    """Classifier/mapper stand-in: first keyword match wins, else ``default``."""

    def __init__(self, rules: dict[str, str] | None = None, default: str = "NONE") -> None:
        self.rules = rules or {}
        self.default = default
        self.calls: list[str] = []
        self.fail_with: Exception | None = None
        self.delay_s = 0.0
        self.written = "The patient chatted with the front desk."

    async def classify(self, system: str, user: str, labels: Sequence[str]) -> tuple[str, str]:
        self.calls.append(user)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.fail_with is not None:
            raise self.fail_with
        lowered = user.lower().split("patient:")[-1]
        for keyword, label in self.rules.items():
            if keyword in lowered and label in labels:
                return label, f"matched {keyword}"
        if self.default not in labels:
            raise Unavailable(ErrorCode.BUSY, "fake default not in labels")
        return self.default, "default"

    async def write(self, system: str, user: str) -> str:
        self.calls.append(user)
        if self.fail_with is not None:
            raise self.fail_with
        return self.written
