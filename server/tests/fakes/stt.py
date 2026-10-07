"""Scripted speech-to-text: an interim result per audio chunk, a final one on end of speech."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.settings import STTSettings
from pipecat.services.stt_service import STTService
from pipecat.utils.time import time_now_iso8601

WORDS = ["I", "need", "an", "appointment"]


class ScriptedSTTService(STTService):
    def __init__(self) -> None:
        super().__init__(
            settings=STTSettings(model="scripted", language=None), audio_passthrough=False
        )
        self.chunks = 0

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        self.chunks += 1
        text = " ".join(WORDS[: min(self.chunks, len(WORDS))])
        yield InterimTranscriptionFrame(text, "", time_now_iso8601())

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, VADUserStoppedSpeakingFrame) and self.chunks:
            final = " ".join(WORDS[: min(self.chunks, len(WORDS))])
            await self.push_frame(TranscriptionFrame(final, "", time_now_iso8601()))
