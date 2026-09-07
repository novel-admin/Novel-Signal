"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export const dynamic = "force-dynamic";

/** Login only. No signup exists: users are created by the platform owner in Supabase Dashboard. */
export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const supabase = createClient();
      const { data, error: signInError } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      // Generic error: do not reveal whether the email exists.
      if (signInError || !data.user || !data.session) {
        setError("Invalid email or password.");
        return;
      }
      const user = data.user;
      if (!user.email_confirmed_at && !user.confirmed_at) {
        router.replace("/verify-email");
        return;
      }
      const { data: factors } = await supabase.auth.mfa.listFactors();
      const verified = (factors?.totp ?? []).filter((factor) => factor.status === "verified");
      if (verified.length === 0) {
        router.replace("/mfa/setup");
        return;
      }
      const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
      router.replace(aal?.currentLevel === "aal2" ? "/" : "/mfa/challenge");
    } catch {
      setError("We could not reach the login service. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="content auth-panel">
      <div className="eyebrow">Novel Signal</div>
      <h1>Log in</h1>
      <p className="lede">
        Accounts are created by the platform owner. If you do not have an account, contact your
        administrator. There is no public signup.
      </p>
      <form onSubmit={submit} className="auth-form">
        <label htmlFor="login-email">Email</label>
        <input id="login-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
        <label htmlFor="login-password">Password</label>
        <input id="login-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
        {error ? <div className="state state-error" role="alert">{error}</div> : null}
        <button className="button primary" type="submit" disabled={busy}>{busy ? "Signing in..." : "Log in"}</button>
      </form>
      <p className="lede">
        <Link href="/first-login">First login or new device?</Link> ·{" "}
        <Link href="/verify-email">Verify email</Link> ·{" "}
        <Link href="/forgot-password">Forgot password?</Link>
      </p>
    </main>
  );
}
