"""Domain errors → HTTP for the staff API: ``{"detail": "<message>"}`` (SPEC 17.5).

Staff-facing text, so it lives here rather than in the patient message catalog.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from clinic_bot.domain.errors import (
    Conflict,
    DomainError,
    ErrorCode,
    Forbidden,
    InvalidInput,
    Locked,
    NotFound,
    SlotTaken,
    Unauthorized,
    Unavailable,
)

_STATUS: tuple[tuple[type[DomainError], int], ...] = (
    (Unauthorized, 401),
    (Forbidden, 403),
    (NotFound, 404),
    (Conflict, 409),
    (SlotTaken, 409),
    (Locked, 429),
    (Unavailable, 503),
)
_MESSAGES = {
    ErrorCode.AUTH_FAILED: "Invalid email or password.",
    ErrorCode.LOCKED: "Too many failed sign-ins. Try again in 15 minutes.",
    ErrorCode.FORBIDDEN: "You do not have access to this.",
    ErrorCode.NOT_FOUND: "Not found.",
    ErrorCode.BAD_EMAIL: "Enter a valid email address.",
    ErrorCode.WEAK_PASSWORD: "Passwords need 8 to 128 characters.",
    ErrorCode.BAD_NAME: "Names need 2 to 80 characters.",
    ErrorCode.EMAIL_TAKEN: "An account with this email already exists.",
    ErrorCode.DOCTOR_HAS_ACCOUNT: "This doctor already has a login.",
    ErrorCode.SELF_DEACTIVATE: "You cannot deactivate your own account.",
    ErrorCode.NOT_RECORDABLE: "This appointment is cancelled or on a later day.",
    ErrorCode.PAST_DAY: "Choose today or a later day.",
    ErrorCode.EXISTS: "That day is already closed.",
    ErrorCode.NO_HEADING: "Each document needs at least one section heading starting with '# '.",
    ErrorCode.SLOT_TAKEN: "Another booking now holds this slot.",
    ErrorCode.BUSY: "The server is busy. Please try again.",
}
WRONG_CURRENT_PASSWORD = "Your current password is not correct."


def status_of(exc: DomainError) -> int:
    return next((code for cls, code in _STATUS if isinstance(exc, cls)), 400)


def message_of(exc: DomainError) -> str:
    if isinstance(exc, InvalidInput) and exc.code is ErrorCode.AUTH_FAILED:
        return WRONG_CURRENT_PASSWORD  # a 400, so the portal does not sign the user out
    if exc.code in _MESSAGES:
        return _MESSAGES[exc.code]
    text = exc.detail or "That change is not allowed."
    return text[:1].upper() + text[1:].rstrip(".") + "."


async def domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return JSONResponse({"detail": message_of(exc)}, status_code=status_of(exc))
