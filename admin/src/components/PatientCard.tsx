import type { PatientDetail } from "../api/types";
import { formatDate, SEX_LABELS } from "../lib/format";

export function PatientCard({ patient }: { patient: PatientDetail }) {
  return (
    <section className="card" aria-labelledby="patient-heading">
      <h2 id="patient-heading">Patient</h2>
      <dl className="facts">
        <dt>Name</dt>
        <dd>{patient.name}</dd>
        <dt>Age</dt>
        <dd>{patient.age}</dd>
        <dt>Sex</dt>
        <dd>{SEX_LABELS[patient.sex]}</dd>
        <dt>Phone</dt>
        <dd>
          <a href={`tel:${patient.phone}`}>{patient.phone}</a>
        </dd>
        <dt>Date of birth</dt>
        <dd>{formatDate(patient.dob)}</dd>
      </dl>
    </section>
  );
}
