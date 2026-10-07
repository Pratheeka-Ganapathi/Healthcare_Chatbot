"""HTTP and WebSocket routes."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, status

from clinic_bot.seed.demo_data import demo_patients

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config/demo")
async def demo_config() -> dict[str, object]:
    return {"patients": demo_patients()}


@router.websocket("/ws")
async def chat(websocket: WebSocket) -> None:
    container = websocket.app.state.container
    if not _origin_allowed(websocket, container.settings.allowed_origins):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    await container.new_session(websocket).run()


@router.websocket("/stt")
async def speech(websocket: WebSocket) -> None:
    """Voice input: mic audio in, transcript out, while the mic is on (SPEC 10.1)."""
    container = websocket.app.state.container
    if not _origin_allowed(websocket, container.settings.allowed_origins):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    await container.new_speech_session(websocket).run()


def _origin_allowed(websocket: WebSocket, allowed: list[str]) -> bool:
    return not allowed or websocket.headers.get("origin") in allowed
