"""Command-line entry points: reseed the database, build the RAG index, pre-warm the
embedding model and MedlinePlus, create a staff admin."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

import httpx

from clinic_bot.adapters.clock import FrozenClock, SystemClock
from clinic_bot.adapters.db.engine import create_engine, session_factory
from clinic_bot.adapters.db.uow import SqlUnitOfWorkFactory
from clinic_bot.adapters.health.cached import CachedHealthInfo, prewarm
from clinic_bot.adapters.health.medlineplus import MedlinePlusProvider
from clinic_bot.adapters.vector.build_index import build
from clinic_bot.adapters.vector.pgvector_store import PgVectorStore
from clinic_bot.config import Settings
from clinic_bot.container import build_embedder
from clinic_bot.domain.errors import DomainError
from clinic_bot.seed.seeder import Seeder
from clinic_bot.services.staff.accounts import AccountService


def reseed() -> None:
    settings = Settings()
    clock = FrozenClock(settings.clinic_now) if settings.clinic_now else SystemClock()

    async def run() -> None:
        engine = create_engine(settings.database_url, pooled=False)
        await Seeder(engine, clock, Path(settings.data_dir) / "docs").reseed()
        await engine.dispose()

    asyncio.run(run())
    print(f"Reseeded {settings.database_url.rsplit('@', 1)[-1]}")  # host/db, never the password


def build_index() -> None:
    """Full rebuild from the files in ``data/docs``. The app also builds it on startup."""
    settings = Settings()

    async def run() -> int:
        engine = create_engine(settings.database_url, pooled=False)
        try:
            store = PgVectorStore(engine)
            await store.ensure_schema()
            docs = Path(settings.data_dir) / "docs"
            return await build(docs, store, build_embedder(settings), settings.index_key)
        finally:
            await engine.dispose()

    count = asyncio.run(run())
    print(f"Indexed {count} chunks into {settings.database_url.rsplit('@', 1)[-1]}")


def prewarm_embedder() -> None:
    """Docker build: download the embedding model into the image (no database needed)."""
    settings = Settings()
    asyncio.run(build_embedder(settings).embed(["warm-up"]))
    print(f"Embedding model ready: {settings.index_key}")


def prewarm_health() -> None:
    settings = Settings()

    async def run() -> int:
        async with httpx.AsyncClient() as client:
            cache = Path(settings.health_cache_dir)
            return await prewarm(CachedHealthInfo(MedlinePlusProvider(client), cache))

    print(f"Pre-warmed {asyncio.run(run())} MedlinePlus answers")


def create_admin() -> None:
    """Create a staff admin, or reset an admin's password (SPEC 17.1). Prompts for it."""
    parser = argparse.ArgumentParser(prog="clinic-create-admin")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Clinic admin")
    args = parser.parse_args()
    password = getpass.getpass("Password (8 or more characters): ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    settings = Settings()
    clock = FrozenClock(settings.clinic_now) if settings.clinic_now else SystemClock()

    async def run() -> None:
        engine = create_engine(settings.database_url, pooled=False)
        try:
            await Seeder(engine, clock, Path(settings.data_dir) / "docs").ensure_seeded()
            uow = SqlUnitOfWorkFactory(session_factory(engine), clock)
            await AccountService(uow, clock).set_admin(args.email, args.name, password)
        finally:
            await engine.dispose()

    try:
        asyncio.run(run())
    except DomainError as exc:
        sys.exit(f"Not saved: {exc.code}")
    print(f"Admin {args.email.strip().lower()} is ready.")
