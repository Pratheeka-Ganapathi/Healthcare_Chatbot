"""pgvector tables over the authored clinic docs, in the app's PostgreSQL database.

Kept out of the ORM ``Base`` on purpose: the chunks are derived data (rebuilt from the
documents), so ``reseed`` and the admin table browser leave them alone. Similarity is exact
cosine over a few dozen chunks, so no ANN index is needed and any embedding size fits.
"""

from __future__ import annotations

from collections.abc import Sequence

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import Column, Integer, MetaData, Table, Text, delete, func, insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from clinic_bot.domain.errors import ErrorCode, Unavailable
from clinic_bot.ports.vector_store import Chunk, ScoredChunk

INDEX_LOCK_KEY = 7_202_611  # serialises schema setup and rebuilds across processes

metadata = MetaData()
doc_chunks = Table(
    "doc_chunks",
    metadata,
    Column("id", Text, primary_key=True),
    Column("doc", Text, nullable=False),
    Column("section", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("embedding", VECTOR(), nullable=False),
)
doc_index_state = Table(  # one row: what the chunks were built from
    "doc_index_state",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("stamp", Text, nullable=False),
)


async def _lock(conn: AsyncConnection) -> None:
    await conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": INDEX_LOCK_KEY})


class PgVectorStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def ensure_schema(self) -> None:
        """Startup and CLI: the ``vector`` extension and both tables, if missing."""
        async with self._engine.begin() as conn:
            await _lock(conn)
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(metadata.create_all)

    async def query(
        self, embedding: Sequence[float], k: int, kinds: Sequence[str]
    ) -> list[ScoredChunk]:
        distance = doc_chunks.c.embedding.cosine_distance(list(embedding))
        stmt = (
            select(doc_chunks, (1.0 - distance).label("score"))
            .where(doc_chunks.c.kind.in_(list(kinds)))
            .order_by(distance)
            .limit(k)
        )
        try:
            async with self._engine.connect() as conn:
                rows = (await conn.execute(stmt)).all()
        except DBAPIError as exc:
            raise Unavailable(ErrorCode.BUSY, "vector store unavailable") from exc
        return [
            ScoredChunk(Chunk(r.id, r.text, r.doc, r.section, r.kind), float(r.score)) for r in rows
        ]

    async def count(self) -> int:
        async with self._engine.connect() as conn:
            return int(await conn.scalar(select(func.count()).select_from(doc_chunks)) or 0)

    async def stamp(self) -> str | None:
        async with self._engine.connect() as conn:
            return await conn.scalar(select(doc_index_state.c.stamp))

    async def replace(
        self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]], stamp: str
    ) -> None:
        """Swap every chunk in one transaction; concurrent queries see the old set until
        it commits."""
        rows = [
            dict(id=c.id, doc=c.doc, section=c.section, kind=c.kind, text=c.text, embedding=list(e))
            for c, e in zip(chunks, embeddings, strict=True)
        ]
        async with self._engine.begin() as conn:
            await _lock(conn)
            await conn.execute(delete(doc_chunks))
            if rows:
                await conn.execute(insert(doc_chunks), rows)
            upsert = pg_insert(doc_index_state).values(id=1, stamp=stamp)
            await conn.execute(
                upsert.on_conflict_do_update(index_elements=["id"], set_={"stamp": stamp})
            )
