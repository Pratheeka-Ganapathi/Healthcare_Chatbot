"""FunctionRegistry: one decorator per LLM-facing function, one wrapper for all of them.

The wrapper runs the same steps for every call (SPEC 16.4): validate args, await the
guardrail verdict, call the handler, map domain errors, push UI, record a span, and
resolve the transition to the next node.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING, Any

import structlog
from pipecat.flows import NO_RESPONSE, FlowManager, FlowsFunctionSchema, NodeConfig
from pydantic import BaseModel, ValidationError

from clinic_bot.conversation.result import ToolResult
from clinic_bot.domain.errors import DomainError, ErrorCode

if TYPE_CHECKING:
    from clinic_bot.conversation.io import ConversationIO
    from clinic_bot.conversation.nodes.factory import NodeFactory
    from clinic_bot.conversation.state import FlowState
    from clinic_bot.ports.messages import MessageCatalog
    from clinic_bot.services.booking import BookingService
    from clinic_bot.services.callback import CallbackService
    from clinic_bot.services.directory import DoctorDirectory, SpecialtyMapper
    from clinic_bot.services.faq import FaqService
    from clinic_bot.services.guardrails.regex_guard import RegexGuard
    from clinic_bot.services.intake import ChecklistRetriever
    from clinic_bot.services.scheduling import SchedulingService
    from clinic_bot.services.verification import VerificationService

log = structlog.get_logger(__name__)

Transition = Callable[[ToolResult, "FlowState"], str | None]
SpanRecorder = Callable[[str, float], None]


class NoArgs(BaseModel):
    pass


@dataclass(frozen=True, slots=True)
class Services:
    verification: VerificationService
    directory: DoctorDirectory
    mapper: SpecialtyMapper
    scheduling: SchedulingService
    booking: BookingService
    checklists: ChecklistRetriever
    faq: FaqService
    callbacks: CallbackService
    regex: RegexGuard


@dataclass(slots=True)
class HandlerContext:
    state: FlowState
    services: Services
    messages: MessageCatalog
    io: ConversationIO
    nodes: NodeFactory
    record_span: SpanRecorder


Handler = Callable[[Any, HandlerContext], Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class FunctionSpec:
    name: str
    description: str
    args: type[BaseModel]
    handler: Handler
    transition: Transition | None


def llm_function[ArgsT: BaseModel](
    *,
    name: str,
    description: str,
    args: type[ArgsT] | None = None,
    transition: Transition | None = None,
) -> Callable[[Callable[[ArgsT, HandlerContext], Awaitable[ToolResult]]], FunctionSpec]:
    """Declare an LLM-facing function. The registry collects the returned specs."""

    def declare(fn: Callable[[ArgsT, HandlerContext], Awaitable[ToolResult]]) -> FunctionSpec:
        return FunctionSpec(name, description, args or NoArgs, fn, transition)

    return declare


class FunctionRegistry:
    def __init__(self, specs: Iterable[FunctionSpec]) -> None:
        self._specs: dict[str, FunctionSpec] = {}
        for spec in specs:
            if spec.name in self._specs:
                raise ValueError(f"function {spec.name} declared twice")
            self._specs[spec.name] = spec

    @classmethod
    def from_modules(cls, *modules: ModuleType) -> FunctionRegistry:
        return cls(
            value
            for module in modules
            for value in vars(module).values()
            if isinstance(value, FunctionSpec)
        )

    def names(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def schemas(self, names: Sequence[str], ctx: HandlerContext) -> list[FlowsFunctionSchema]:
        """Flows function schemas for ``names``, bound to one session's context."""
        out: list[FlowsFunctionSchema] = []
        for name in names:
            spec = self._specs[name]
            properties, required = llm_parameters(spec.args)
            out.append(
                FlowsFunctionSchema(
                    name=spec.name,
                    description=spec.description,
                    properties=properties,
                    required=required,
                    handler=self._bind(spec, ctx),
                    cancel_on_interruption=True,
                )
            )
        return out

    def _bind(
        self, spec: FunctionSpec, ctx: HandlerContext
    ) -> Callable[[dict[str, Any], FlowManager], Awaitable[tuple[Any, Any]]]:
        async def run(args: dict[str, Any], _fm: FlowManager) -> tuple[Any, Any]:
            return await self.invoke(spec.name, args, ctx)

        return run

    async def invoke(self, name: str, raw: dict[str, Any], ctx: HandlerContext) -> tuple[Any, Any]:
        """The shared wrapper. Returns ``(result for the LLM, next node | None | NO_RESPONSE)``."""
        spec = self._specs[name]
        try:
            args = spec.args.model_validate(raw)
        except ValidationError:
            return ToolResult.failure(ErrorCode.INVALID).for_llm(), None
        if ctx.state.verdict is not None and (await asyncio.shield(ctx.state.verdict)).blocks:
            return ToolResult.failure(ErrorCode.BLOCKED).for_llm(), NO_RESPONSE
        started = time.perf_counter()
        result = await self._call(spec, args, ctx)
        ctx.record_span(f"tool.{name}", (time.perf_counter() - started) * 1000)
        if result.ui is not None:
            await ctx.io.ui(result.ui)
        log.info("tool", name=name, ok=result.ok, error=result.error, node=ctx.state.current_node)
        return result.for_llm(), await self._next(spec, result, ctx)

    async def _call(self, spec: FunctionSpec, args: BaseModel, ctx: HandlerContext) -> ToolResult:
        try:
            return await spec.handler(args, ctx)
        except DomainError as exc:
            data = {k: str(v) for k, v in exc.data.items() if k != "retryable"}
            return ToolResult.failure(exc.code, data or None)
        except Exception:  # registry boundary: log and degrade safely
            log.exception("tool_failed", name=spec.name)
            await ctx.io.say(ctx.messages.get("internal_error"))
            return ToolResult.failure(ErrorCode.INTERNAL, silent=True)

    async def _next(self, spec: FunctionSpec, result: ToolResult, ctx: HandlerContext) -> Any:
        target = spec.transition(result, ctx.state) if spec.transition else None
        if target is None:
            return NO_RESPONSE if result.silent else None
        try:
            config: NodeConfig = await ctx.nodes.create(target, ctx)
        except DomainError as exc:  # e.g. a busy database while preparing the next node
            log.warning("node_prepare_failed", node=target, error=exc.code)
            await ctx.io.say(ctx.messages.get("busy"))
            return NO_RESPONSE
        except Exception:  # registry boundary: log and degrade safely
            log.exception("node_prepare_crashed", node=target)
            await ctx.io.say(ctx.messages.get("internal_error"))
            return NO_RESPONSE
        return config


def llm_parameters(model: type[BaseModel]) -> tuple[dict[str, Any], list[str]]:
    """Flatten a pydantic model into provider-neutral JSON schema properties."""
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})
    props = {k: _simplify(v, defs) for k, v in schema.get("properties", {}).items()}
    return props, list(schema.get("required", []))


def _simplify(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in node:
        node = {
            **defs[node["$ref"].split("/")[-1]],
            **{k: v for k, v in node.items() if k != "$ref"},
        }
    if "anyOf" in node:
        options = [o for o in node["anyOf"] if o.get("type") != "null"]
        node = {**options[0], **{k: v for k, v in node.items() if k not in ("anyOf", "default")}}
    out: dict[str, Any] = {}
    for key in ("type", "description", "enum", "minimum", "maximum"):
        if key in node:
            out[key] = node[key]
    if node.get("type") == "array" and "items" in node:
        out["items"] = _simplify(node["items"], defs)
    if node.get("type") == "object" and "properties" in node:
        out["properties"] = {k: _simplify(v, defs) for k, v in node["properties"].items()}
        out["required"] = list(node.get("required", []))
    return out
