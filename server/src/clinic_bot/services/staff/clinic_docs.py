"""Editable clinic FAQ documents; saving re-indexes them for ``answer_faq`` (SPEC 17.3)."""

from __future__ import annotations

import asyncio

from clinic_bot.domain.errors import ErrorCode, NotFound
from clinic_bot.domain.staff import EDITABLE_DOCS, ClinicDoc, StaffUser
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.unit_of_work import UnitOfWorkFactory
from clinic_bot.ports.vector_store import DocIndexer


class ClinicDocService:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock, indexer: DocIndexer) -> None:
        self._uow, self._clock, self._indexer = uow, clock, indexer
        self._reindex = asyncio.Lock()

    async def all(self) -> list[ClinicDoc]:
        """In the order of ``EDITABLE_DOCS``."""
        async with self._uow() as uow:
            docs = {d.name: d for d in await uow.clinic_docs.all()}
        return [docs[name] for name in EDITABLE_DOCS if name in docs]

    async def save(self, name: str, content: str, by: StaffUser) -> ClinicDoc:
        """Store the new text, then rebuild the index. Raises ``NotFound`` for a document
        that is not editable and ``InvalidInput`` (NO_HEADING, INVALID)."""
        if name not in EDITABLE_DOCS:
            raise NotFound(ErrorCode.NOT_FOUND)
        doc = ClinicDoc(name, content.replace("\r\n", "\n"), self._clock.now(), by.name)
        async with self._reindex:
            async with self._uow(write=True) as uow:
                await uow.clinic_docs.save(doc)
                await uow.commit()
            await self._indexer.rebuild(await self._contents())
        return doc

    async def sync_index(self) -> bool:
        """Startup: rebuild if the stored documents changed since the last index build."""
        async with self._reindex:
            return await self._indexer.ensure_current(await self._contents())

    async def _contents(self) -> dict[str, str]:
        return {d.name: d.content for d in await self.all()}
