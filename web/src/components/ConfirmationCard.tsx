import type { ConfirmationCard as ConfirmationPayload } from "../ui/types";

/** Styled after the paper OPD token slip a clinic front desk hands you. */
export function ConfirmationCard({ payload }: { payload: ConfirmationPayload }) {
  return (
    <article className="token" aria-label="Appointment confirmed">
      <header className="token-head">
        <span>City Care Clinic</span>
        <span>Appointment</span>
      </header>
      <p className="token-ref">{payload.appointment_ref}</p>
      <dl className="token-grid">
        <dt>Doctor</dt>
        <dd>{payload.doctor}</dd>
        <dt>Department</dt>
        <dd>{payload.specialty}</dd>
        <dt>Date</dt>
        <dd>{payload.date}</dd>
        <dt>Time</dt>
        <dd>{payload.time}</dd>
        <dt>Visit</dt>
        <dd className="token-visit">{payload.visit_type}</dd>
      </dl>
      <footer className="token-foot">Please arrive 10 minutes early.</footer>
    </article>
  );
}
