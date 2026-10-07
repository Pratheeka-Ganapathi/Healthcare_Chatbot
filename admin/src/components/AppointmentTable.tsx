import type { AppointmentSummary } from "../api/types";
import { ageSex, VISIT_TYPE_LABELS } from "../lib/format";
import { navigate } from "../routing/useHashRoute";
import { StatusBadge } from "./StatusBadge";

interface Props {
  appointments: AppointmentSummary[];
  hrefFor: (id: number) => string;
  showDoctor?: boolean;
  emptyText: string;
}

export function AppointmentTable({ appointments, hrefFor, showDoctor = false, emptyText }: Props) {
  if (appointments.length === 0) return <p className="empty">{emptyText}</p>;
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Time</th>
            {showDoctor && <th scope="col">Doctor</th>}
            <th scope="col">Patient</th>
            <th scope="col">Visit</th>
            <th scope="col">Status</th>
            <th scope="col">Complaint</th>
            <th scope="col">Consultation</th>
          </tr>
        </thead>
        <tbody>
          {appointments.map((appt) => (
            <tr key={appt.id} className="row-link" onClick={() => navigate(hrefFor(appt.id))}>
              <td className="nowrap">
                <a href={hrefFor(appt.id)} onClick={(event) => event.stopPropagation()}>
                  {appt.date_label}
                </a>
              </td>
              <td className="nowrap">{appt.time_label}</td>
              {showDoctor && <td>{appt.doctor_name}</td>}
              <td>
                {appt.patient.name}{" "}
                <span className="muted nowrap">{ageSex(appt.patient.age, appt.patient.sex)}</span>
              </td>
              <td className="nowrap">{VISIT_TYPE_LABELS[appt.visit_type]}</td>
              <td>
                <StatusBadge status={appt.status} />
              </td>
              <td className="clip" title={appt.chief_complaint ?? undefined}>
                {appt.chief_complaint ?? <span className="muted">—</span>}
              </td>
              <td className="center">
                {appt.has_consultation ? (
                  <span className="tick" title="Consultation recorded">
                    ✓<span className="sr-only"> Consultation recorded</span>
                  </span>
                ) : (
                  <span className="muted" title="Not recorded yet">
                    —<span className="sr-only"> Not recorded yet</span>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
