import type { StaffUser } from "../api/types";
import { ROLE_LABELS } from "../lib/format";

interface Props {
  user: StaffUser;
  onSignOut: () => void;
}

export function TopBar({ user, onSignOut }: Props) {
  const role =
    user.role === "doctor" && user.doctor_name
      ? `${ROLE_LABELS.doctor} · ${user.doctor_name}`
      : ROLE_LABELS[user.role];
  return (
    <header className="topbar">
      <div className="topbar-user">
        <strong>{user.name}</strong>
        <span className="muted">{role}</span>
      </div>
      <div className="topbar-actions">
        <a className="btn btn-ghost" href="#/account">
          Change password
        </a>
        <button type="button" className="btn btn-secondary" onClick={onSignOut}>
          Sign out
        </button>
      </div>
    </header>
  );
}
