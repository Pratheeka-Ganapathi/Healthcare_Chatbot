"""Off-the-turn-path transcript persistence (queue + batched inserts)."""

from __future__ import annotations

import asyncio
import contextlib

from clinic_bot.domain.entities import TranscriptRecord
from clinic_bot.ports.unit_of_work import UnitOfWorkFactory

BATCH_SIZE = 20


class TranscriptWriter:
    """Sessions enqueue one record on disconnect; a background task writes batches."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow
        self._queue: asyncio.Queue[TranscriptRecord] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="transcript-writer")

    def submit(self, record: TranscriptRecord) -> None:
        self._queue.put_nowait(record)

    async def aclose(self) -> None:
        """Flush what is queued, then stop."""
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        await self._flush(self._drain())

    async def _run(self) -> None:
        while True:
            first = await self._queue.get()
            await self._flush([first, *self._drain()])

    def _drain(self) -> list[TranscriptRecord]:
        batch: list[TranscriptRecord] = []
        while not self._queue.empty() and len(batch) < BATCH_SIZE:
            batch.append(self._queue.get_nowait())
        return batch

    async def _flush(self, batch: list[TranscriptRecord]) -> None:
        if not batch:
            return
        async with self._uow(write=True) as uow:
            await uow.transcripts.add_many(batch)
            await uow.commit()
