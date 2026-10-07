import { useState, type FormEvent } from "react";

import { updateDoctor } from "../api/client";
import type { Doctor } from "../api/types";
import { useSubmit } from "../lib/useSubmit";
import { FormMessages } from "./FormMessages";

interface Props {
  doctor: Doctor;
  onSaved: (doctor: Doctor) => void;
  onClose: () => void;
}

function parseRupees(value: string): number | null {
  if (!/^\d{1,7}$/.test(value.trim())) return null;
  return Number(value.trim());
}

export function DoctorEditForm({ doctor, onSaved, onClose }: Props) {
  const [name, setName] = useState(doctor.name);
  const [bio, setBio] = useState(doctor.bio);
  const [fee, setFee] = useState(String(doctor.fee_rupees));
  const [followupFee, setFollowupFee] = useState(String(doctor.followup_fee_rupees));
  const submit = useSubmit();

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const feeRupees = parseRupees(fee);
    const followupRupees = parseRupees(followupFee);
    if (!name.trim()) return submit.fail("Enter the doctor's name.");
    if (feeRupees === null || followupRupees === null) {
      return submit.fail("Fees must be whole rupees, for example 800.");
    }
    void submit.run(async () => {
      const saved = await updateDoctor(doctor.id, {
        name: name.trim(),
        bio: bio.trim(),
        fee_rupees: feeRupees,
        followup_fee_rupees: followupRupees,
      });
      onSaved(saved);
      return `Saved. The chatbot shows the new details for ${saved.name} straight away.`;
    });
  };

  return (
    <section className="card panel" aria-labelledby="doctor-edit-heading">
      <h2 id="doctor-edit-heading">Edit {doctor.name}</h2>
      <p className="muted small">
        {doctor.specialty_label} · {doctor.days_label}, {doctor.hours}. Consulting days and hours
        are fixed in this version.
      </p>
      <form className="form" onSubmit={onSubmit}>
        <fieldset disabled={submit.busy}>
          <div className="field">
            <label htmlFor="doctor-name">Name</label>
            <input
              id="doctor-name"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="doctor-bio">Bio</label>
            <textarea
              id="doctor-bio"
              rows={4}
              value={bio}
              onChange={(e) => setBio(e.target.value)}
            />
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="doctor-fee">Fee (₹)</label>
              <input
                id="doctor-fee"
                type="number"
                min={0}
                step={1}
                required
                value={fee}
                onChange={(e) => setFee(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="doctor-followup-fee">Follow-up fee (₹)</label>
              <input
                id="doctor-followup-fee"
                type="number"
                min={0}
                step={1}
                required
                value={followupFee}
                onChange={(e) => setFollowupFee(e.target.value)}
              />
            </div>
          </div>
          <div className="form-actions">
            <button type="submit" className="btn btn-primary">
              {submit.busy ? "Saving…" : "Save doctor"}
            </button>
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              Close
            </button>
          </div>
        </fieldset>
        <FormMessages submit={submit} />
      </form>
    </section>
  );
}
