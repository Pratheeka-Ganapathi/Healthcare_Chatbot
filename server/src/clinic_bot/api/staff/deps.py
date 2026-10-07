"""FastAPI dependencies: the staff services and the signed-in user (bearer token)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from clinic_bot.domain.enums import StaffRole
from clinic_bot.domain.errors import Unauthorized
from clinic_bot.domain.staff import StaffUser
from clinic_bot.services.staff import StaffServices

_bearer = HTTPBearer(auto_error=False)
SIGNED_OUT = "Your session has ended. Please sign in again."


def staff_services(request: Request) -> StaffServices:
    return cast(StaffServices, request.app.state.container.staff)


Staff = Annotated[StaffServices, Depends(staff_services)]


@dataclass(frozen=True, slots=True)
class Caller:
    user: StaffUser
    token: str

    @property
    def user_id(self) -> int:
        assert self.user.id is not None
        return self.user.id


async def caller(
    staff: Staff,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Caller:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, SIGNED_OUT)
    try:
        user = await staff.auth.authenticate(credentials.credentials)
    except Unauthorized as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, SIGNED_OUT) from exc
    return Caller(user, credentials.credentials)


def _role(role: StaffRole):  # type: ignore[no-untyped-def]
    async def check(who: Annotated[Caller, Depends(caller)]) -> Caller:
        if who.user.role is not role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this.")
        return who

    return check


AnyStaff = Annotated[Caller, Depends(caller)]
Admin = Annotated[Caller, Depends(_role(StaffRole.ADMIN))]
DoctorCaller = Annotated[Caller, Depends(_role(StaffRole.DOCTOR))]
