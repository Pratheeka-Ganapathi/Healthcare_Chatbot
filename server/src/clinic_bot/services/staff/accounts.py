"""Staff accounts: doctor logins are created by an admin only (SPEC 17.1, 17.3)."""

from __future__ import annotations

from dataclasses import replace

from clinic_bot.domain.enums import StaffRole
from clinic_bot.domain.errors import Conflict, ErrorCode, NotFound
from clinic_bot.domain.staff import (
    EmailAddress,
    StaffUser,
    check_password,
    check_staff_name,
)
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.unit_of_work import UnitOfWorkFactory
from clinic_bot.services.staff.passwords import hash_password


class AccountService:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def all(self) -> list[StaffUser]:
        async with self._uow() as uow:
            return await uow.staff_users.all()

    async def create_doctor_account(
        self, email_raw: str, name_raw: str, password: str, doctor_id: int
    ) -> StaffUser:
        """Raises ``InvalidInput`` (BAD_EMAIL, BAD_NAME, WEAK_PASSWORD), ``NotFound`` for an
        unknown doctor, ``Conflict`` (EMAIL_TAKEN, DOCTOR_HAS_ACCOUNT)."""
        return await self._create(email_raw, name_raw, password, StaffRole.DOCTOR, doctor_id)

    async def update(
        self,
        actor: StaffUser,
        user_id: int,
        *,
        name: str | None = None,
        active: bool | None = None,
        password: str | None = None,
    ) -> StaffUser:
        """Rename, (de)activate or reset a password. Deactivating or resetting ends the
        account's sessions. Raises ``NotFound``, ``InvalidInput``, ``Conflict(SELF_DEACTIVATE)``."""
        if active is False and actor.id == user_id:
            raise Conflict(ErrorCode.SELF_DEACTIVATE)
        hashed = await hash_password(check_password(password)) if password is not None else None
        async with self._uow(write=True) as uow:
            user = await uow.staff_users.get(user_id)
            if user is None:
                raise NotFound(ErrorCode.NOT_FOUND)
            user = replace(
                user,
                name=check_staff_name(name) if name is not None else user.name,
                active=user.active if active is None else active,
                password_hash=hashed or user.password_hash,
            )
            await uow.staff_users.save(user)
            if hashed is not None or active is False:
                await uow.staff_sessions.delete_for_user(user_id)
            await uow.commit()
        return user

    async def ensure_admin(self, email_raw: str, name_raw: str, password: str) -> bool:
        """Startup bootstrap from ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD``. Creates the admin only
        if no account has that email; never changes an existing one. True if created."""
        email = EmailAddress.parse(email_raw)
        async with self._uow() as uow:
            if await uow.staff_users.by_email(email) is not None:
                return False
        await self._create(email_raw, name_raw, password, StaffRole.ADMIN, None)
        return True

    async def set_admin(self, email_raw: str, name_raw: str, password: str) -> StaffUser:
        """CLI: create an admin, or reset an existing admin's password and reactivate it."""
        email = EmailAddress.parse(email_raw)
        async with self._uow() as uow:
            existing = await uow.staff_users.by_email(email)
        if existing is None:
            return await self._create(email_raw, name_raw, password, StaffRole.ADMIN, None)
        if existing.role is not StaffRole.ADMIN or existing.id is None:
            raise Conflict(ErrorCode.EMAIL_TAKEN)
        return await self.update(existing, existing.id, active=True, password=password)

    async def _create(
        self, email_raw: str, name_raw: str, password: str, role: StaffRole, doctor_id: int | None
    ) -> StaffUser:
        email, name = EmailAddress.parse(email_raw), check_staff_name(name_raw)
        hashed = await hash_password(check_password(password))
        user = StaffUser(None, email, name, role, doctor_id, hashed, True, self._clock.now())
        async with self._uow(write=True) as uow:
            if doctor_id is not None:
                await uow.doctors.require(doctor_id)
            saved = await uow.staff_users.add(user)
            await uow.commit()
        return saved
