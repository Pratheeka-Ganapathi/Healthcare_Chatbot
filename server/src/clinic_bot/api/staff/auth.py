"""Sign-in, sign-out and the signed-in user (SPEC 17.1)."""

from __future__ import annotations

from fastapi import APIRouter, status

from clinic_bot.api.staff.bodies import LoginIn, PasswordIn
from clinic_bot.api.staff.deps import AnyStaff, Staff
from clinic_bot.api.staff.views import LoginOut, StaffUserOut

router = APIRouter(tags=["staff: auth"])


@router.post("/auth/login")
async def login(body: LoginIn, staff: Staff) -> LoginOut:
    result = await staff.auth.login(body.email, body.password)
    user = StaffUserOut.of(result.user, staff.directory)
    return LoginOut(token=result.token, expires_at=result.expires_at, user=user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(who: AnyStaff, staff: Staff) -> None:
    await staff.auth.logout(who.token)


@router.get("/me")
async def me(who: AnyStaff, staff: Staff) -> StaffUserOut:
    return StaffUserOut.of(who.user, staff.directory)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: PasswordIn, who: AnyStaff, staff: Staff) -> None:
    await staff.auth.change_password(who.user, who.token, body.current_password, body.new_password)
