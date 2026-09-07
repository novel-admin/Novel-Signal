"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

export const dynamic = "force-dynamic";

/** First login: the owner creates the user, the user sets a password via the secure email link. */
export default function FirstLoginPage() {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    if (password.length < 12) {
      setError("Use at least 12 characters for your first password.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    try {
      const supabase = createClient();
      const { error: updateError } = await supabase.auth.updateUser({ password });
      if (updateError) {
        setError("This secure link is invalid or expired. Ask the owner for a new invite or password reset.");
        return;
      }
      setStatus("Password set. Continue to email verification and MFA enrollment.");
    } catch {
      setError("We could not reach the login service. Try again.");
    }
  }

  return (
    <main className="content auth-panel">
      <div className="eyebrow">Novel Signal</div>
      <h1>First login</h1>
      <p className="lede">
        The platform owner creates every account in the Supabase Dashboard. Open the invite or
        password-reset email, follow its secure link here, then set your password below. After
        that: verify your email, enroll a TOTP authenticator, and reach AAL2 before accessing data.
      </p>
      <form onSubmit={submit} className="auth-form">
        <label htmlFor="first-password">New password</label>
        <input id="first-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required />
        <label htmlFor="first-confirm">Confirm password</label>
        <input id="first-confirm" type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} autoComplete="new-password" required />
        {error ? <div className="state state-error" role="alert">{error}</div> : null}
        {status ? <div className="state" role="status">{status}</div> : null}
        <button className="button primary" type="submit">Set password</button>
      </form>
      <p className="lede"><Link href="/login">Back to login</Link> · <Link href="/verify-email">Verify email</Link></p>
    </main>
  );
}
