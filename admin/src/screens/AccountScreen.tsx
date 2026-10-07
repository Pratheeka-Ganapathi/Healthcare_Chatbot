import { useState, type FormEvent } from "react";

import { changePassword } from "../api/client";
import { FormMessages } from "../components/FormMessages";
import { PageHeader } from "../components/PageHeader";
import { MIN_PASSWORD_LENGTH } from "../lib/password";
import { useSubmit } from "../lib/useSubmit";

export function AccountScreen() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const submit = useSubmit();

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (next.length < MIN_PASSWORD_LENGTH) {
      return submit.fail(`The new password needs at least ${MIN_PASSWORD_LENGTH} characters.`);
    }
    if (next !== confirm) return submit.fail("The new passwords do not match.");
    if (next === current) return submit.fail("Choose a password different from the current one.");
    void submit.run(async () => {
      await changePassword({ current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setConfirm("");
      return "Password changed. Any other sessions you had open have been signed out.";
    });
  };

  return (
    <>
      <PageHeader title="Change password" />
      <section className="card narrow">
        <form className="form" onSubmit={onSubmit}>
          <fieldset disabled={submit.busy}>
            <div className="field">
              <label htmlFor="current-password">Current password</label>
              <input
                id="current-password"
                type="password"
                autoComplete="current-password"
                required
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="new-password">New password</label>
              <input
                id="new-password"
                type="password"
                autoComplete="new-password"
                minLength={MIN_PASSWORD_LENGTH}
                required
                value={next}
                onChange={(e) => setNext(e.target.value)}
                aria-describedby="new-password-hint"
              />
              <p className="hint" id="new-password-hint">
                At least {MIN_PASSWORD_LENGTH} characters.
              </p>
            </div>
            <div className="field">
              <label htmlFor="confirm-password">Confirm new password</label>
              <input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </div>
            <div className="form-actions">
              <button type="submit" className="btn btn-primary">
                {submit.busy ? "Saving…" : "Change password"}
              </button>
            </div>
          </fieldset>
          <FormMessages submit={submit} />
        </form>
      </section>
    </>
  );
}
