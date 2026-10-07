"""ChatSession: one connection's lifecycle, from client-ready to transcript and summary."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

import structlog
from fastapi import WebSocket
from pipecat.processors.frameworks.rtvi import RTVIProcessor
from pipecat.services.llm_service import LLMService
from pipecat.workers.runner import WorkerRunner

from clinic_bot.conversation.nodes.factory import NodeFactory
from clinic_bot.conversation.registry import HandlerContext, Services
from clinic_bot.conversation.state import FlowState
from clinic_bot.domain.entities import TranscriptRecord
from clinic_bot.pipeline.builder import PipelineBuilder, PipelineIO
from clinic_bot.pipeline.processors.turn_metrics import TurnMetrics
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.messages import MessageCatalog
from clinic_bot.services.chat_summaries import ChatSummaryService
from clinic_bot.services.transcripts import TranscriptWriter

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SessionDeps:
    builder: PipelineBuilder
    llm_factory: Callable[[], LLMService]
    services: Services
    messages: MessageCatalog
    nodes: NodeFactory
    transcripts: TranscriptWriter
    summaries: ChatSummaryService
    clock: Clock


class ChatSession:
    def __init__(self, websocket: WebSocket, deps: SessionDeps) -> None:
        self._ws, self._deps = websocket, deps
        self.state = FlowState(session_id=uuid.uuid4().hex)

    async def run(self) -> None:
        deps = self._deps
        structlog.contextvars.bind_contextvars(session_id=self.state.session_id)
        log_ = log.bind(session_id=self.state.session_id)
        transport = deps.builder.transport(self._ws)
        built = deps.builder.build(transport, deps.llm_factory(), self.state, self._context)

        @built.rtvi.event_handler("on_client_ready")
        async def on_client_ready(rtvi: RTVIProcessor) -> None:
            await rtvi.set_bot_ready()
            try:
                await built.flow.initialize(await deps.nodes.create("greet", self._ctx))
            except Exception:  # session boundary: tell the patient, offer the desk
                log_.exception("flow_start_failed")
                await self._ctx.io.say(deps.messages.get("internal_error"))

        @transport.event_handler("on_client_disconnected")
        async def on_disconnected(_transport: object, _ws: object) -> None:
            await built.worker.cancel()

        log_.info("session_started")
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(built.worker)
        try:
            await runner.run()
        except Exception:  # session boundary: log, never crash the server
            log_.exception("session_failed")
        finally:
            self._finish(built.metrics, log_)

    def _context(self, io: PipelineIO, metrics: TurnMetrics) -> HandlerContext:
        self._ctx = HandlerContext(
            state=self.state,
            services=self._deps.services,
            messages=self._deps.messages,
            io=io,
            nodes=self._deps.nodes,
            record_span=metrics.record,
        )
        return self._ctx

    def _finish(self, metrics: TurnMetrics, log_: structlog.stdlib.BoundLogger) -> None:
        state = self.state
        record = TranscriptRecord(
            session_id=state.session_id,
            patient_id=state.verified_patient_id,
            turns=tuple(state.turns),
            guardrail_events=tuple(state.guardrail_events),
            created_at=self._deps.clock.now(),
        )
        self._deps.transcripts.submit(record)
        self._deps.summaries.submit(record)
        log_.info("session_ended", node=state.current_node, metrics=metrics.summary())
