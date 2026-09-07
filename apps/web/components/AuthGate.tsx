"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { createClient } from "@/lib/supabase/client";

const PUBLIC_PREFIXES = ["/login", "/verify-email", "/first-login", "/forgot-password", "/reset-password", "/mfa", "/auth"];

type GateState =
  | { status: "loading" }
  | { status: "public" }
  | { status: "ready" }
  | { status: "error"; message: string };

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

function genericMessage(): string {
  return "We could not reach the login service. Try again.";
}

/** Supabase-only gate. No signup. Enforces verified email + mandatory TOTP + AAL2. */
export function AuthGate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [state, setState] = useState<GateState>({ status: "loading" });

  useEffect(() => {
    if (isPublic(pathname)) {
      setState({ status: "public" });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const supabase = createClient();
        const {
          data: { user },
        } = await supabase.auth.getUser();
        if (cancelled) return;
        if (!user) {
          router.replace("/login");
          return;
        }
        if (!user.email_confirmed_at && !user.confirmed_at) {
          router.replace("/verify-email");
          return;
        }
        const { data: factors } = await supabase.auth.mfa.listFactors();
        if (cancelled) return;
        const verified = (factors?.totp ?? []).filter((factor) => factor.status === "verified");
        if (verified.length === 0) {
          router.replace("/mfa/setup");
          return;
        }
        const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
        if (cancelled) return;
        if (aal?.currentLevel !== "aal2") {
          router.replace("/mfa/challenge");
          return;
        }
        // Never downgrade AAL2: verified factors + aal2 required to render data.
        setState({ status: "ready" });
      } catch {
        if (!cancelled) setState({ status: "error", message: genericMessage() });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  if (isPublic(pathname)) return <>{children}</>;
  if (state.status === "loading") {
    return (
      <main className="content">
        <div className="state" role="status">Checking session and MFA...</div>
      </main>
    );
  }
  if (state.status === "error") {
    return (
      <main className="content">
        <div className="state state-error" role="alert">{state.message}</div>
      </main>
    );
  }
  if (state.status === "ready") return <>{children}</>;
  // Redirecting: render nothing so protected data never flashes.
  return (
    <main className="content">
      <div className="state" role="status">Redirecting to login...</div>
    </main>
  );
}
