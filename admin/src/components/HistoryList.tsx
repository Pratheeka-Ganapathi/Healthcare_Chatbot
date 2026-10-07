import type { HistoryItem } from "../api/types";

interface Props {
  items: HistoryItem[];
  currentAppointmentId: number;
}

export function HistoryList({ items, currentAppointmentId }: Props) {
  const earlier = items.filter((item) => item.appointment_id !== currentAppointmentId);
  return (
    <section className="card" aria-labelledby="history-heading">
      <h2 id="history-heading">Previous consultations</h2>
      {earlier.length === 0 ? (
        <p className="muted">No earlier consultations for this patient.</p>
      ) : (
        <ul className="timeline">
          {earlier.map((item) => (
            <li key={item.appointment_id}>
              <p className="timeline-meta">
                {item.date_label} · {item.doctor_name}
                {item.followup_required && <span className="badge badge-info">Follow-up</span>}
              </p>
              <p>
                <strong>{item.diagnosis || "No diagnosis recorded"}</strong>
              </p>
              {item.notes && <p className="pre">{item.notes}</p>}
              {item.medication && (
                <p className="pre small">
                  <span className="muted">Medication: </span>
                  {item.medication}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
