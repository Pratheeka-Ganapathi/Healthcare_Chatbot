"""A real server (uvicorn + FastAPI + Pipecat) with scripted LLMs."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
import uvicorn
from sqlalchemy import text

from clinic_bot.adapters.db.engine import create_engine
from clinic_bot.api.app import create_app
from clinic_bot.config import Settings
from clinic_bot.container import Container, Overrides, build_embedder
from clinic_bot.ports.embeddings import Embedder
from tests.fakes.health import FakeHealthInfo
from tests.fakes.llm import FakeStructuredLLM, ScriptedLLMService
from tests.fakes.stt import ScriptedSTTService


@dataclass
class LiveServer:
    url: str
    container: Container
    llms: list[ScriptedLLMService]
    classifier: FakeStructuredLLM
    mapper: FakeStructuredLLM
    summarizer: FakeStructuredLLM

    @property
    def llm(self) -> ScriptedLLMService:
        """The main LLM of the most recent connection."""
        return self.llms[-1]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def embedder() -> Embedder:
    """One real fastembed model for the whole run. Each server loading its own copy made
    the first in-request re-embed (an admin doc save) slow enough to time out."""
    return build_embedder(Settings(_env_file=None))  # type: ignore[call-arg]


@pytest.fixture
async def live_server(settings: Settings, embedder: Embedder) -> AsyncIterator[LiveServer]:
    llms: list[ScriptedLLMService] = []

    def new_llm() -> ScriptedLLMService:
        llms.append(ScriptedLLMService())
        return llms[-1]

    classifier = FakeStructuredLLM(
        {"elephant": "EMERGENCY", "write me": "OFF_TOPIC", "end it all": "SELF_HARM"}
    )
    mapper = FakeStructuredLLM({"rash": "dermatology", "knee": "orthopaedics"}, "general_medicine")
    summarizer = FakeStructuredLLM()
    overrides = Overrides(
        embedder=embedder,
        classifier_llm=classifier,
        mapper_llm=mapper,
        summary_llm=summarizer,
        health=FakeHealthInfo(),
        main_llm_factory=new_llm,
        stt_factory=ScriptedSTTService,
    )
    holder: dict[str, Container] = {}

    async def factory(s: Settings) -> Container:
        holder["c"] = await Container.for_tests(s, overrides)
        return holder["c"]

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings, factory), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    task = asyncio.create_task(server.serve())
    while not server.started:  # noqa: ASYNC110 - uvicorn exposes a flag, not an event
        await asyncio.sleep(0.05)
    try:
        yield LiveServer(
            f"ws://127.0.0.1:{port}/ws", holder["c"], llms, classifier, mapper, summarizer
        )
    finally:
        server.should_exit = True
        await task


async def query(server: LiveServer, sql: str, **params: object) -> list[dict[str, Any]]:
    """Raw rows for assertions, read straight from the test database."""
    engine = create_engine(server.container.settings.database_url, pooled=False)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql), params)
            return [dict(r._mapping) for r in result]
    finally:
        await engine.dispose()


async def appointments_of(server: LiveServer, patient_id: int) -> list[dict[str, Any]]:
    rows = await query(
        server, "SELECT * FROM appointments WHERE patient_id = :pid ORDER BY id", pid=patient_id
    )
    for row in rows:
        if isinstance(row.get("intake_summary"), str):
            row["intake_summary"] = json.loads(row["intake_summary"])
    return rows
