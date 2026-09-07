"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export const dynamic = "force-dynamic";

/** TOTP challenge on every future login until AAL2 is reached. */
export default function MfaChallengePage() {
  const router = useRouter();
  const [factorId, setFactorId] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const supabase = createClient();
        const { data } = await supabase.auth.mfa.listFactors();
        const verified = (data?.totp ?? []).filter((factor) => factor.status === "verified");
        if (verified.length === 0) {
          router.replace("/mfa/setup");
          return;
        }
        setFactorId(verified[0].id);
      } catch {
        setError("We could not reach the login service. Try again.");
      }
    })();
  }, [router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!factorId) return;
    setBusy(true);
    try {
      const supabase = createClient();
      // Supabase rate-limits MFA attempts; generic error avoids oracle behavior.
      const challenge = await supabase.auth.mfa.challenge({ factorId });
      if (challenge.error) {
        setError("Invalid code. Try again.");
        return;
      }
      const { error: verifyError } = await supabase.auth.mfa.verify({
        factorId,
        challengeId: challenge.data.id,
        code: code.trim(),
      });
      if (verifyError) {
        setError("Invalid code. Try again.");
        return;
      }
      router.replace("/");
    } catch {
      setError("We could not reach the login service. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="content auth-panel">
      <div className="eyebrow">Novel Signal</div>
      <h1>Two-factor check</h1>
      <p className="lede">Enter the 6-digit code from your authenticator app to reach AAL2.</p>
      <form onSubmit={submit} className="auth-form">
        <label htmlFor="challenge-code">6-digit code</label>
        <input id="challenge-code" inputMode="numeric" value={code} onChange={(event) => setCode(event.target.value)} autoComplete="one-time-code" required />
        {error ? <div className="state state-error" role="alert">{error}</div> : null}
        <button className="button primary" type="submit" disabled={busy || !factorId}>{busy ? "Checking..." : "Verify"}</button>
      </form>
    </main>
  );
}
