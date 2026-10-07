import type { AppointmentDetail } from "../api/types";
import { ChatSummaries } from "./ChatSummaries";
import { ConsultationForm } from "./ConsultationForm";
import { ConsultationSummary } from "./ConsultationSummary";
import { HistoryList } from "./HistoryList";
import { IntakeSummary } from "./IntakeSummary";
import { Notice } from "./Notice";
import { PatientCard } from "./PatientCard";
import { StatusBadge } from "./StatusBadge";
import { VisitDetailsForm } from "./VisitDetailsForm";
import { VisitInfo } from "./VisitInfo";

interface Props {
  detail: AppointmentDetail;
  /** Given for the doctor's editable view; omitted for the admin's read-only view. */
  onSaved?: (detail: AppointmentDetail) => void;
}

function lockedReason(detail: AppointmentDetail): string {
  return detail.status === "cancelled"
    ? "The patient cancelled this appointment, so the visit details and consultation cannot be recorded."
    : "This appointment is on a later day. You can record the visit details and consultation from the day of the visit.";
}

export function AppointmentDetailView({ detail, onSaved }: Props) {
  const locked = !detail.can_record;
  return (
    <div className="detail">
      <div className="page-head">
        <h1>{detail.patient.name}</h1>
        <div className="page-head-extra">
          <span className="muted">
            {detail.date_label}, {detail.time_label} · {detail.doctor_name}
          </span>
          <StatusBadge status={detail.status} />
        </div>
      </div>
      <div className="card-grid">
        <PatientCard patient={detail.patient} />
        <VisitInfo detail={detail} />
      </div>
      {onSaved ? (
        <>
          {locked && <Notice tone="info">{lockedReason(detail)}</Notice>}
          <div className="card-grid">
            <VisitDetailsForm detail={detail} disabled={locked} onSaved={onSaved} />
            <IntakeSummary intake={detail.intake} showVisitFields={false} />
          </div>
          <ConsultationForm detail={detail} disabled={locked} onSaved={onSaved} />
        </>
      ) : (
        <div className="card-grid">
          <IntakeSummary intake={detail.intake} showVisitFields />
          <ConsultationSummary consultation={detail.consultation} />
        </div>
      )}
      <div className="card-grid">
        <ChatSummaries items={detail.chat_summaries} />
        <HistoryList items={detail.history} currentAppointmentId={detail.id} />
      </div>
    </div>
  );
}
