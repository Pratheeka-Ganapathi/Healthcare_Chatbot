// The signed-in session lives in sessionStorage. Storage can be blocked or throw, so every
// access is wrapped and the app works (without restore) when it is unavailable.
import type { StaffUser } from "../api/types";

const KEY = "clinic-staff-session";

export interface StoredSession {
  token: string;
  user: StaffUser;
}

export function loadSession(): StoredSession | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    if (typeof parsed.token !== "string" || typeof parsed.user !== "object" || !parsed.user) {
      return null;
    }
    return { token: parsed.token, user: parsed.user };
  } catch {
    return null;
  }
}

export function saveSession(session: StoredSession): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(session));
  } catch {
    // Storage unavailable: the session lasts until the tab reloads.
  }
}

export function clearSession(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
}
