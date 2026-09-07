"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export const dynamic = "force-dynamic";

/** Mandatory TOTP enrollment: user enrolls, scans QR, verifies code, reaches AAL2. */
export default function MfaSetupPage() {
  const router = useRouter();
  const [qr, setQr] = useState<string | null>(null);
  const [factorId, setFactorId] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const supabase = createClient();
        const { data, error: enrollError } = await supabase.auth.mfa.enroll({
          factorType: "totp",
        });
        if (enrollError || !data) {
          setError("We could not start MFA enrollment. Try again.");
          return;
        }
        setFactorId(data.id);
        setQr(data.totp.qr_code);
        setSecret(data.totp.secret);
      } catch {
        setError("We could not reach the login service. Try again.");
      }
    })();
  }, []);

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!factorId) {
      setError("Enrollment is not ready yet.");
      return;
    }
    setBusy(true);
    try {
      const supabase = createClient();
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
      <h1>Set up two-factor authentication</h1>
      <p className="lede">
        MFA is mandatory. Scan the QR code with your authenticator app, then enter the 6-digit
        code. You will reach AAL2 only after verification.
      </p>
      {qr ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={qr} alt="TOTP enrollment QR code" width={200} height={200} />
      ) : (
        <div className="state" role="status">Preparing enrollment...</div>
      )}
      {secret ? <p className="lede">Manual key (keep private): <span className="mono">{secret}</span></p> : null}
      <form onSubmit={verify} className="auth-form">
        <label htmlFor="mfa-code">6-digit code</label>
        <input id="mfa-code" inputMode="numeric" value={code} onChange={(event) => setCode(event.target.value)} autoComplete="one-time-code" required />
        {error ? <div className="state state-error" role="alert">{error}</div> : null}
        <button className="button primary" type="submit" disabled={busy || !factorId}>{busy ? "Verifying..." : "Verify and finish"}</button>
      </form>
    </main>
  );
}
