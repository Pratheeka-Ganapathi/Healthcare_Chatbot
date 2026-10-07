import type { Consultation } from "../api/types";
import { formatDate, formatDateTime } from "../lib/format";

/** Read-only consultation for the admin view. */
export function ConsultationSummary({ consultation }: { consultation: Consultation | null }) {
  return (
    <section className="card" aria-labelledby="consultation-heading">
      <h2 id="consultation-heading">Consultation</h2>
      {!consultation ? (
        <p className="muted">No consultation recorded yet.</p>
      ) : (
        <dl className="facts facts-wide">
          <dt>Diagnosis</dt>
          <dd>{consultation.diagnosis || "—"}</dd>
          <dt>Notes</dt>
          <dd className="pre">{consultation.notes || "—"}</dd>
          <dt>Medication</dt>
          <dd className="pre">{consultation.medication || "—"}</dd>
          <dt>Follow-up</dt>
          <dd>
            {consultation.followup_required
              ? `Within ${consultation.followup_in_days ?? "?"} days (valid until ${formatDate(
                  consultation.followup_valid_until,
                )})`
              : "Not required"}
          </dd>
          <dt>Submitted by</dt>
          <dd>
            {consultation.submitted_by}, {formatDateTime(consultation.updated_at)}
          </dd>
        </dl>
      )}
    </section>
  );
}
