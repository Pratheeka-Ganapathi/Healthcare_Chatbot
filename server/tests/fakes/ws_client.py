"""Minimal RTVI-over-protobuf WebSocket client, speaking what the widget speaks."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pipecat.frames.protobufs.frames_pb2 as pb
import websockets


def _encode(message: dict[str, Any]) -> bytes:
    frame = pb.Frame()
    frame.message.data = json.dumps(message)
    return frame.SerializeToString()


def _decode(raw: bytes) -> dict[str, Any] | None:
    frame = pb.Frame()
    frame.ParseFromString(raw)
    if frame.WhichOneof("frame") != "message":
        return None
    data: dict[str, Any] = json.loads(frame.message.data)
    return data


@dataclass
class BotTurn:
    texts: list[str] = field(default_factory=list)
    ui: list[dict[str, Any]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(self.texts)


class RtviClient:
    def __init__(self, url: str, origin: str = "http://localhost:5173") -> None:
        self._url, self._origin = url, origin
        self._ws: Any = None
        self.messages: list[dict[str, Any]] = []
        self._current: list[str] = []

    async def __aenter__(self) -> RtviClient:
        self._ws = await websockets.connect(self._url, origin=self._origin)
        await self._send("client-ready", {"version": "2.1.0", "about": {"library": "test"}})
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._ws.close()

    async def _send(self, kind: str, data: dict[str, Any]) -> None:
        msg = {"label": "rtvi-ai", "type": kind, "id": uuid.uuid4().hex[:8], "data": data}
        await self._ws.send(_encode(msg))

    async def send_text(self, text: str) -> None:
        await self._send(
            "send-text",
            {"content": text, "options": {"run_immediately": True, "audio_response": False}},
        )

    async def collect(self, quiet_s: float = 1.0, max_s: float = 15.0) -> BotTurn:
        """Gather bot output until nothing arrives for ``quiet_s``."""
        turn = BotTurn()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_s
        while loop.time() < deadline:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=quiet_s)
            except TimeoutError:
                break
            msg = _decode(raw) if isinstance(raw, bytes) else None
            if msg is None:
                continue
            self.messages.append(msg)
            self._absorb(msg, turn)
        return turn

    def _absorb(self, msg: dict[str, Any], turn: BotTurn) -> None:
        kind = msg.get("type")
        if kind == "bot-llm-started":
            self._current = []
        elif kind == "bot-llm-text":
            self._current.append(msg["data"]["text"])
        elif kind == "bot-llm-stopped":
            text = "".join(self._current).strip()
            if text:
                turn.texts.append(text)
            self._current = []
        elif kind == "server-message" and msg.get("data", {}).get("type") == "ui":
            turn.ui.append(msg["data"]["payload"])
