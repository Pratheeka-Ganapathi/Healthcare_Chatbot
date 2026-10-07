import type { Intake } from "../api/types";

interface Props {
  intake: Intake | null;
  /** Also show complaint, duration and severity (the read-only view; doctors edit them). */
  showVisitFields: boolean;
}

export function IntakeSummary({ intake, showVisitFields }: Props) {
  return (
    <section className="card" aria-labelledby="intake-heading">
      <h2 id="intake-heading">Intake from the chatbot</h2>
      {!intake ? (
        <p className="muted">The chatbot did not collect an intake for this visit.</p>
      ) : (
        <>
          {showVisitFields && (
            <dl className="facts">
              <dt>Chief complaint</dt>
              <dd>{intake.chief_complaint}</dd>
              <dt>Duration</dt>
              <dd>{intake.duration ?? "—"}</dd>
              <dt>Severity</dt>
              <dd>{intake.severity === null ? "—" : `${intake.severity} / 10`}</dd>
            </dl>
          )}
          {intake.answers.length > 0 ? (
            <dl className="qa">
              {intake.answers.map((item, index) => (
                <div key={index} className="qa-item">
                  <dt>{item.q}</dt>
                  <dd>{item.a}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="muted">No intake answers recorded.</p>
          )}
          {intake.red_flags_checked.length > 0 && (
            <p className="small">
              <strong>Red flags asked about:</strong> {intake.red_flags_checked.join(", ")}
            </p>
          )}
        </>
      )}
    </section>
  );
}
