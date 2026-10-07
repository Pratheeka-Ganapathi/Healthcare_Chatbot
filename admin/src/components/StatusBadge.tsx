import type { AppointmentStatus } from "../api/types";
import { STATUS_LABELS } from "../lib/format";

export function StatusBadge({ status }: { status: AppointmentStatus }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABELS[status]}</span>;
}
