"""BaseNode: template method that turns a node definition into a Flows NodeConfig."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from pipecat.flows import (
    ActionConfig,
    ContextStrategy,
    ContextStrategyConfig,
    FlowManager,
    NodeConfig,
)

from clinic_bot.conversation.prompts import SUMMARY_PROMPT, PromptLibrary
from clinic_bot.ports.messages import MessageCatalog

if TYPE_CHECKING:
    from clinic_bot.conversation.registry import FunctionRegistry, HandlerContext
    from clinic_bot.conversation.state import FlowState

GLOBAL_FUNCTIONS: tuple[str, ...] = ("answer_faq", "request_human")
FAQ_DETOUR = (
    "If the patient asks an unrelated question about the clinic, call answer_faq, answer only "
    "from its result, then return to this step and say where you were."
)
RESET_WITH_SUMMARY = ContextStrategyConfig(
    strategy=ContextStrategy.RESET_WITH_SUMMARY, summary_prompt=SUMMARY_PROMPT
)


class BaseNode(ABC):
    name: ClassVar[str]
    functions: ClassVar[tuple[str, ...]] = ()
    include_globals: ClassVar[bool] = True

    def __init__(
        self, prompts: PromptLibrary, registry: FunctionRegistry, messages: MessageCatalog
    ) -> None:
        self._prompts, self._registry, self._messages = prompts, registry, messages

    async def prepare(self, ctx: HandlerContext) -> None:
        """Load whatever the task text needs into state (async I/O happens here)."""
        return None

    async def on_enter(self, ctx: HandlerContext) -> None:
        """Fixed output shown when the node becomes active."""
        return None

    @abstractmethod
    def task(self, state: FlowState) -> str: ...

    def respond_immediately(self, state: FlowState) -> bool:
        return True

    def context_strategy(self, state: FlowState) -> ContextStrategyConfig | None:
        return None

    def build(self, ctx: HandlerContext) -> NodeConfig:
        state = ctx.state
        names = self.functions + (GLOBAL_FUNCTIONS if self.include_globals else ())
        config: NodeConfig = {
            "name": self.name,
            "role_message": self._prompts.role(),
            "task_messages": [{"role": "system", "content": self._task_text(state)}],
            "functions": list(self._registry.schemas(names, ctx)),
            "pre_actions": [self._enter_action(ctx)],
            "respond_immediately": self.respond_immediately(state),
        }
        if strategy := self.context_strategy(state):
            config["context_strategy"] = strategy
        return config

    def _task_text(self, state: FlowState) -> str:
        text = self.task(state)
        return f"{text}\n\n{FAQ_DETOUR}" if self.include_globals else text

    def _enter_action(self, ctx: HandlerContext) -> ActionConfig:
        async def enter(_action: dict[str, Any], _fm: FlowManager) -> None:
            ctx.state.current_node = self.name
            await self.on_enter(ctx)

        return {"type": f"enter_{self.name}", "handler": enter}


def patient_line(state: FlowState) -> str:
    if state.patient is None:
        return "The patient is not verified yet."
    p = state.patient
    return f"Verified patient: {p.name}, age {p.age}, {p.sex.value}."
