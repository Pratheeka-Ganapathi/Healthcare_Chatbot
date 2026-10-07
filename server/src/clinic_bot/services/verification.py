"""Patient identity: check by phone + date of birth, or register a new patient.

Both paths share the per-phone lockout.
"""

from __future__ import annotations

from datetime import datetime

from clinic_bot.domain.entities import Patient, VerifyAttempt
from clinic_bot.domain.enums import Sex
from clinic_bot.domain.errors import ErrorCode, Locked, NotFound
from clinic_bot.domain.policies import LockoutPolicy
from clinic_bot.domain.values import DateOfBirth, PersonName, PhoneNumber
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory


class VerificationService:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock, lockout: LockoutPolicy) -> None:
        self._uow, self._clock, self._lockout = uow, clock, lockout

    async def verify(self, phone_raw: str, dob_raw: str) -> Patient:
        """Return the patient on a match.

        Raises ``InvalidInput`` (BAD_PHONE / BAD_DOB) when input can't be parsed,
        ``Locked`` when the phone is locked out, and ``NotFound(NO_MATCH)`` for any
        mismatch. Wrong phone and wrong DOB are indistinguishable to the caller.
        """
        now = self._clock.now()
        phone = PhoneNumber.parse(phone_raw)
        dob = DateOfBirth.parse(dob_raw, now.date())
        async with self._uow(write=True) as uow:
            await self._ensure_not_locked(uow, phone, now)
            patient = await uow.patients.by_phone(phone)
            ok = patient is not None and patient.matches(phone, dob)
            await uow.verify_attempts.add(VerifyAttempt(phone.digits, now, ok))
            await uow.commit()
        if patient is None or not ok:
            raise NotFound(ErrorCode.NO_MATCH)
        return patient

    async def register(self, name_raw: str, phone_raw: str, dob_raw: str, sex: Sex) -> Patient:
        """Create a patient for a new phone number.

        If the phone is already registered, this acts as a verification: a full
        match (name, phone, DOB) returns that patient; anything else raises
        ``NotFound(NO_MATCH)`` and counts toward the lockout like a wrong DOB.
        Also raises ``InvalidInput`` (BAD_NAME / BAD_PHONE / BAD_DOB) and ``Locked``.
        """
        now = self._clock.now()
        name = PersonName.parse(name_raw)
        phone = PhoneNumber.parse(phone_raw)
        dob = DateOfBirth.parse(dob_raw, now.date())
        async with self._uow(write=True) as uow:
            await self._ensure_not_locked(uow, phone, now)
            existing = await uow.patients.by_phone(phone)
            if existing is None:
                patient: Patient | None = await uow.patients.add(name, phone, dob, sex, now)
            else:
                ok = existing.matches_registration(name, phone, dob)
                patient = existing if ok else None
                await uow.verify_attempts.add(VerifyAttempt(phone.digits, now, ok))
            await uow.commit()
        if patient is None:
            raise NotFound(ErrorCode.NO_MATCH)
        return patient

    def age_of(self, patient: Patient) -> int:
        return patient.age_on(self._clock.today())

    async def _ensure_not_locked(self, uow: UnitOfWork, phone: PhoneNumber, now: datetime) -> None:
        attempts = await uow.verify_attempts.since(phone.digits, now - self._lockout.lookback)
        if self._lockout.is_locked(_failures_after_last_success(attempts), now):
            raise Locked(ErrorCode.LOCKED)


def _failures_after_last_success(attempts: list[VerifyAttempt]) -> list[datetime]:
    ordered = sorted(attempts, key=lambda a: a.ts)
    last_success = max((i for i, a in enumerate(ordered) if a.success), default=-1)
    return [a.ts for a in ordered[last_success + 1 :] if not a.success]
