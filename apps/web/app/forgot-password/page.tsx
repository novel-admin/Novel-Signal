"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

export const dynamic = "force-dynamic";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    try {
      const supabase = createClient();
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo: `${window.location.origin}/auth/callback`,
      });
      // Generic response either way.
      if (resetError) {
        setError("We could not start the reset. Try again.");
        return;
      }
      setStatus("If the address belongs to an account, a password-reset email is on its way.");
    } catch {
      setError("We could not reach the login service. Try again.");
    }
  }

  return (
    <main className="content auth-panel">
      <div className="eyebrow">Novel Signal</div>
      <h1>Forgot password</h1>
      <p className="lede">Enter your work email to receive a secure reset link. The link expires.</p>
      <form onSubmit={submit} className="auth-form">
        <label htmlFor="forgot-email">Email</label>
        <input id="forgot-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
        {error ? <div className="state state-error" role="alert">{error}</div> : null}
        {status ? <div className="state" role="status">{status}</div> : null}
        <button className="button primary" type="submit">Send reset link</button>
      </form>
      <p className="lede"><Link href="/login">Back to login</Link></p>
    </main>
  );
}
