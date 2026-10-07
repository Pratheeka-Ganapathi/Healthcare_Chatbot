"""UIEmitter: tool UI payloads → RTVI server messages ``{"type": "ui", "payload": ...}``."""

from __future__ import annotations

from pipecat.frames.frames import Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame

from clinic_bot.conversation.result import UIPayload, ui_to_json


class UIEmitterProcessor(FrameProcessor):
    def __init__(self) -> None:
        super().__init__(name="UIEmitter")

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)

    async def emit(self, payload: UIPayload) -> None:
        message = {"type": "ui", "payload": ui_to_json(payload)}
        await self.push_frame(RTVIServerMessageFrame(data=message), FrameDirection.DOWNSTREAM)
