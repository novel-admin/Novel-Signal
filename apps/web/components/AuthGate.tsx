"use client";

import { FormEvent, useEffect, useState } from "react";
import { request } from "@novel-signal/api-client";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [email, setEmail] = useState("demo@demo.com");
  const [password, setPassword] = useState("demo123");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    request<{ authenticated: boolean }>("/auth/session")
      .then((result) => { setAuthenticated(result.authenticated); setReady(true); })
      .catch(() => { setError("The backend is unavailable."); setReady(true); });
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      await request("/auth/login", { method: "POST", body: { email, password } });
      setAuthenticated(true);
    } catch {
      setError("Invalid email or password.");
    }
  }

  if (!ready) return <main className="content"><div className="state" role="status">Loading...</div></main>;
  if (authenticated) return <>{children}</>;
  return <main className="content auth-panel">
    <div className="eyebrow">Novel Signal</div>
    <h1>Dashboard access</h1>
    <p className="lede">Sign in with the account configured by your workspace administrator.</p>
    <form onSubmit={submit} className="auth-form">
      <label htmlFor="dashboard-email">Email</label>
      <input id="dashboard-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
      <label htmlFor="dashboard-password">Password</label>
      <input id="dashboard-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
      {error ? <div className="state state-error" role="alert">{error}</div> : null}
      <button className="button primary" type="submit">Enter dashboard</button>
    </form>
  </main>;
}
