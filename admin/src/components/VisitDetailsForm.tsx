import { useState, type FormEvent } from "react";

import { updateDoctorAppointment } from "../api/client";
import type { AppointmentDetail, AppointmentUpdate, EditableStatus } from "../api/types";
import { STATUS_LABELS } from "../lib/format";
import { useSubmit } from "../lib/useSubmit";
import { FormMessages } from "./FormMessages";

const STATUSES: EditableStatus[] = ["booked", "completed", "no_show"];
const SEVERITIES = Array.from({ length: 10 }, (_, i) => String(i + 1));

interface Fields {
  status: EditableStatus | null;
  chief_complaint: string;
  duration: string;
  severity: string;
}

interface Props {
  detail: AppointmentDetail;
  disabled: boolean;
  onSaved: (detail: AppointmentDetail) => void;
}

function savedFields(detail: AppointmentDetail): Fields {
  const severity = detail.intake?.severity;
  return {
    status: detail.status === "cancelled" ? null : detail.status,
    chief_complaint: detail.intake?.chief_complaint ?? "",
    duration: detail.intake?.duration ?? "",
    severity: severity === null || severity === undefined ? "" : String(severity),
  };
}

/** Status plus the intake visit fields. Untouched fields follow the latest saved detail. */
export function VisitDetailsForm({ detail, disabled, onSaved }: Props) {
  const [draft, setDraft] = useState<Partial<Fields>>({});
  const submit = useSubmit();
  const saved = savedFields(detail);
  const fields: Fields = { ...saved, ...draft };

  const edit = (patch: Partial<Fields>) => {
    setDraft((current) => ({ ...current, ...patch }));
    submit.clear();
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const body: AppointmentUpdate = {};
    if (fields.status && fields.status !== saved.status) body.status = fields.status;
    const intakeChanged =
      fields.chief_complaint !== saved.chief_complaint ||
      fields.duration !== saved.duration ||
      fields.severity !== saved.severity;
    if (intakeChanged) {
      if (!fields.chief_complaint.trim()) return submit.fail("Enter the chief complaint.");
      body.intake = {
        chief_complaint: fields.chief_complaint.trim(),
        duration: fields.duration.trim() || null,
        severity: fields.severity === "" ? null : Number(fields.severity),
      };
    }
    if (!body.status && !body.intake) return submit.fail("Nothing has changed yet.");
    void submit.run(async () => {
      const updated = await updateDoctorAppointment(detail.id, body);
      setDraft({});
      onSaved(updated);
      return "Visit details saved.";
    });
  };

  return (
    <section className="card" aria-labelledby="visit-details-heading">
      <h2 id="visit-details-heading">Visit details</h2>
      <form className="form" onSubmit={onSubmit}>
        <fieldset disabled={disabled || submit.busy}>
          {fields.status === null ? (
            <p>
              <strong>Status:</strong> {STATUS_LABELS.cancelled} by the patient through the chatbot.
            </p>
          ) : (
            <div className="field">
              <label htmlFor="visit-status">Status</label>
              <select
                id="visit-status"
                value={fields.status}
                onChange={(e) => edit({ status: e.target.value as EditableStatus })}
              >
                {STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {STATUS_LABELS[status]}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="field">
            <label htmlFor="visit-complaint">Chief complaint</label>
            <input
              id="visit-complaint"
              type="text"
              value={fields.chief_complaint}
              onChange={(e) => edit({ chief_complaint: e.target.value })}
            />
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="visit-duration">Duration</label>
              <input
                id="visit-duration"
                type="text"
                placeholder="e.g. 3 days"
                value={fields.duration}
                onChange={(e) => edit({ duration: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="visit-severity">Severity (1 to 10)</label>
              <select
                id="visit-severity"
                value={fields.severity}
                onChange={(e) => edit({ severity: e.target.value })}
              >
                <option value="">Not recorded</option>
                {SEVERITIES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="form-actions">
            <button type="submit" className="btn btn-primary">
              {submit.busy ? "Saving…" : "Save visit details"}
            </button>
          </div>
        </fieldset>
        <FormMessages submit={submit} />
      </form>
    </section>
  );
}
