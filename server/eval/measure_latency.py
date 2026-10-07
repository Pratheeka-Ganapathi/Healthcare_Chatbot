"""Server-side latency budgets (SPEC 16.7), excluding LLM time. Frozen clock, real PostgreSQL,
real fastembed + pgvector. Prints p50/p95 in milliseconds. Reseeds the *test* database
(``TEST_DATABASE_URL``, default ``clinic_test`` from docker compose), never the app's.

    uv run python eval/measure_latency.py
"""

from __future__ import annotations

import asyncio
import os
import statistics
import time
from collections.abc import Awaitable, Callable
from datetime import datetime

from clinic_bot.adapters.clock import IST, FrozenClock
from clinic_bot.adapters.db.engine import create_engine, session_factory
from clinic_bot.adapters.db.uow import SqlUnitOfWorkFactory
from clinic_bot.adapters.embeddings.fastembed_embedder import FastEmbedEmbedder
from clinic_bot.adapters.vector.build_index import build
from clinic_bot.adapters.vector.pgvector_store import PgVectorStore
from clinic_bot.config import SERVER_ROOT
from clinic_bot.domain.day_resolver import DayResolver
from clinic_bot.domain.enums import TimePref
from clinic_bot.domain.policies import (
    BookingPolicy,
    CancellationPolicy,
    FeePolicy,
    LockoutPolicy,
    SlotTimingPolicy,
)
from clinic_bot.seed.seeder import Seeder
from clinic_bot.services.booking import BookingService
from clinic_bot.services.directory import DoctorDirectory
from clinic_bot.services.guardrails.regex_guard import RegexGuard
from clinic_bot.services.scheduling import SchedulingService
from clinic_bot.services.verification import VerificationService

RUNS = 50
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://clinic:clinic@localhost:5432/clinic_test"
)


async def timed(fn: Callable[[], Awaitable[object]], runs: int = RUNS) -> tuple[float, float]:
    await fn()  # warm-up
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        await fn()
        samples.append((time.perf_counter() - start) * 1000)
    ordered = sorted(samples)
    return statistics.median(ordered), ordered[round(0.95 * (len(ordered) - 1))]


async def main() -> None:
    clock = FrozenClock(datetime(2026, 10, 6, 10, 0, tzinfo=IST))
    engine = create_engine(TEST_DATABASE_URL)
    await Seeder(engine, clock).reseed()
    uow = SqlUnitOfWorkFactory(session_factory(engine), clock)
    directory = DoctorDirectory(uow)
    await directory.reload()
    scheduling = SchedulingService(uow, clock, DayResolver(), SlotTimingPolicy(), directory)
    booking = BookingService(uow, clock, BookingPolicy(), FeePolicy(), CancellationPolicy())
    verification = VerificationService(uow, clock, LockoutPolicy())
    embedder = FastEmbedEmbedder(MODEL)
    store = PgVectorStore(engine)
    await store.ensure_schema()
    await build(SERVER_ROOT / "data" / "docs", store, embedder, f"fastembed:{MODEL}")
    regex = RegexGuard()

    async def regex_check() -> object:
        return regex.precheck("I have had a fever and body ache since Monday, can I book")

    async def rag() -> object:
        [vector] = await embedder.embed(["do I need to fast before a sugar test"])
        return await store.query(vector, 3, ["faq", "prep"])

    rows = {
        "Regex precheck": await timed(regex_check, 1000),
        "verify_patient (DB, write)": await timed(
            lambda: verification.verify("9000000005", "03/03/1995")
        ),
        "get_free_slots (DB)": await timed(
            lambda: scheduling.free_slots(1, "wednesday", TimePref.ANY)
        ),
        "upcoming appointments (DB)": await timed(lambda: booking.upcoming(2)),
        "RAG query (embed + pgvector)": await timed(rag),
    }
    print("| Step | p50 ms | p95 ms |\n|---|---|---|")
    for name, (p50, p95) in rows.items():
        print(f"| {name} | {p50:.2f} | {p95:.2f} |")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
