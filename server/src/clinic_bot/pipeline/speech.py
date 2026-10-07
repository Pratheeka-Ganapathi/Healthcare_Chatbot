"""SpeechSession: voice input for the widget's mic button (SPEC 10.1).

Its own short-lived WebSocket, open only while the mic is on. Audio goes to the STT
service and the transcript goes straight back to the widget, which puts it in the
message box. Nothing here reaches the LLM: the patient reviews the text and sends it
on the chat connection, where the guardrails see it like any typed message.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import structlog
from fastapi import WebSocket
from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    InputAudioRawFrame,
    InputTransportMessageFrame,
    InterimTranscriptionFrame,
    OutputTransportMessageUrgentFrame,
    TranscriptionFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.stt_service import STTService
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.workers.runner import WorkerRunner

from clinic_bot.pipeline.builder import MessageOnlySerializer

log = structlog.get_logger(__name__)

SAMPLE_RATE = 16_000
SPEECH_END = "speech-end"  # widget → server: the mic is off, finish the utterance


def _message(kind: str, **fields: object) -> OutputTransportMessageUrgentFrame:
    return OutputTransportMessageUrgentFrame(message={"type": kind, **fields})


class SpeechControl(FrameProcessor):
    """Before the STT: turns the widget's ``speech-end`` into an end-of-speech signal
    (the STT then finalizes the utterance) and reports STT errors to the widget."""

    def __init__(self) -> None:
        super().__init__(name="SpeechControl")

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputTransportMessageFrame):
            message = frame.message if isinstance(frame.message, dict) else {}
            if message.get("type") == SPEECH_END:
                await self.push_frame(VADUserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
            return
        if isinstance(frame, ErrorFrame) and direction is FrameDirection.UPSTREAM:
            log.warning("stt_error", error=frame.error[:200], fatal=frame.fatal)
            await self.push_frame(_message("speech-error"), FrameDirection.DOWNSTREAM)
        await self.push_frame(frame, direction)


class TranscriptRelay(FrameProcessor):
    """After the STT: transcripts go to the widget as ``{"type": "transcript"}``
    messages and stop here; audio stops here too."""

    def __init__(self) -> None:
        super().__init__(name="TranscriptRelay")

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame | InterimTranscriptionFrame):
            final = isinstance(frame, TranscriptionFrame)
            await self.push_frame(_message("transcript", text=frame.text, final=final))
            return
        if isinstance(frame, InputAudioRawFrame):
            return
        await self.push_frame(frame, direction)


@dataclass(frozen=True)
class SpeechDeps:
    stt_factory: Callable[[], STTService]
    allowed_origins: list[str]
    max_seconds: int


class SpeechSession:
    def __init__(self, websocket: WebSocket, deps: SpeechDeps) -> None:
        self._ws, self._deps = websocket, deps

    def _transport(self) -> FastAPIWebsocketTransport:
        params = FastAPIWebsocketParams(
            serializer=MessageOnlySerializer(),
            audio_in_enabled=True,
            audio_in_sample_rate=SAMPLE_RATE,
            audio_out_enabled=False,
            allowed_origins=self._deps.allowed_origins,
            session_timeout=self._deps.max_seconds,
        )
        return FastAPIWebsocketTransport(websocket=self._ws, params=params)

    async def run(self) -> None:
        transport = self._transport()
        pipeline = Pipeline(
            [
                transport.input(),
                SpeechControl(),
                self._deps.stt_factory(),
                TranscriptRelay(),
                transport.output(),
            ]
        )
        worker = PipelineWorker(
            pipeline,
            params=PipelineParams(audio_in_sample_rate=SAMPLE_RATE, enable_metrics=False),
            enable_rtvi=False,  # plain transcript messages; the widget needs no RTVI here
            idle_timeout_secs=None,
        )

        @transport.event_handler("on_client_disconnected")
        async def on_disconnected(_transport: object, _ws: object) -> None:
            await worker.cancel()

        @transport.event_handler("on_session_timeout")
        async def on_timeout(_transport: object, _ws: object) -> None:
            await worker.cancel()

        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        try:
            await runner.run()
        except Exception:  # session boundary: log, never crash the server
            log.exception("speech_session_failed")
