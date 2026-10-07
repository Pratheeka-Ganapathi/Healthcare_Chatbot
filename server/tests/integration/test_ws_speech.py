"""Voice input over a real WebSocket: audio in, transcript out, nothing sent to the chat."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pipecat.frames.protobufs.frames_pb2 as pb
import pytest
import websockets

from tests.integration.conftest import LiveServer

CHUNK = b"\x00\x00" * 1600  # 100 ms of 16 kHz silence


def _audio() -> bytes:
    frame = pb.Frame()
    frame.audio.audio, frame.audio.sample_rate, frame.audio.num_channels = CHUNK, 16_000, 1
    return frame.SerializeToString()


def _message(data: dict[str, Any]) -> bytes:
    frame = pb.Frame()
    frame.message.data = json.dumps(data)
    return frame.SerializeToString()


async def _transcripts(ws: Any, until_final: bool) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    while True:
        frame = pb.Frame()
        frame.ParseFromString(await asyncio.wait_for(ws.recv(), timeout=5))
        msg = json.loads(frame.message.data)
        seen.append(msg)
        if not until_final or msg.get("final"):
            return seen


def _stt_url(server: LiveServer) -> str:
    return server.url.removesuffix("/ws") + "/stt"


async def test_speech_streams_interim_then_final_transcript(live_server: LiveServer) -> None:
    async with websockets.connect(_stt_url(live_server), origin="http://localhost:5173") as ws:
        for _ in range(3):
            await ws.send(_audio())
        interim = await _transcripts(ws, until_final=False)
        assert interim == [{"type": "transcript", "text": "I", "final": False}]
        await ws.send(_message({"type": "speech-end"}))
        seen = await _transcripts(ws, until_final=True)
    assert seen[-1] == {"type": "transcript", "text": "I need an", "final": True}
    assert all(m["type"] == "transcript" for m in seen)
    assert live_server.llms == []  # speech never opens a chat or reaches an LLM


async def test_speech_rejects_unknown_origins(live_server: LiveServer) -> None:
    with pytest.raises(websockets.exceptions.InvalidStatus):
        async with websockets.connect(_stt_url(live_server), origin="https://evil.example"):
            pass
