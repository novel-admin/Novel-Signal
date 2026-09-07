"use client";

import { FormEvent, useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

type Factor = { id: string; status: string; factor_type: string };

export const dynamic = "force-dynamic";

export default function SecuritySettingsPage() {
  const [email, setEmail] = useState<string | null>(null);
  const [aal, setAal] = useState<string | null>(null);
  const [factors, setFactors] = useState<Factor[]>([]);
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const supabase = createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    setEmail(user?.email ?? null);
    const { data: level } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    setAal(level?.currentLevel ?? null);
    const { data } = await supabase.auth.mfa.listFactors();
    setFactors(((data?.totp ?? []) as Factor[]).map((factor) => ({
      id: factor.id,
      status: factor.status,
      factor_type: factor.factor_type,
    })));
  }

  useEffect(() => {
    refresh().catch(() => setError("Could not load security settings."));
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

  async function removeFactor(id: string) {
    setError(null);
    setStatus(null);
    if (!window.confirm("Remove this authenticator? You must enroll a new one before accessing data.")) return;
    const supabase = createClient();
    const { error: unenrollError } = await supabase.auth.mfa.unenroll({ factorId: id });
    if (unenrollError) {
      setError("Could not remove the authenticator.");
      return;
    }
    setStatus("Authenticator removed. Enroll a new one to keep access.");
    await refresh();
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
      <p className="lede">Signed in as {email ?? "…"}. Assurance level: {aal ?? "…"}. MFA is mandatory.</p>
      {error ? <div className="state state-error" role="alert">{error}</div> : null}
      {status ? <div className="state" role="status">{status}</div> : null}
      <section className="card">
        <h2>Authenticators</h2>
        {factors.length === 0 ? <p className="lede">No authenticator enrolled.</p> : null}
        {factors.map((factor) => (
          <div key={factor.id}>
            <span>{factor.factor_type} · {factor.status}</span>{" "}
            <button className="button" type="button" onClick={() => removeFactor(factor.id)}>Remove</button>
          </div>
        ))}
        <p className="lede">
          Lost your authenticator? Contact the platform owner for owner-controlled recovery. Do not
          share codes or secrets. The owner will verify your identity and guide re-enrollment.
        </p>
      </section>
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
