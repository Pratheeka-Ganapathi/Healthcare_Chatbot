import type { AppointmentStatus, Role, Sex, VisitType } from "../api/types";

const CLINIC_TZ = "Asia/Kolkata";

export function formatRupees(amount: number): string {
  return `₹${amount.toLocaleString("en-IN")}`;
}

/** ISO timestamp → "7 Oct 2026, 6:15 pm" in clinic time. */
export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-IN", {
    timeZone: CLINIC_TZ,
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Plain date "2026-10-21" → "Wed 21 Oct 2026" (no timezone shift). */
export function formatDate(isoDate: string | null): string {
  if (!isoDate) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!match) return isoDate;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return date.toLocaleDateString("en-GB", {
    timeZone: "UTC",
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Today's date in clinic time as YYYY-MM-DD (for date inputs). */
export function todayInClinic(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: CLINIC_TZ });
}

export const STATUS_LABELS: Record<AppointmentStatus, string> = {
  booked: "Booked",
  cancelled: "Cancelled",
  completed: "Completed",
  no_show: "No-show",
};

export const VISIT_TYPE_LABELS: Record<VisitType, string> = {
  new: "New visit",
  followup: "Follow-up",
};

export const SEX_LABELS: Record<Sex, string> = { female: "Female", male: "Male", other: "Other" };

export const ROLE_LABELS: Record<Role, string> = { admin: "Admin", doctor: "Doctor" };

/** "34 F" style short label for tables. */
export function ageSex(age: number, sex: Sex): string {
  return `${age} ${SEX_LABELS[sex].charAt(0)}`;
}
