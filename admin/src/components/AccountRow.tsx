import { useState } from "react";

import { updateAccount } from "../api/client";
import type { StaffUser } from "../api/types";
import { formatDateTime, ROLE_LABELS } from "../lib/format";
import { useSubmit } from "../lib/useSubmit";
import { ResetPasswordForm } from "./ResetPasswordForm";

const COLUMNS = 7;

interface Props {
  user: StaffUser;
  isCurrentUser: boolean;
  onUpdated: (user: StaffUser) => void;
}

export function AccountRow({ user, isCurrentUser, onUpdated }: Props) {
  const [resetting, setResetting] = useState(false);
  const toggle = useSubmit();

  const toggleActive = () => {
    const next = !user.active;
    const question = next
      ? `Activate the login for ${user.name}?`
      : `Deactivate the login for ${user.name}? They are signed out at once.`;
    if (!window.confirm(question)) return;
    void toggle.run(async () => {
      onUpdated(await updateAccount(user.id, { active: next }));
    });
  };

  return (
    <>
      <tr className={user.active ? undefined : "row-muted"}>
        <td>
          {user.name}
          {isCurrentUser && <span className="muted small"> (you)</span>}
        </td>
        <td>{user.email}</td>
        <td>{ROLE_LABELS[user.role]}</td>
        <td>{user.doctor_name ?? <span className="muted">—</span>}</td>
        <td>
          {user.active ? (
            <span className="badge badge-completed">Active</span>
          ) : (
            <span className="badge badge-cancelled">Inactive</span>
          )}
        </td>
        <td className="nowrap">
          {user.last_login_at ? formatDateTime(user.last_login_at) : "Never"}
        </td>
        <td>
          <div className="row-actions">
            <button
              type="button"
              className="btn btn-secondary btn-small"
              onClick={() => setResetting(true)}
              disabled={resetting}
            >
              Reset password
            </button>
            {!isCurrentUser && (
              <button
                type="button"
                className={`btn btn-small ${user.active ? "btn-danger" : "btn-secondary"}`}
                onClick={toggleActive}
                disabled={toggle.busy}
              >
                {toggle.busy ? "Saving…" : user.active ? "Deactivate" : "Activate"}
              </button>
            )}
          </div>
          {toggle.error && (
            <p className="field-error" role="alert">
              {toggle.error}
            </p>
          )}
        </td>
      </tr>
      {resetting && (
        <tr className="row-form">
          <td colSpan={COLUMNS}>
            <ResetPasswordForm
              user={user}
              onDone={onUpdated}
              onCancel={() => setResetting(false)}
            />
          </td>
        </tr>
      )}
    </>
  );
}
