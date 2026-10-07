from __future__ import annotations

import asyncio

import pytest

from clinic_bot.domain.enums import GuardrailLabel
from clinic_bot.domain.errors import ErrorCode, Unavailable
from clinic_bot.services.guardrails.base import Guard, GuardContext, Verdict
from clinic_bot.services.guardrails.llm_guard import LLMClassifierGuard
from clinic_bot.services.guardrails.pipeline import GuardPipeline
from clinic_bot.services.guardrails.regex_guard import RegexGuard
from tests.fakes.llm import FakeStructuredLLM

regex = RegexGuard()
CTX = GuardContext("pre_talk")


@pytest.mark.parametrize(
    "text",
    [
        "what is the dose of crocin for adults",
        "can I take Dolo 650 with food",
        "should I take my tablets before the fasting test?",
        "is there any side effect of combiflam",
        "what is pantoprazole used for",
        "can you prescribe something for acidity",
    ],
)
def test_medication_refused(text: str) -> None:
    assert regex.precheck(text).label is GuardrailLabel.MEDICATION


@pytest.mark.parametrize(
    "text",
    ["write python code to reverse a string", "tell me a joke", "generate an essay on climate"],
)
def test_off_topic_code_requests(text: str) -> None:
    assert regex.precheck(text).label is GuardrailLabel.OFF_TOPIC


@pytest.mark.parametrize(
    "text", ["I want to book with a skin doctor", "what are your timings", "9000000001, 05/06/1990"]
)
def test_ordinary_messages_pass(text: str) -> None:
    assert regex.precheck(text).label is GuardrailLabel.NONE


def test_priority_self_harm_before_emergency() -> None:
    assert (
        regex.precheck("I want to kill myself, I took an overdose").label
        is GuardrailLabel.SELF_HARM
    )


@pytest.mark.parametrize(
    ("label", "blocks", "advisory"),
    [
        (GuardrailLabel.EMERGENCY, False, True),
        (GuardrailLabel.SELF_HARM, False, True),
        (GuardrailLabel.MEDICATION, True, False),
        (GuardrailLabel.OFF_TOPIC, True, False),
        (GuardrailLabel.NONE, False, False),
    ],
)
def test_only_medication_and_off_topic_block(
    label: GuardrailLabel, blocks: bool, advisory: bool
) -> None:
    verdict = Verdict(label, "classifier")
    assert (verdict.blocks, verdict.advisory) == (blocks, advisory)


def test_blocking_check_still_catches_medication_after_a_red_flag() -> None:
    text = "I have chest pain, can I take Dolo 650?"
    assert regex.precheck(text).label is GuardrailLabel.EMERGENCY
    assert regex.blocking(text).label is GuardrailLabel.MEDICATION
    assert regex.blocking("I have chest pain since morning").label is GuardrailLabel.NONE


async def test_classifier_maps_label() -> None:
    guard = LLMClassifierGuard(FakeStructuredLLM({"elephant": "EMERGENCY"}))
    verdict = await guard.check("an elephant on my chest", CTX)
    assert verdict == Verdict(GuardrailLabel.EMERGENCY, "classifier", "matched elephant")


class SlowGuard(Guard):
    async def check(self, text: str, ctx: GuardContext) -> Verdict:
        await asyncio.sleep(1)
        return Verdict(GuardrailLabel.EMERGENCY, "classifier")


async def test_classifier_timeout_defaults_to_none() -> None:
    failures: list[str] = []
    pipeline = GuardPipeline(regex, SlowGuard(), timeout_s=0.05)
    verdict = await pipeline.start_classifier("hi", CTX, failures.append)
    assert verdict == Verdict.none("default") and failures


async def test_classifier_error_defaults_to_none() -> None:
    llm = FakeStructuredLLM()
    llm.fail_with = Unavailable(ErrorCode.BUSY, "429", retryable=True)
    pipeline = GuardPipeline(regex, LLMClassifierGuard(llm), timeout_s=1)
    assert (await pipeline.start_classifier("hi", CTX)).label is GuardrailLabel.NONE
