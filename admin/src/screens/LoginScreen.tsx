import { useState, type FormEvent } from "react";

import { login } from "../api/client";
import type { LoginResponse } from "../api/types";
import { Notice } from "../components/Notice";
import { useSubmit } from "../lib/useSubmit";

interface Props {
  notice: string | null;
  onSignedIn: (result: LoginResponse) => void;
}

export function LoginScreen({ notice, onSignedIn }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const submit = useSubmit();

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submit.run(async () => {
      onSignedIn(await login({ email: email.trim(), password }));
    });
  };

  return (
    <div className="login-page">
      <main className="login-card">
        <div className="login-brand">
          <span className="brand-mark" aria-hidden="true" />
          <h1>
            City Care Clinic <span className="login-sub">— Staff portal</span>
          </h1>
        </div>
        <p className="muted">Sign in with the email and password the clinic admin gave you.</p>
        {notice && !submit.error && <Notice tone="info">{notice}</Notice>}
        <form className="form" onSubmit={onSubmit}>
          <fieldset disabled={submit.busy}>
            <div className="field">
              <label htmlFor="login-email">Email</label>
              <input
                id="login-email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="login-password">Password</label>
              <input
                id="login-password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {submit.error && <Notice tone="error">{submit.error}</Notice>}
            <button type="submit" className="btn btn-primary btn-block">
              {submit.busy ? "Signing in…" : "Sign in"}
            </button>
          </fieldset>
        </form>
      </main>
      <footer className="demo-footer">Demo with synthetic data.</footer>
    </div>
  );
}
