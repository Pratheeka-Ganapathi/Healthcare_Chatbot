"""PipelineBuilder: one Pipecat pipeline + FlowManager per WebSocket connection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import WebSocket
from pipecat.flows import FlowManager, NodeConfig
from pipecat.frames.frames import (
    Frame,
    OutputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
)
from pipecat.observers.base_observer import BaseObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frameworks.rtvi import RTVIObserverParams, RTVIProcessor
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.llm_service import LLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

from clinic_bot.conversation.registry import HandlerContext
from clinic_bot.conversation.result import UIPayload
from clinic_bot.conversation.state import FlowState
from clinic_bot.pipeline.processors.guardrail_input import (
    GuardrailInputProcessor,
    TrustedContextFrame,
)
from clinic_bot.pipeline.processors.output_gate import OutputGateProcessor
from clinic_bot.pipeline.processors.turn_metrics import TurnMetrics, TurnMetricsObserver
from clinic_bot.pipeline.processors.ui_emitter import UIEmitterProcessor
from clinic_bot.services.guardrails.pipeline import GuardPipeline


class MessageOnlySerializer(ProtobufFrameSerializer):
    """Text v1 sends only RTVI messages. The widget reads bot text from them; raw text,
    audio and interruption frames would only be rejected by its deserializer.
    """

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if not isinstance(frame, OutputTransportMessageFrame | OutputTransportMessageUrgentFrame):
            return None
        return await super().serialize(frame)


class PipelineIO:
    """ConversationIO for one session, backed by its processors and FlowManager."""

    def __init__(self, gate: OutputGateProcessor, ui: UIEmitterProcessor, state: FlowState) -> None:
        self._gate, self._ui, self._state = gate, ui, state
        self.worker: PipelineWorker | None = None
        self.flow: FlowManager | None = None

    async def say(self, text: str) -> None:
        await self._gate.emit_fixed(text)

    async def ui(self, payload: UIPayload) -> None:
        self._state.offer_buttons(payload)
        await self._ui.emit(payload)

    async def add_user_context(self, text: str) -> None:
        assert self.worker is not None
        frame = TrustedContextFrame(messages=[{"role": "user", "content": text}], run_llm=False)
        await self.worker.queue_frame(frame)

    async def set_node(self, config: NodeConfig) -> None:
        assert self.flow is not None
        await self.flow.set_node_from_config(config)


@dataclass
class BuiltPipeline:
    worker: PipelineWorker
    flow: FlowManager
    rtvi: RTVIProcessor
    transport: BaseTransport
    metrics: TurnMetrics


class PipelineBuilder:
    def __init__(
        self, guards: GuardPipeline, max_input_chars: int, allowed_origins: list[str]
    ) -> None:
        self._guards, self._max_chars, self._origins = guards, max_input_chars, allowed_origins

    def transport(self, websocket: WebSocket) -> FastAPIWebsocketTransport:
        params = FastAPIWebsocketParams(
            serializer=MessageOnlySerializer(),
            audio_in_enabled=False,
            audio_out_enabled=False,
            allowed_origins=self._origins,
        )
        return FastAPIWebsocketTransport(websocket=websocket, params=params)

    def build(
        self,
        transport: BaseTransport,
        llm: LLMService,
        state: FlowState,
        ctx_for: Callable[[PipelineIO, TurnMetrics], HandlerContext],
    ) -> BuiltPipeline:
        metrics = TurnMetrics()
        pair = LLMContextAggregatorPair(LLMContext())
        rtvi = RTVIProcessor()
        gate = OutputGateProcessor(state, metrics)
        ui = UIEmitterProcessor()
        io = PipelineIO(gate, ui, state)
        ctx = ctx_for(io, metrics)
        guard = GuardrailInputProcessor(ctx, self._guards, self._max_chars, metrics)
        pipeline = Pipeline(
            [
                transport.input(),
                rtvi,
                guard,
                pair.user(),
                llm,
                gate,
                ui,
                pair.assistant(),
                transport.output(),
            ]
        )
        worker = PipelineWorker(
            pipeline,
            params=PipelineParams(enable_metrics=False),
            observers=[_rtvi_observer(rtvi, llm), TurnMetricsObserver(metrics, llm)],
            idle_timeout_secs=None,
        )
        flow = FlowManager(llm=llm, context_aggregator=pair, worker=worker, transport=transport)
        io.worker, io.flow = worker, flow
        return BuiltPipeline(worker, flow, rtvi, transport, metrics)


def _rtvi_observer(rtvi: RTVIProcessor, llm: LLMService) -> BaseObserver:
    """The LLM is ignored as a source: bot text reaches the client only once the
    OutputGate re-emits it after the guardrail verdict."""
    return rtvi.create_rtvi_observer(
        params=RTVIObserverParams(
            ignored_sources=[llm],
            bot_output_enabled=False,
            bot_tts_enabled=False,
            user_llm_enabled=False,
            metrics_enabled=False,
        )
    )
