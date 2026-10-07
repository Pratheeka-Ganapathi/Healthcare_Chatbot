"""Shared fixtures. Every test runs with a frozen clock (CLINIC_NOW).

SQL-backed tests need PostgreSQL: ``docker compose up -d db`` locally (it creates
``clinic_test``), a service container in CI. Override with ``TEST_DATABASE_URL``.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

from clinic_bot.adapters.clock import IST, FrozenClock
from clinic_bot.config import SERVER_ROOT, Settings

# litellm copies ./.env into os.environ on import unless LITELLM_MODE is set. Tests must not
# see the developer's server/.env: the settings below rely on _env_file=None.
os.environ.setdefault("LITELLM_MODE", "PRODUCTION")

FROZEN_NOW = datetime(2026, 10, 6, 10, 0, tzinfo=IST)  # a Tuesday
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://clinic:clinic@localhost:5432/clinic_test"
)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(FROZEN_NOW)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        clinic_now=FROZEN_NOW,
        database_url=TEST_DATABASE_URL,
        reseed_on_start=True,
        health_cache_dir=str(tmp_path / "health"),
        data_dir=str(SERVER_ROOT / "data"),
        google_api_key="test-key",
        allowed_origins=["http://localhost:5173"],
        classifier_timeout_s=2.0,
    )
