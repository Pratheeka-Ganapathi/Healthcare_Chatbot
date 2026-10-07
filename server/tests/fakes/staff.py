"""Staff portal test helpers: a recording doc indexer, a table browser, accounts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from clinic_bot.domain.staff import StaffUser
from clinic_bot.ports.staff import TableInfo, TablePage
from clinic_bot.services.staff.accounts import AccountService
from tests.fakes.repos import InMemoryUnitOfWorkFactory

ADMIN_EMAIL, ADMIN_PASSWORD = "admin@citycare.test", "admin-pass-1"
DOCTOR_PASSWORD = "doctor-pass-1"


class RecordingIndexer:
    def __init__(self) -> None:
        self.rebuilt: list[dict[str, str]] = []

    async def rebuild(self, docs: Mapping[str, str]) -> int:
        self.rebuilt.append(dict(docs))
        return len(docs)

    async def ensure_current(self, docs: Mapping[str, str]) -> bool:
        return False


class CountingTables:
    """Counts rows of the in-memory store the way the SQL browser counts tables."""

    def __init__(self, uow: InMemoryUnitOfWorkFactory) -> None:
        self._uow = uow

    async def counts(self, names: Sequence[str]) -> dict[str, int]:
        s = self._uow.store
        sizes = {
            "patients": len(s.patients),
            "doctors": len(s.doctors),
            "consultations": len(s.consultations),
            "chat_summaries": len(s.chat_summaries),
            "callbacks": len(s.callbacks),
        }
        return {n: sizes[n] for n in names}

    async def tables(self) -> list[TableInfo]:
        return []

    async def page(self, name: str, offset: int, limit: int) -> TablePage:
        raise NotImplementedError


async def make_admin(accounts: AccountService) -> StaffUser:
    return await accounts.set_admin(ADMIN_EMAIL, "Clinic admin", ADMIN_PASSWORD)


async def make_doctor(accounts: AccountService, doctor_id: int, email: str) -> StaffUser:
    return await accounts.create_doctor_account(
        email, f"Doctor {doctor_id}", DOCTOR_PASSWORD, doctor_id
    )
