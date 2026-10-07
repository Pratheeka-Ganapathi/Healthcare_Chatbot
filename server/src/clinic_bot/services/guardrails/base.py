"""Guard abstraction and the verdict value object."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from clinic_bot.domain.enums import GuardrailLabel

BLOCKING_LABELS = frozenset({GuardrailLabel.MEDICATION, GuardrailLabel.OFF_TOPIC})
ADVISORY_LABELS = frozenset({GuardrailLabel.EMERGENCY, GuardrailLabel.SELF_HARM})


# "button": the message was a button the server itself offered, so Layer 2 was skipped.
VerdictSource = Literal["regex", "classifier", "default", "button"]


@dataclass(frozen=True, slots=True)
class Verdict:
    label: GuardrailLabel
    source: VerdictSource
    reason: str = ""

    @property
    def blocks(self) -> bool:
        """Medication and off-topic replace the bot's reply with a fixed one."""
        return self.label in BLOCKING_LABELS

    @property
    def advisory(self) -> bool:
        """Emergency and self-harm add a soft safety line; the chat carries on as usual."""
        return self.label in ADVISORY_LABELS

    @classmethod
    def none(cls, source: VerdictSource = "default") -> Verdict:
        return cls(GuardrailLabel.NONE, source)


@dataclass(frozen=True, slots=True)
class GuardContext:
    node: str
    last_bot_message: str = ""


class Guard(ABC):
    @abstractmethod
    async def check(self, text: str, ctx: GuardContext) -> Verdict: ...
