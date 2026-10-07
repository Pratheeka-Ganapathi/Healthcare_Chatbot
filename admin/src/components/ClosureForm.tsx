import { useState, type FormEvent } from "react";

import { createClosure } from "../api/client";
import type { Closure } from "../api/types";
import { todayInClinic } from "../lib/format";
import { useSubmit } from "../lib/useSubmit";
import { FormMessages } from "./FormMessages";

export function ClosureForm({ onCreated }: { onCreated: (closure: Closure) => void }) {
  const [today] = useState(todayInClinic);
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const submit = useSubmit();

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!date) return submit.fail("Choose the day the clinic is closed.");
    if (date < today) return submit.fail("Choose today or a later day.");
    if (!reason.trim()) return submit.fail("Enter a reason, for example a public holiday.");
    void submit.run(async () => {
      const closure = await createClosure({ date, reason: reason.trim() });
      setDate("");
      setReason("");
      onCreated(closure);
      const booked = closure.booked_appointments;
      return booked > 0
        ? `Closure added for ${closure.date_label}. ${booked} booked appointment(s) on that day are not cancelled; contact those patients.`
        : `Closure added for ${closure.date_label}. The chatbot no longer offers slots that day.`;
    });
  };

  return (
    <form className="form" onSubmit={onSubmit}>
      <fieldset disabled={submit.busy}>
        <div className="field-row">
          <div className="field field-narrow">
            <label htmlFor="closure-date">Date</label>
            <input
              id="closure-date"
              type="date"
              min={today}
              required
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="closure-reason">Reason</label>
            <input
              id="closure-reason"
              type="text"
              required
              placeholder="e.g. Ayudha Puja"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
        </div>
        <div className="form-actions">
          <button type="submit" className="btn btn-primary">
            {submit.busy ? "Adding…" : "Add closure"}
          </button>
        </div>
      </fieldset>
      <FormMessages submit={submit} />
    </form>
  );
}
