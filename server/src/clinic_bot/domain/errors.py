"""Error codes and the domain error hierarchy.

``ErrorCode`` is the shared vocabulary between tools, eval and the widget.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    BAD_PHONE = "BAD_PHONE"
    BAD_DOB = "BAD_DOB"
    BAD_NAME = "BAD_NAME"
    NO_MATCH = "NO_MATCH"
    LOCKED = "LOCKED"
    NO_DOCTORS = "NO_DOCTORS"
    INVALID_CHOICE = "INVALID_CHOICE"
    INVALID = "INVALID"
    NO_SLOTS = "NO_SLOTS"
    BAD_DAY = "BAD_DAY"
    CLOSED = "CLOSED"
    NONE = "NONE"
    NOT_VERIFIED = "NOT_VERIFIED"
    SLOT_TAKEN = "SLOT_TAKEN"
    DUPLICATE_SAME_DAY = "DUPLICATE_SAME_DAY"
    OVERLAP = "OVERLAP"
    CAP_REACHED = "CAP_REACHED"
    NOT_OWNER = "NOT_OWNER"
    CUTOFF_VIOLATION = "CUTOFF_VIOLATION"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_FOUND = "NOT_FOUND"
    BLOCKED = "BLOCKED"
    BUSY = "BUSY"
    INTERNAL = "INTERNAL"
    # Staff portal (SPEC 17)
    AUTH_FAILED = "AUTH_FAILED"
    FORBIDDEN = "FORBIDDEN"
    BAD_EMAIL = "BAD_EMAIL"
    WEAK_PASSWORD = "WEAK_PASSWORD"
    EMAIL_TAKEN = "EMAIL_TAKEN"
    DOCTOR_HAS_ACCOUNT = "DOCTOR_HAS_ACCOUNT"
    SELF_DEACTIVATE = "SELF_DEACTIVATE"
    NOT_RECORDABLE = "NOT_RECORDABLE"
    PAST_DAY = "PAST_DAY"
    EXISTS = "EXISTS"
    NO_HEADING = "NO_HEADING"


class DomainError(Exception):
    """Base class for every expected, user-recoverable failure."""

    def __init__(self, code: ErrorCode, detail: str = "", **data: object) -> None:
        super().__init__(f"{code}: {detail}" if detail else str(code))
        self.code = code
        self.detail = detail
        self.data: dict[str, object] = dict(data)


class InvalidInput(DomainError):
    """Input could not be parsed or validated."""


class InvalidChoice(DomainError):
    """An id that was not offered in this session."""


class NotVerified(DomainError):
    """Patient data requested before verification succeeded."""


class Locked(DomainError):
    """Verification is temporarily locked for this phone number."""


class NotFound(DomainError):
    """Nothing matched (patient, slots, doctors, documents)."""


class NotOwner(DomainError):
    """The appointment belongs to someone else."""


class BookingRejected(DomainError):
    """A booking rule (duplicate, overlap, cap) rejected the request."""


class SlotTaken(DomainError):
    """Another session booked the slot first."""


class CutoffViolation(DomainError):
    """Cancellation attempted inside the cutoff window."""


class Unauthorized(DomainError):
    """Staff login failed, or the session token is missing, expired or revoked."""


class Forbidden(DomainError):
    """A signed-in staff user without the role for this action."""


class Conflict(DomainError):
    """The change clashes with existing data (email taken, closure exists, wrong state)."""


class Unavailable(DomainError):
    """An upstream dependency is busy or failed (rate limit, timeout)."""
