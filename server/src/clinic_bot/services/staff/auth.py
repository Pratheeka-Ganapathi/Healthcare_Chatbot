"""Staff login, bearer-token sessions and password changes (SPEC 17.1)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from clinic_bot.domain.errors import ErrorCode, InvalidInput, Locked, Unauthorized
from clinic_bot.domain.policies import LockoutPolicy
from clinic_bot.domain.staff import EmailAddress, StaffSession, StaffUser, check_password
from clinic_bot.ports.clock import Clock
from clinic_bot.ports.unit_of_work import UnitOfWorkFactory
from clinic_bot.services.staff.passwords import (
    hash_password,
    new_token,
    token_digest,
    verify_password,
)

MAX_TRACKED_EMAILS = 1000


class LoginThrottle:
    """Failed logins per email, in memory (one backend process). Reuses the patient lockout
    rule: 5 failures in 15 minutes lock that email for 15 minutes."""

    def __init__(self, policy: LockoutPolicy) -> None:
        self._policy = policy
        self._failures: dict[str, list[datetime]] = {}

    def ensure_open(self, email: str, now: datetime) -> None:
        """Raises ``Locked``."""
        recent = [t for t in self._failures.get(email, []) if now - t <= self._policy.lookback]
        self._failures[email] = recent
        if self._policy.is_locked(recent, now):
            raise Locked(ErrorCode.LOCKED)

    def failed(self, email: str, now: datetime) -> None:
        if len(self._failures) > MAX_TRACKED_EMAILS:
            self._forget_old(now)
        self._failures.setdefault(email, []).append(now)

    def succeeded(self, email: str) -> None:
        self._failures.pop(email, None)

    def _forget_old(self, now: datetime) -> None:
        cutoff = now - self._policy.lookback
        self._failures = {e: ts for e, ts in self._failures.items() if ts and ts[-1] > cutoff}


@dataclass(frozen=True, slots=True)
class LoginResult:
    token: str
    user: StaffUser
    expires_at: datetime


class StaffAuthService:
    def __init__(
        self, uow: UnitOfWorkFactory, clock: Clock, throttle: LoginThrottle, session_hours: int
    ) -> None:
        self._uow, self._clock, self._throttle = uow, clock, throttle
        self._hours = session_hours

    async def login(self, email_raw: str, password: str) -> LoginResult:
        """Raises ``Unauthorized(AUTH_FAILED)`` for any wrong detail or an inactive account,
        and ``Locked`` after repeated failures for the email."""
        now = self._clock.now()
        try:
            email = EmailAddress.parse(email_raw)
        except InvalidInput as exc:
            raise Unauthorized(ErrorCode.AUTH_FAILED) from exc
        self._throttle.ensure_open(email.value, now)
        async with self._uow() as uow:
            user = await uow.staff_users.by_email(email)
        ok = await verify_password(password, user.password_hash if user else None)
        if user is None or user.id is None or not ok or not user.active:
            self._throttle.failed(email.value, now)
            raise Unauthorized(ErrorCode.AUTH_FAILED)
        self._throttle.succeeded(email.value)
        token, digest = new_token()
        session = StaffSession.start(digest, user.id, now, self._hours)
        user = replace(user, last_login_at=now)
        async with self._uow(write=True) as uow:
            await uow.staff_sessions.purge_expired(now)
            await uow.staff_sessions.add(session)
            await uow.staff_users.save(user)
            await uow.commit()
        return LoginResult(token, user, session.expires_at)

    async def authenticate(self, token: str) -> StaffUser:
        """The user behind a live token. Raises ``Unauthorized(AUTH_FAILED)``."""
        now = self._clock.now()
        async with self._uow() as uow:
            session = await uow.staff_sessions.get(token_digest(token))
            user = await uow.staff_users.get(session.user_id) if session else None
        if session is None or user is None or not user.active or not session.is_live(now):
            raise Unauthorized(ErrorCode.AUTH_FAILED)
        return user

    async def logout(self, token: str) -> None:
        async with self._uow(write=True) as uow:
            await uow.staff_sessions.delete(token_digest(token))
            await uow.commit()

    async def change_password(
        self, user: StaffUser, token: str, current: str, new_password: str
    ) -> None:
        """Ends the user's other sessions. Raises ``InvalidInput`` (AUTH_FAILED for a wrong
        current password, WEAK_PASSWORD)."""
        check_password(new_password)
        if user.id is None or not await verify_password(current, user.password_hash):
            raise InvalidInput(ErrorCode.AUTH_FAILED)
        hashed = await hash_password(new_password)
        async with self._uow(write=True) as uow:
            await uow.staff_users.save(replace(user, password_hash=hashed))
            await uow.staff_sessions.delete_for_user(user.id, keep=token_digest(token))
            await uow.commit()
