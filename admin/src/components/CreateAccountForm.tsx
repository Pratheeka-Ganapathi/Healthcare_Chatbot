import { useState, type FormEvent } from "react";

import { createAccount } from "../api/client";
import type { Doctor } from "../api/types";
import { MIN_PASSWORD_LENGTH } from "../lib/password";
import { useSubmit } from "../lib/useSubmit";
import { FormMessages } from "./FormMessages";
import { GeneratedPasswordField } from "./GeneratedPasswordField";

interface Props {
  /** Doctors who do not have a login yet. */
  doctors: Doctor[];
  onCreated: () => void;
}

export function CreateAccountForm({ doctors, onCreated }: Props) {
  const [doctorId, setDoctorId] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const submit = useSubmit();

  const pickDoctor = (value: string) => {
    setDoctorId(value);
    const doctor = doctors.find((d) => String(d.id) === value);
    if (doctor) setName(doctor.name);
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!doctorId) return submit.fail("Choose the doctor this login is for.");
    if (password.length < MIN_PASSWORD_LENGTH) {
      return submit.fail(`The password needs at least ${MIN_PASSWORD_LENGTH} characters.`);
    }
    void submit.run(async () => {
      const user = await createAccount({
        doctor_id: Number(doctorId),
        name: name.trim(),
        email: email.trim(),
        password,
      });
      setDoctorId("");
      setName("");
      setEmail("");
      setPassword("");
      onCreated();
      return `Login created for ${user.name} (${user.email}). Hand over the password: ${password}`;
    });
  };

  if (doctors.length === 0 && !submit.success) {
    return <p className="muted">Every doctor already has a login.</p>;
  }

  return (
    <form className="form" onSubmit={onSubmit}>
      <fieldset disabled={submit.busy || doctors.length === 0}>
        <div className="field-row">
          <div className="field">
            <label htmlFor="account-doctor">Doctor</label>
            <select
              id="account-doctor"
              required
              value={doctorId}
              onChange={(e) => pickDoctor(e.target.value)}
            >
              <option value="">Choose a doctor</option>
              {doctors.map((doctor) => (
                <option key={doctor.id} value={doctor.id}>
                  {doctor.name} ({doctor.specialty_label})
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="account-name">Name</label>
            <input
              id="account-name"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
        </div>
        <div className="field-row">
          <div className="field">
            <label htmlFor="account-email">Email</label>
            <input
              id="account-email"
              type="email"
              required
              autoComplete="off"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <GeneratedPasswordField
            id="account-password"
            label="Initial password"
            value={password}
            onChange={setPassword}
          />
        </div>
        <div className="form-actions">
          <button type="submit" className="btn btn-primary">
            {submit.busy ? "Creating…" : "Create doctor login"}
          </button>
        </div>
      </fieldset>
      <FormMessages submit={submit} />
    </form>
  );
}
