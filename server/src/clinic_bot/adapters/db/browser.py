"""Read-only table browser for the admin portal (SPEC 17.3)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import Table, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clinic_bot.adapters.db.orm import Base
from clinic_bot.domain.errors import ErrorCode, NotFound, Unavailable
from clinic_bot.ports.staff import Cell, TableInfo, TablePage

HIDDEN_TABLES = frozenset({"staff_sessions"})
HIDDEN_COLUMNS = {"staff_users": frozenset({"password_hash"})}
MAX_PAGE = 200


def _cell(value: object) -> Cell:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime | date):
        return value.isoformat()
    return json.dumps(value, ensure_ascii=False, default=str)


class SqlTableBrowser:
    def __init__(self, factory: async_sessionmaker[Any]) -> None:
        self._factory = factory

    def _visible(self) -> list[Table]:
        tables = Base.metadata.tables.values()
        return sorted((t for t in tables if t.name not in HIDDEN_TABLES), key=lambda t: t.name)

    def _table(self, name: str) -> Table:
        table = Base.metadata.tables.get(name)
        if table is None or name in HIDDEN_TABLES:
            raise NotFound(ErrorCode.NOT_FOUND)
        return table

    async def tables(self) -> list[TableInfo]:
        counts = await self.counts([t.name for t in self._visible()])
        return [TableInfo(name, count) for name, count in counts.items()]

    async def counts(self, names: Sequence[str]) -> dict[str, int]:
        tables = [self._table(name) for name in names]
        session: AsyncSession
        try:
            async with self._factory() as session:
                return {
                    t.name: int(await session.scalar(select(func.count()).select_from(t)) or 0)
                    for t in tables
                }
        except DBAPIError as exc:
            raise Unavailable(ErrorCode.BUSY, "database busy") from exc

    async def page(self, name: str, offset: int, limit: int) -> TablePage:
        table = self._table(name)
        hidden = HIDDEN_COLUMNS.get(name, frozenset())
        columns = [c for c in table.columns if c.name not in hidden]
        offset, limit = max(offset, 0), min(max(limit, 1), MAX_PAGE)
        stmt = select(*columns).order_by(*table.primary_key.columns).offset(offset).limit(limit)
        session: AsyncSession
        try:
            async with self._factory() as session:
                total = int(await session.scalar(select(func.count()).select_from(table)) or 0)
                rows = (await session.execute(stmt)).all()
        except DBAPIError as exc:
            raise Unavailable(ErrorCode.BUSY, "database busy") from exc
        return TablePage(
            name=name,
            columns=tuple(c.name for c in columns),
            rows=tuple(tuple(_cell(v) for v in row) for row in rows),
            total=total,
            offset=offset,
            limit=limit,
        )
