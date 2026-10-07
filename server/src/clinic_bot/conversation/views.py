"""Domain objects → LLM-facing data and widget UI payloads."""

from __future__ import annotations

from collections.abc import Sequence

from clinic_bot.conversation.result import (
    AppointmentButtons,
    AppointmentChip,
    ConfirmationCard,
    DoctorCard,
    DoctorCards,
    SlotButtons,
    SlotChip,
    SlotGroup,
)
from clinic_bot.domain.entities import Appointment, Doctor
from clinic_bot.domain.enums import VisitType
from clinic_bot.ports.messages import MessageCatalog
from clinic_bot.services.directory import DoctorDirectory
from clinic_bot.services.scheduling import SlotOffer, day_label, time_label


def doctor_data(d: Doctor, *, with_fees: bool = False) -> dict[str, object]:
    """Fees go to the LLM only when the patient asked about cost."""
    data: dict[str, object] = {
        "doctor_id": d.id,
        "name": d.name,
        "specialty": d.specialty.label,
        "days": d.days_label(),
        "hours": d.hours,
    }
    if with_fees:
        data |= {"fee": d.fee.display(), "followup_fee": d.followup_fee.display()}
    return data


def doctor_line(d: Doctor) -> str:
    return f"doctor_id {d.id}: {d.name}, {d.specialty.label}, {d.days_label()}, {d.hours}"


def doctor_cards(doctors: Sequence[Doctor], messages: MessageCatalog) -> DoctorCards:
    return DoctorCards(
        doctors=[
            DoctorCard(
                name=d.name,
                specialty=d.specialty.label,
                days=d.days_label(),
                hours=d.hours,
                text=messages.get("ui.choose_doctor", doctor=d.name),
            )
            for d in doctors
        ]
    )


def slot_buttons(
    offers: Sequence[SlotOffer],
    directory: DoctorDirectory,
    selected_doctor_id: int | None,
    messages: MessageCatalog,
) -> SlotButtons:
    groups = []
    for offer in offers:
        doctor = directory.get(offer.doctor_id)
        key = "ui.slot" if offer.doctor_id == selected_doctor_id else "ui.slot_other_doctor"
        chips = [
            SlotChip(
                label=time_label(s),
                text=messages.get(key, date=offer.label, time=time_label(s), doctor=doctor.name),
            )
            for s in offer.slots
        ]
        groups.append(SlotGroup(date_label=offer.label, doctor=doctor.name, slots=chips))
    return SlotButtons(groups=groups)


def slot_data(offers: Sequence[SlotOffer], directory: DoctorDirectory) -> list[dict[str, object]]:
    return [
        {
            "doctor": directory.get(o.doctor_id).name,
            "resolved_date": o.resolved_date.isoformat(),
            "date_label": o.label,
            "slots": [{"slot_id": s.id, "time": time_label(s)} for s in o.slots],
        }
        for o in offers
    ]


def appointment_label(
    appt: Appointment, directory: DoctorDirectory, messages: MessageCatalog
) -> str:
    doctor = directory.get(appt.doctor_id)
    return messages.get(
        "ui.appointment",
        doctor=doctor.name,
        date=day_label(appt.slot.day),
        time=time_label(appt.slot),
    )


def appointment_buttons(
    appts: Sequence[Appointment], directory: DoctorDirectory, messages: MessageCatalog
) -> AppointmentButtons:
    chips = []
    for appt in appts:
        label = appointment_label(appt, directory, messages)
        chips.append(
            AppointmentChip(
                label=label, text=messages.get("ui.cancel_appointment", appointment=label)
            )
        )
    return AppointmentButtons(appointments=chips)


def appointment_ref(appointment_id: int) -> str:
    return f"A-{appointment_id:05d}"


def visit_type_label(visit_type: VisitType, messages: MessageCatalog) -> str:
    return messages.get(f"visit_type.{visit_type.value}")


def confirmation_card(
    appt: Appointment, doctor: Doctor, messages: MessageCatalog
) -> ConfirmationCard:
    return ConfirmationCard(
        doctor=doctor.name,
        specialty=doctor.specialty.label,
        date=day_label(appt.slot.day),
        time=time_label(appt.slot),
        visit_type=visit_type_label(appt.visit_type, messages),
        appointment_ref=appointment_ref(appt.id or 0),
    )
