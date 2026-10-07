"""Closed vocabularies shared across the core."""

from __future__ import annotations

from enum import StrEnum


class Specialty(StrEnum):
    GENERAL_MEDICINE = "general_medicine"
    DERMATOLOGY = "dermatology"
    ORTHOPAEDICS = "orthopaedics"
    PAEDIATRICS = "paediatrics"
    GYNAECOLOGY = "gynaecology"
    ENT = "ent"

    @property
    def label(self) -> str:
        return _SPECIALTY_LABELS[self]


_SPECIALTY_LABELS = {
    Specialty.GENERAL_MEDICINE: "General Medicine",
    Specialty.DERMATOLOGY: "Dermatology",
    Specialty.ORTHOPAEDICS: "Orthopaedics",
    Specialty.PAEDIATRICS: "Paediatrics",
    Specialty.GYNAECOLOGY: "Gynaecology",
    Specialty.ENT: "ENT",
}


class VisitType(StrEnum):
    NEW = "new"
    FOLLOWUP = "followup"


class TimePref(StrEnum):
    MORNING = "morning"
    EVENING = "evening"
    ANY = "any"


class AppointmentStatus(StrEnum):
    BOOKED = "booked"
    CANCELLED = "cancelled"  # only the patient, through the bot
    COMPLETED = "completed"  # set by the doctor (SPEC 17.2)
    NO_SHOW = "no_show"


class Intent(StrEnum):
    BOOK = "book"
    CANCEL = "cancel"
    FAQ = "faq"


class GuardrailLabel(StrEnum):
    EMERGENCY = "EMERGENCY"
    SELF_HARM = "SELF_HARM"
    MEDICATION = "MEDICATION"
    OFF_TOPIC = "OFF_TOPIC"
    NONE = "NONE"


class CallbackPriority(StrEnum):
    NORMAL = "normal"
    HIGH = "high"


class StaffRole(StrEnum):
    ADMIN = "admin"
    DOCTOR = "doctor"


class Sex(StrEnum):
    FEMALE = "female"
    MALE = "male"
    OTHER = "other"
