import { useEffect, useState } from "react";

import { ApiError, getMe, logout, setAuthToken, setUnauthorizedHandler } from "./api/client";
import type { LoginResponse, StaffUser } from "./api/types";
import { AppShell } from "./components/AppShell";
import { LoadingState } from "./components/LoadingState";
import { RouteView } from "./RouteView";
import { redirectFor } from "./routing/routes";
import { replaceRoute, useHashRoute } from "./routing/useHashRoute";
import { LoginScreen } from "./screens/LoginScreen";
import { clearSession, loadSession, saveSession } from "./session/storage";

type Auth =
  | { status: "checking" }
  | { status: "signed_out"; notice: string | null }
  | { status: "signed_in"; user: StaffUser };

const SESSION_ENDED = "Your session has ended. Please sign in again.";

function initialAuth(): Auth {
  return loadSession() ? { status: "checking" } : { status: "signed_out", notice: null };
}

function endLocalSession(): void {
  clearSession();
  setAuthToken(null);
}

export function App() {
  const [auth, setAuth] = useState<Auth>(initialAuth);
  const route = useHashRoute();

  useEffect(() => {
    setUnauthorizedHandler(() => {
      endLocalSession();
      setAuth({ status: "signed_out", notice: SESSION_ENDED });
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  useEffect(() => {
    const stored = loadSession();
    if (!stored) return;
    setAuthToken(stored.token);
    let active = true;
    getMe().then(
      (user) => {
        if (!active) return;
        saveSession({ token: stored.token, user });
        setAuth({ status: "signed_in", user });
      },
      (error: unknown) => {
        // A 401 already signed out through the handler. Otherwise (server unreachable) keep the
        // stored user; the screens show their own errors and a later 401 still signs out.
        if (!active || (error instanceof ApiError && error.status === 401)) return;
        setAuth({ status: "signed_in", user: stored.user });
      },
    );
    return () => {
      active = false;
    };
  }, []);

  const role = auth.status === "signed_in" ? auth.user.role : null;
  const redirect = auth.status === "checking" ? null : redirectFor(route, role);

  useEffect(() => {
    if (redirect) replaceRoute(redirect);
  }, [redirect]);

  const signedIn = (result: LoginResponse) => {
    saveSession({ token: result.token, user: result.user });
    setAuthToken(result.token);
    setAuth({ status: "signed_in", user: result.user });
  };

  const signOut = () => {
    // The request reads the token before this function clears it.
    logout().catch(() => undefined);
    endLocalSession();
    setAuth({ status: "signed_out", notice: null });
  };

  if (auth.status === "checking") {
    return (
      <div className="page-center">
        <LoadingState label="Restoring your session…" />
      </div>
    );
  }
  if (redirect) return null;
  if (auth.status === "signed_out")
    return <LoginScreen notice={auth.notice} onSignedIn={signedIn} />;
  return (
    <AppShell user={auth.user} route={route} onSignOut={signOut}>
      <RouteView route={route} user={auth.user} />
    </AppShell>
  );
}
