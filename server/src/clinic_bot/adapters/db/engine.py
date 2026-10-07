"""Async PostgreSQL engine (asyncpg) and the session factory.

Write units of work serialise on one transaction-level advisory lock, so policy checks
and the insert run as if alone (the partial unique index still backs up the slot rule).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

WRITE_LOCK_KEY = 7_202_610  # any constant; every write transaction takes the same lock
LOCK_TIMEOUT = "5s"


def create_engine(url: str, *, pooled: bool = True) -> AsyncEngine:
    """``pooled=False`` closes connections on release (tests, one-off scripts)."""
    if not pooled:
        return create_async_engine(url, poolclass=NullPool)
    return create_async_engine(url, pool_size=5, max_overflow=5, pool_pre_ping=True)


def session_factory(engine: AsyncEngine) -> async_sessionmaker[Any]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def take_write_lock(session: AsyncSession) -> None:
    """Released at commit or rollback. Waits at most ``LOCK_TIMEOUT``."""
    await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": WRITE_LOCK_KEY})
