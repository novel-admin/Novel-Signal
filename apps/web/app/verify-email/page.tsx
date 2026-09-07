"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

export const dynamic = "force-dynamic";

export default function VerifyEmailPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function resend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    try {
      const supabase = createClient();
      const { error: resendError } = await supabase.auth.resend({
        type: "signup",
        email: email.trim(),
      });
      if (resendError) {
        setError("We could not send the verification email. Check the address and try again.");
        return;
      }
      setStatus("If the address belongs to an account, a verification email is on its way.");
    } catch {
      setError("We could not reach the email service. Try again.");
    }
  }

  return (
    <main className="content auth-panel">
      <div className="eyebrow">Novel Signal</div>
      <h1>Verify your email</h1>
      <p className="lede">
        Open the verification link from your inbox, then return here and log in. You must verify
        your email before you can enroll MFA and access application data.
      </p>
      <form onSubmit={resend} className="auth-form">
        <label htmlFor="verify-email">Email</label>
        <input id="verify-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
        {error ? <div className="state state-error" role="alert">{error}</div> : null}
        {status ? <div className="state" role="status">{status}</div> : null}
        <button className="button primary" type="submit">Resend verification email</button>
      </form>
      <p className="lede"><Link href="/login">Back to login</Link></p>
    </main>
  );
}
