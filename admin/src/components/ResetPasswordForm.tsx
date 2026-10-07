import { useState, type FormEvent } from "react";

import { updateAccount } from "../api/client";
import type { StaffUser } from "../api/types";
import { MIN_PASSWORD_LENGTH } from "../lib/password";
import { useSubmit } from "../lib/useSubmit";
import { FormMessages } from "./FormMessages";
import { GeneratedPasswordField } from "./GeneratedPasswordField";

interface Props {
  user: StaffUser;
  onDone: (user: StaffUser) => void;
  onCancel: () => void;
}

export function ResetPasswordForm({ user, onDone, onCancel }: Props) {
  const [password, setPassword] = useState("");
  const submit = useSubmit();

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      return submit.fail(`The password needs at least ${MIN_PASSWORD_LENGTH} characters.`);
    }
    void submit.run(async () => {
      const updated = await updateAccount(user.id, { password });
      onDone(updated);
      return `Password reset. ${user.name} is signed out everywhere; the new password is ${password}`;
    });
  };

  return (
    <form className="form inline-form" onSubmit={onSubmit}>
      <fieldset disabled={submit.busy || submit.success !== null}>
        <GeneratedPasswordField
          id={`reset-password-${user.id}`}
          label={`New password for ${user.name}`}
          value={password}
          onChange={setPassword}
        />
        <div className="form-actions">
          <button type="submit" className="btn btn-primary">
            {submit.busy ? "Saving…" : "Reset password"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </fieldset>
      <FormMessages submit={submit} />
      {submit.success && (
        <button type="button" className="btn btn-ghost btn-small" onClick={onCancel}>
          Close
        </button>
      )}
    </form>
  );
}
