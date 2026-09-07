"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

export const dynamic = "force-dynamic";

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    if (password.length < 12) {
      setError("Use at least 12 characters.");
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
        setError("This reset link is invalid or expired. Request a new one.");
        return;
      }
      setStatus("Password updated. Log in again and complete MFA if asked.");
    } catch {
      setError("We could not reach the login service. Try again.");
    }
  }

  return (
    <main className="content auth-panel">
      <div className="eyebrow">Novel Signal</div>
      <h1>Reset password</h1>
      <p className="lede">You arrived here from a secure reset link. Choose a new password.</p>
      <form onSubmit={submit} className="auth-form">
        <label htmlFor="reset-password">New password</label>
        <input id="reset-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required />
        <label htmlFor="reset-confirm">Confirm password</label>
        <input id="reset-confirm" type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} autoComplete="new-password" required />
        {error ? <div className="state state-error" role="alert">{error}</div> : null}
        {status ? <div className="state" role="status">{status}</div> : null}
        <button className="button primary" type="submit">Update password</button>
      </form>
      <p className="lede"><Link href="/login">Back to login</Link></p>
    </main>
  );
}
