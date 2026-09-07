"use client";

import { FormEvent, useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

export const dynamic = "force-dynamic";

export default function SecuritySettingsPage() {
  const [email, setEmail] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const supabase = createClient();
        const {
          data: { user },
        } = await supabase.auth.getUser();
        setEmail(user?.email ?? null);
      } catch {
        setError("Could not load security settings.");
      }
    })();
  }, []);

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    if (password.length < 12) {
      setError("Use at least 12 characters.");
      return;
    }
    const supabase = createClient();
    const { error: updateError } = await supabase.auth.updateUser({ password });
    if (updateError) {
      setError("Password change failed. Log in again and try once more.");
      return;
    }
    setPassword("");
    setStatus("Password changed. Other sessions may need to log in again.");
  }

  async function signOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    window.location.href = "/login";
  }

  return (
    <main className="content">
      <div className="eyebrow">Settings</div>
      <h1>Security</h1>
      <p className="lede">Signed in as {email ?? "…"}. Contact your administrator for account or workspace changes.</p>
      {error ? <div className="state state-error" role="alert">{error}</div> : null}
      {status ? <div className="state" role="status">{status}</div> : null}
      <section className="card">
        <h2>Change password</h2>
        <form onSubmit={changePassword} className="auth-form">
          <label htmlFor="security-password">New password</label>
          <input id="security-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required />
          <button className="button primary" type="submit">Change password</button>
        </form>
      </section>
      <button className="button" type="button" onClick={signOut}>Log out everywhere on this device</button>
    </main>
  );
}
