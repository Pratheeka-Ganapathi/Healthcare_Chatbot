"""LLM-facing schemas and the shared wrapper enforce the authorisation invariants."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pipecat.flows import NO_RESPONSE

from clinic_bot.container import FUNCTION_MODULES
from clinic_bot.conversation.registry import FunctionRegistry, HandlerContext, llm_parameters
from clinic_bot.conversation.result import UIPayload
from clinic_bot.conversation.state import FlowState
from clinic_bot.domain.enums import GuardrailLabel
from clinic_bot.services.guardrails.base import Verdict

registry = FunctionRegistry.from_modules(*FUNCTION_MODULES)
FORBIDDEN = {"patient_id", "fee", "visit_type", "followup_fee", "price"}


def test_expected_functions_are_declared() -> None:
    assert set(registry.names()) >= {
        "route_intent",
        "verify_patient",
        "list_doctors",
        "choose_doctor",
        "check_followup",
        "set_same_issue",
        "submit_intake",
        "get_free_slots",
        "find_alternatives",
        "select_slot",
        "confirm_booking",
        "list_appointments",
        "cancel_appointment",
        "reschedule_appointment",
        "answer_faq",
        "request_human",
        "register_patient",
    }


@pytest.mark.parametrize("name", registry.names())
def test_no_function_takes_patient_id_fee_or_visit_type(name: str) -> None:
    spec = registry._specs[name]
    properties, _ = llm_parameters(spec.args)
    assert not FORBIDDEN & set(properties)


def test_confirm_booking_takes_no_arguments() -> None:
    properties, required = llm_parameters(registry._specs["confirm_booking"].args)
    assert properties == {} and required == []


class RecordingIO:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.ui_sent: list[UIPayload] = []

    async def say(self, text: str) -> None:
        self.said.append(text)

    async def ui(self, payload: UIPayload) -> None:
        self.ui_sent.append(payload)

    async def add_user_context(self, text: str) -> None: ...

    async def set_node(self, config: Any) -> None: ...


def ctx(state: FlowState) -> HandlerContext:
    return HandlerContext(
        state,
        services=None,
        messages=None,
        io=RecordingIO(),
        nodes=None,
        record_span=lambda *_: None,
    )  # type: ignore[arg-type]


async def test_ids_not_offered_are_rejected() -> None:
    state = FlowState("s", verified_patient_id=5, selected_doctor_id=1)
    state.offered_slots = {10: 1}
    result, nxt = await registry.invoke("select_slot", {"slot_id": 99}, ctx(state))
    assert result == {"ok": False, "error": "INVALID_CHOICE"} and nxt is None
    result, _ = await registry.invoke("choose_doctor", {"doctor_id": 7}, ctx(state))
    assert result["error"] == "INVALID_CHOICE"


async def test_bad_arguments_are_invalid() -> None:
    result, _ = await registry.invoke("select_slot", {"slot_id": "abc"}, ctx(FlowState("s")))
    assert result == {"ok": False, "error": "INVALID"}


async def test_no_patient_data_before_verification() -> None:
    result, _ = await registry.invoke(
        "submit_intake", {"chief_complaint": "rash"}, ctx(FlowState("s"))
    )
    assert result["error"] == "NOT_VERIFIED"


async def test_handlers_wait_for_the_verdict_and_stop_on_a_block() -> None:
    state = FlowState("s", verified_patient_id=5)
    state.offered_slots = {10: 1}
    state.verdict = asyncio.get_running_loop().create_future()
    call = asyncio.create_task(registry.invoke("select_slot", {"slot_id": 10}, ctx(state)))
    await asyncio.sleep(0.05)
    assert not call.done() and state.selected_slot_id is None
    state.verdict.set_result(Verdict(GuardrailLabel.MEDICATION, "classifier"))
    result, nxt = await call
    assert result["error"] == "BLOCKED" and nxt is NO_RESPONSE and state.selected_slot_id is None


async def test_handlers_go_ahead_on_an_advisory_verdict() -> None:
    state = FlowState("s", verified_patient_id=5)
    state.offered_slots = {10: 1}
    state.verdict = asyncio.get_running_loop().create_future()
    state.verdict.set_result(Verdict(GuardrailLabel.EMERGENCY, "classifier"))
    handler_ctx = HandlerContext(
        state,
        services=None,
        messages=KeyCatalog(),
        io=RecordingIO(),
        nodes=None,
        record_span=lambda *_: None,
    )  # type: ignore[arg-type]
    result, _ = await registry.invoke("select_slot", {"slot_id": 10}, handler_ctx)
    assert result["ok"] is True and state.selected_slot_id == 10


class KeyCatalog:
    def get(self, key: str, **_: object) -> str:
        return key


async def test_check_followup_failure_does_not_move_on() -> None:
    state = FlowState("s", verified_patient_id=5)  # no doctor chosen yet
    result, nxt = await registry.invoke("check_followup", {}, ctx(state))
    assert result["ok"] is False and nxt is None
