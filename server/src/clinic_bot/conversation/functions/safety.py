"""Handoff, callbacks and the fixed responses to guardrail verdicts.

The guardrail processor calls ``apply_verdict`` and ``handle_terminal_input``; the LLM can
call ``request_human``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from clinic_bot.conversation.registry import HandlerContext, llm_function
from clinic_bot.conversation.result import ToolResult
from clinic_bot.conversation.state import FlowState
from clinic_bot.domain.enums import CallbackPriority, GuardrailLabel
from clinic_bot.services.guardrails.base import Verdict

SUMMARY_TURNS = 6


def callback_summary(state: FlowState, reason: str) -> str:
    """Built server-side from state + the last few turns (never by the LLM)."""
    parts = [f"Reason: {reason}", f"Step: {state.current_node}"]
    if state.patient:
        parts.append(f"Patient: {state.patient.name} (verified)")
    else:
        parts.append("Patient: not verified")
    if state.intake:
        parts.append(f"Complaint: {state.intake.chief_complaint}")
    recent = state.turns[-SUMMARY_TURNS:]
    parts.extend(f"{t['role']}: {t['text']}" for t in recent)
    return "\n".join(parts)


async def _handoff(ctx: HandlerContext, reason: str, priority: CallbackPriority) -> ToolResult:
    state = ctx.state
    callback = await ctx.services.callbacks.create(
        state.verified_patient_id, reason, callback_summary(state, reason), priority
    )
    state.handoff_ticket = callback.ticket()
    return ToolResult.success({"ticket": state.handoff_ticket})


class RequestHumanArgs(BaseModel):
    reason: str = Field(description="Short reason the patient needs the front desk")


@llm_function(
    name="request_human",
    description="Ask the front desk to call the patient back.",
    args=RequestHumanArgs,
    transition=lambda r, _s: "handoff" if r.ok else None,
)
async def request_human(args: RequestHumanArgs, ctx: HandlerContext) -> ToolResult:
    return await _handoff(ctx, args.reason, CallbackPriority.NORMAL)


_FIXED_REPLY = {
    GuardrailLabel.EMERGENCY: "emergency.note",
    GuardrailLabel.SELF_HARM: "self_harm.note",
    GuardrailLabel.MEDICATION: "medication.refusal",
    GuardrailLabel.OFF_TOPIC: "off_topic",
}


async def apply_verdict(ctx: HandlerContext, verdict: Verdict) -> None:
    """Fixed text for a flagged message from either layer. Never changes the node.

    Emergency and self-harm get a soft line and the bot's normal reply follows;
    medication and off-topic replace the reply (the OutputGate drops it).
    """
    state = ctx.state
    state.guardrail_events.append(
        {"label": verdict.label.value, "source": verdict.source, "node": state.current_node}
    )
    if key := _FIXED_REPLY.get(verdict.label):
        await ctx.io.say(ctx.messages.get(key))


async def handle_terminal_input(ctx: HandlerContext) -> None:
    await ctx.io.say(ctx.messages.get("handoff.ended"))
