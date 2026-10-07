import type { AppointmentDetail } from "../api/types";
import { formatRupees, VISIT_TYPE_LABELS } from "../lib/format";
import { StatusBadge } from "./StatusBadge";

export function VisitInfo({ detail }: { detail: AppointmentDetail }) {
  return (
    <section className="card" aria-labelledby="visit-heading">
      <h2 id="visit-heading">Visit</h2>
      <dl className="facts">
        <dt>Date</dt>
        <dd>{detail.date_label}</dd>
        <dt>Time</dt>
        <dd>{detail.time_label}</dd>
        <dt>Doctor</dt>
        <dd>{detail.doctor_name}</dd>
        <dt>Visit type</dt>
        <dd>{VISIT_TYPE_LABELS[detail.visit_type]}</dd>
        <dt>Fee</dt>
        <dd>{formatRupees(detail.fee_rupees)}</dd>
        <dt>Status</dt>
        <dd>
          <StatusBadge status={detail.status} />
        </dd>
      </dl>
    </section>
  );
}
