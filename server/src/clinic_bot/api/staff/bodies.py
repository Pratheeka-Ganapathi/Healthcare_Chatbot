"""Request bodies of the staff API (SPEC 17.5). Money is whole rupees."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class IntakeIn(BaseModel):
    chief_complaint: str = Field(min_length=1, max_length=500)
    duration: str | None = Field(default=None, max_length=100)
    severity: int | None = Field(default=None, ge=1, le=10)


class VisitPatchIn(BaseModel):
    status: Literal["booked", "completed", "no_show"] | None = None
    intake: IntakeIn | None = None


class ConsultationIn(BaseModel):
    notes: str = Field(default="", max_length=5000)
    diagnosis: str = Field(default="", max_length=5000)
    medication: str = Field(default="", max_length=5000)
    followup_required: bool = False
    followup_in_days: int | None = None


class DoctorIn(BaseModel):
    name: str = Field(max_length=80)
    bio: str = Field(max_length=1000)
    fee_rupees: int
    followup_fee_rupees: int


class AccountIn(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(max_length=80)
    password: str = Field(max_length=128)
    doctor_id: int


class AccountPatchIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    active: bool | None = None
    password: str | None = Field(default=None, max_length=128)


class DocIn(BaseModel):
    content: str = Field(max_length=50_000)


class ClosureIn(BaseModel):
    date: date
    reason: str = Field(max_length=200)
