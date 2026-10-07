"""Doctor lookup (in-memory, static per seed) and complaint → specialty mapping."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from rapidfuzz import fuzz, process

from clinic_bot.domain.entities import Doctor, IntakeSummary
from clinic_bot.domain.enums import Sex, Specialty
from clinic_bot.domain.errors import ErrorCode, NotFound, Unavailable
from clinic_bot.domain.policies import SpecialtyRules
from clinic_bot.ports.llm import StructuredLLM
from clinic_bot.ports.unit_of_work import UnitOfWorkFactory

NAME_MATCH_CUTOFF = 70.0
_TITLE_WORDS = ("dr.", "dr", "doctor")


class DoctorDirectory:
    """Immutable view of the seeded doctors, keyed by id and specialty."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow
        self._by_id: Mapping[int, Doctor] = MappingProxyType({})
        self._by_specialty: Mapping[Specialty, tuple[Doctor, ...]] = MappingProxyType({})

    async def reload(self) -> None:
        """Load doctors once. Call again after a reseed."""
        async with self._uow() as uow:
            doctors = await uow.doctors.all()
        self._by_id = MappingProxyType({d.id: d for d in doctors})
        grouped: dict[Specialty, list[Doctor]] = {}
        for d in doctors:
            grouped.setdefault(d.specialty, []).append(d)
        self._by_specialty = MappingProxyType({k: tuple(v) for k, v in grouped.items()})

    def get(self, doctor_id: int) -> Doctor:
        try:
            return self._by_id[doctor_id]
        except KeyError as exc:
            raise NotFound(ErrorCode.NOT_FOUND) from exc

    def in_specialty(self, specialty: Specialty) -> tuple[Doctor, ...]:
        return self._by_specialty.get(specialty, ())

    def all(self) -> tuple[Doctor, ...]:
        return tuple(self._by_id.values())

    def search(self, specialty: Specialty | None, name: str | None) -> tuple[Doctor, ...]:
        """Filter by specialty and/or fuzzy name. Raises ``NotFound(NO_DOCTORS)``."""
        pool = self.in_specialty(specialty) if specialty else self.all()
        found = self._match_name(pool, name) if name else pool
        if not found:
            raise NotFound(ErrorCode.NO_DOCTORS)
        return found

    def _match_name(self, pool: Sequence[Doctor], name: str) -> tuple[Doctor, ...]:
        query = _normalise_name(name)
        exact = tuple(d for d in pool if _normalise_name(d.name) == query)
        if exact:
            return exact
        choices = {d.id: _normalise_name(d.name) for d in pool}
        hits = process.extract(
            query, choices, scorer=fuzz.WRatio, score_cutoff=NAME_MATCH_CUTOFF, limit=None
        )
        return tuple(self._by_id[key] for _, _, key in hits)


def _normalise_name(name: str) -> str:
    words = [w for w in name.lower().replace(",", " ").split() if w not in _TITLE_WORDS]
    return " ".join(words)


class SpecialtyMapper:
    """Server-side, enum-constrained mapping of an intake to a specialty hint."""

    def __init__(
        self, llm: StructuredLLM, guide: str, rules: SpecialtyRules, available: Sequence[Specialty]
    ) -> None:
        self._llm, self._guide, self._rules = llm, guide, rules
        self._labels = [s.value for s in available]

    async def map(self, intake: IntakeSummary, age: int, sex: Sex) -> Specialty:
        """Ambiguous, multi-system or failed mapping falls back to general medicine."""
        user = (
            f"Patient age: {age}. Patient sex: {sex.value} (soft hint only).\n"
            f"Complaint: {intake.chief_complaint}\n"
            f"Duration: {intake.duration or 'unknown'}. Severity: {intake.severity or 'unknown'}.\n"
            + "\n".join(f"Q: {a.q} A: {a.a}" for a in intake.answers)
        )
        try:
            label, _ = await self._llm.classify(self._system_prompt(), user, self._labels)
        except Unavailable:
            return Specialty.GENERAL_MEDICINE
        return self._rules.adjust(Specialty(label), age)

    def _system_prompt(self) -> str:
        return (
            "You route a clinic patient to one specialty. Use the guide below. "
            "Reply with exactly one label. If the complaint is unclear or involves "
            "several body systems, choose general_medicine.\n\n" + self._guide
        )
