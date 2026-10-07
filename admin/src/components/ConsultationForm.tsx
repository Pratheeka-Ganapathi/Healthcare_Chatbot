import { useState, type FormEvent } from "react";

import { saveConsultation } from "../api/client";
import type { AppointmentDetail, ConsultationRequest } from "../api/types";
import { formatDate, formatDateTime } from "../lib/format";
import { useSubmit } from "../lib/useSubmit";
import { FormMessages } from "./FormMessages";

const DEFAULT_FOLLOWUP_DAYS = 14;

interface Props {
  detail: AppointmentDetail;
  disabled: boolean;
  onSaved: (detail: AppointmentDetail) => void;
}

function initialForm(detail: AppointmentDetail) {
  const c = detail.consultation;
  return {
    diagnosis: c?.diagnosis ?? "",
    notes: c?.notes ?? "",
    medication: c?.medication ?? "",
    followupRequired: c?.followup_required ?? false,
    followupDays: String(c?.followup_in_days ?? DEFAULT_FOLLOWUP_DAYS),
  };
}

function successMessage(detail: AppointmentDetail): string {
  const until = detail.consultation?.followup_valid_until ?? null;
  const base = "Consultation saved. The appointment is marked completed.";
  return until ? `${base} Follow-up valid until ${formatDate(until)}.` : base;
}

export function ConsultationForm({ detail, disabled, onSaved }: Props) {
  const [form, setForm] = useState(() => initialForm(detail));
  const submit = useSubmit();
  const existing = detail.consultation;

  const edit = (patch: Partial<typeof form>) => {
    setForm((current) => ({ ...current, ...patch }));
    submit.clear();
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const days = Number(form.followupDays);
    if (form.followupRequired && (!Number.isInteger(days) || days < 1 || days > 90)) {
      return submit.fail("Follow-up days must be a whole number from 1 to 90.");
    }
    const body: ConsultationRequest = {
      diagnosis: form.diagnosis.trim(),
      notes: form.notes.trim(),
      medication: form.medication.trim(),
      followup_required: form.followupRequired,
      followup_in_days: form.followupRequired ? days : null,
    };
    void submit.run(async () => {
      const updated = await saveConsultation(detail.id, body);
      onSaved(updated);
      return successMessage(updated);
    });
  };

  return (
    <section className="card" aria-labelledby="consultation-heading">
      <h2 id="consultation-heading">Consultation</h2>
      {existing && (
        <p className="muted small">
          Last submitted by {existing.submitted_by}, {formatDateTime(existing.updated_at)}.
          {existing.followup_valid_until &&
            ` Follow-up valid until ${formatDate(existing.followup_valid_until)}.`}
        </p>
      )}
      <form className="form" onSubmit={onSubmit}>
        <fieldset disabled={disabled || submit.busy}>
          <div className="field">
            <label htmlFor="consult-diagnosis">Diagnosis</label>
            <input
              id="consult-diagnosis"
              type="text"
              value={form.diagnosis}
              onChange={(e) => edit({ diagnosis: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="consult-notes">Consultation notes</label>
            <textarea
              id="consult-notes"
              rows={5}
              value={form.notes}
              onChange={(e) => edit({ notes: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="consult-medication">Medication</label>
            <textarea
              id="consult-medication"
              rows={4}
              placeholder="One per line: name, dose, frequency, duration"
              value={form.medication}
              onChange={(e) => edit({ medication: e.target.value })}
            />
          </div>
          <div className="field-check">
            <input
              id="consult-followup"
              type="checkbox"
              checked={form.followupRequired}
              onChange={(e) => edit({ followupRequired: e.target.checked })}
            />
            <label htmlFor="consult-followup">Follow-up required</label>
          </div>
          {form.followupRequired && (
            <div className="field field-narrow">
              <label htmlFor="consult-days">Follow-up within (days)</label>
              <input
                id="consult-days"
                type="number"
                min={1}
                max={90}
                step={1}
                required
                value={form.followupDays}
                onChange={(e) => edit({ followupDays: e.target.value })}
              />
              <p className="hint">The patient can book the follow-up fee through the chatbot.</p>
            </div>
          )}
          <div className="form-actions">
            <button type="submit" className="btn btn-primary">
              {submit.busy ? "Saving…" : existing ? "Update consultation" : "Submit consultation"}
            </button>
          </div>
        </fieldset>
        <FormMessages submit={submit} />
      </form>
    </section>
  );
}
