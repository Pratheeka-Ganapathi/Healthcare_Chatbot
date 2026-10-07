"""Staff portal use cases (SPEC 17). The API reaches them through ``StaffServices``."""

from __future__ import annotations

from dataclasses import dataclass

from clinic_bot.ports.clock import Clock
from clinic_bot.ports.staff import TableBrowser
from clinic_bot.services.directory import DoctorDirectory
from clinic_bot.services.staff.accounts import AccountService
from clinic_bot.services.staff.auth import StaffAuthService
from clinic_bot.services.staff.clinic import ClinicAdminService
from clinic_bot.services.staff.clinic_docs import ClinicDocService
from clinic_bot.services.staff.consultations import ConsultationService
from clinic_bot.services.staff.records import VisitRecords


@dataclass(frozen=True, slots=True)
class StaffServices:
    auth: StaffAuthService
    accounts: AccountService
    records: VisitRecords
    consultations: ConsultationService
    clinic: ClinicAdminService
    docs: ClinicDocService
    tables: TableBrowser
    directory: DoctorDirectory
    clock: Clock
