"use client";

import { FormEvent, useEffect, useState } from "react";
import { request } from "@novel-signal/api-client";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [code, setCode] = useState("");
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
      await request("/auth/login", { method: "POST", body: { code } });
      setAuthenticated(true);
    } catch {
      setError("Invalid access code.");
    }
  }

  if (!ready) return <main className="content"><div className="state" role="status">Loading...</div></main>;
  if (authenticated) return <>{children}</>;
  return <main className="content auth-panel">
    <div className="eyebrow">Novel Signal</div>
    <h1>Dashboard access</h1>
    <p className="lede">Enter the demo access code to continue.</p>
    <form onSubmit={submit} className="auth-form">
      <label htmlFor="dashboard-code">Access code</label>
      <input id="dashboard-code" type="password" value={code} onChange={(event) => setCode(event.target.value)} autoComplete="current-password" required />
      {error ? <div className="state state-error" role="alert">{error}</div> : null}
      <button className="button primary" type="submit">Enter dashboard</button>
    </form>
  </main>;
}
