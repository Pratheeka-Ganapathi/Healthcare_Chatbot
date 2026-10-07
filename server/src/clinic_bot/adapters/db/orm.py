"""SQLAlchemy 2.0 mapped classes (PostgreSQL). Datetimes are stored naive in Asia/Kolkata."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PatientRow(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(10), unique=True)
    dob: Mapped[date] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class DoctorRow(Base):
    __tablename__ = "doctors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    specialty: Mapped[str] = mapped_column(String(40), index=True)
    bio: Mapped[str] = mapped_column(Text)
    consulting_days: Mapped[str] = mapped_column(String(20))  # "0,1,2,3,4,5"
    hours: Mapped[str] = mapped_column(String(80))
    fee: Mapped[int] = mapped_column(Integer)  # paise
    followup_fee: Mapped[int] = mapped_column(Integer)  # paise


class SlotRow(Base):
    __tablename__ = "slots"
    __table_args__ = (
        UniqueConstraint("doctor_id", "start"),
        Index("ix_slots_doctor_start", "doctor_id", "start"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    start: Mapped[datetime] = mapped_column(DateTime)
    end: Mapped[datetime] = mapped_column(DateTime)


class ClosureRow(Base):
    __tablename__ = "closures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True)
    reason: Mapped[str] = mapped_column(String(200))


class AppointmentRow(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index(
            "uq_appointments_active_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status = 'booked'"),
        ),
        # Idempotency key. Partial, like the slot index, so a slot cancelled in this
        # session can be booked again in the same session.
        Index(
            "uq_appointments_session_slot",
            "session_id",
            "slot_id",
            unique=True,
            postgresql_where=text("status = 'booked'"),
        ),
        Index("ix_appointments_patient_status", "patient_id", "status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"))
    visit_type: Mapped[str] = mapped_column(String(10))
    fee: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10))
    intake_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    session_id: Mapped[str] = mapped_column(String(64))
    followup_grant_id: Mapped[int | None] = mapped_column(
        ForeignKey("followup_grants.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FollowupGrantRow(Base):
    __tablename__ = "followup_grants"
    __table_args__ = (
        Index("ix_grants_patient_doctor_valid", "patient_id", "doctor_id", "valid_until"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    source_appointment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_until: Mapped[date] = mapped_column(Date)
    created_by: Mapped[str] = mapped_column(String(80))
    used_appointment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class VerifyAttemptRow(Base):
    __tablename__ = "verify_attempts"
    __table_args__ = (Index("ix_verify_phone_ts", "phone_norm", "ts"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone_norm: Mapped[str] = mapped_column(String(10))
    ts: Mapped[datetime] = mapped_column(DateTime)
    success: Mapped[bool]


class TranscriptRow(Base):
    __tablename__ = "transcripts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64))
    patient_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turns: Mapped[list[dict[str, str]]] = mapped_column(JSON)
    guardrail_events: Mapped[list[dict[str, str]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class ChatSummaryRow(Base):
    __tablename__ = "chat_summaries"
    __table_args__ = (Index("ix_chat_summaries_patient", "patient_id", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    session_id: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class CallbackRow(Base):
    __tablename__ = "callbacks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text)  # LLM-supplied, so unbounded
    summary: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime)


# Staff portal (SPEC 17.4)


class StaffUserRow(Base):
    __tablename__ = "staff_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(10))
    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctors.id"), unique=True, nullable=True
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StaffSessionRow(Base):
    __tablename__ = "staff_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("staff_users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class ConsultationRow(Base):
    __tablename__ = "consultations"
    __table_args__ = (Index("ix_consultations_patient", "patient_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), unique=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    notes: Mapped[str] = mapped_column(Text)
    diagnosis: Mapped[str] = mapped_column(Text)
    medication: Mapped[str] = mapped_column(Text)
    followup_required: Mapped[bool] = mapped_column(Boolean)
    followup_in_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    followup_grant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("staff_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class ClinicDocRow(Base):
    __tablename__ = "clinic_docs"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
