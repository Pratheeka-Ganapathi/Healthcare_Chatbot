"""The synthetic clinic: doctors, patients and seed constants (SPEC 9.1). Pure data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

SLOT_MINUTES = 15
WINDOW_DAYS = 7
PREBOOK_RATE = 0.25
SEED_SESSION = "seed"


@dataclass(frozen=True)
class DoctorSeed:
    name: str
    specialty: str
    bio: str
    days: tuple[int, ...]
    sessions: tuple[tuple[time, time], ...]
    fee_rupees: int
    followup_rupees: int

    def hours_label(self) -> str:
        fmt = "%I:%M %p"
        return ", ".join(
            f"{s.strftime(fmt).lstrip('0')} - {e.strftime(fmt).lstrip('0')}"
            for s, e in self.sessions
        )


MORNING = (time(9, 30), time(12, 30))
EVENING = (time(17, 0), time(20, 0))

DOCTORS: tuple[DoctorSeed, ...] = (
    DoctorSeed(
        "Dr. Rao",
        "general_medicine",
        "General physician, adult medicine.",
        (0, 1, 2, 3, 4, 5),
        (MORNING, EVENING),
        600,
        300,
    ),
    DoctorSeed(
        "Dr. Rao S",
        "general_medicine",
        "General physician, lifestyle and preventive care.",
        (0, 2, 4),
        (EVENING,),
        600,
        300,
    ),
    DoctorSeed(
        "Dr. Priya Nair", "general_medicine", "General physician.", (1, 3, 5), (MORNING,), 500, 250
    ),
    DoctorSeed(
        "Dr. Kavya Shetty",
        "dermatology",
        "Dermatologist.",
        (0, 2, 4),
        ((time(16, 30), time(19, 30)),),
        800,
        400,
    ),
    DoctorSeed(
        "Dr. Arjun Menon",
        "orthopaedics",
        "Orthopaedic surgeon.",
        (1, 3, 5),
        ((time(10, 0), time(12, 30)), (time(17, 0), time(19, 0))),
        900,
        450,
    ),
    DoctorSeed(
        "Dr. Lakshmi Iyer", "paediatrics", "Paediatrician.", (0, 1, 2, 3, 4), (MORNING,), 700, 350
    ),
    DoctorSeed(
        "Dr. Farah Khan",
        "gynaecology",
        "Gynaecologist.",
        (0, 1, 3, 4),
        ((time(16, 0), time(19, 0)),),
        900,
        450,
    ),
    DoctorSeed(
        "Dr. Vikram Gowda",
        "ent",
        "ENT specialist.",
        (0, 2, 5),
        ((time(10, 0), time(12, 30)), (time(17, 0), time(19, 0))),
        750,
        375,
    ),
)


@dataclass(frozen=True)
class PatientSeed:
    name: str
    phone: str
    dob: date
    sex: str
    demo_note: str | None = None


PATIENTS: tuple[PatientSeed, ...] = (
    PatientSeed(
        "Asha Kumar", "9000000001", date(1990, 6, 5), "female", "Has a follow-up grant with Dr. Rao"
    ),
    PatientSeed("Rahul Verma", "9000000002", date(1985, 11, 20), "male"),
    PatientSeed(
        "Meena Pillai",
        "9000000003",
        date(1972, 2, 14),
        "female",
        "Has an appointment in about an hour (cancel cutoff demo)",
    ),
    PatientSeed("Kiran Reddy", "9000000004", date(2012, 8, 30), "male"),
    PatientSeed("Sanjay Joshi", "9000000005", date(1995, 3, 3), "male", "No bookings yet"),
    PatientSeed("Fatima Sheikh", "9000000006", date(1988, 9, 9), "female"),
)


def demo_patients() -> list[dict[str, str]]:
    """The three test patients shown in the widget's "Try it" panel."""
    shown = [p for p in PATIENTS if p.demo_note]
    return [
        {
            "name": p.name,
            "phone": p.phone,
            "dob": p.dob.strftime("%d/%m/%Y"),
            "note": p.demo_note or "",
        }
        for p in shown
    ]
