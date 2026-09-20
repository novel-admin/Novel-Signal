"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ApiError, request, setAccessTokenProvider } from "@novel-signal/api-client";
import { createClient } from "@/lib/supabase/client";

setAccessTokenProvider(async () => {
  const { data: { session } } = await createClient().auth.getSession();
  return session?.access_token ?? null;
});

const PUBLIC_PREFIXES = ["/login", "/verify-email", "/first-login", "/forgot-password", "/reset-password", "/auth"];

type GateState =
  | { status: "loading" }
  | { status: "public" }
  | { status: "ready" }
  | { status: "not-configured" }
  | { status: "error"; message: string };

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

async function signOut() {
  try {
    await createClient().auth.signOut();
  } catch {
    // Cookies are cleared best-effort; navigation still lands on /login.
  }
  window.location.href = "/login";
}

/** Internal-tool gate. A valid Supabase session plus a backend-mapped
 *  workspace membership renders the app. No MFA, no AAL checks. */
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
          data: { session },
        } = await supabase.auth.getSession();
        if (cancelled) return;
        if (!session) {
          router.replace("/login");
          return;
        }
        try {
          const me = await request<{ workspaces: unknown[] }>("/auth/me", {
            token: session.access_token,
          });
          if (cancelled) return;
          if (!Array.isArray(me.workspaces) || me.workspaces.length === 0) {
            // Logged in, but no application mapping or workspace membership.
            setState({ status: "not-configured" });
            return;
          }
        } catch (requestError) {
          if (cancelled) return;
          if (requestError instanceof ApiError && requestError.status === 401) {
            // Expired or invalid session: drop it and start over at /login.
            await signOut();
            return;
          }
          if (requestError instanceof ApiError && requestError.status === 403) {
            // Valid login, but no application mapping or workspace membership.
            setState({ status: "not-configured" });
            return;
          }
          setState({ status: "error", message: "The backend is unavailable. Try again." });
          return;
        }
        if (!cancelled) setState({ status: "ready" });
      } catch {
        if (!cancelled) setState({ status: "error", message: "The backend is unavailable. Try again." });
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
        <div className="state" role="status">Checking session...</div>
      </main>
    );
  }
  if (state.status === "not-configured") {
    return (
      <main className="content auth-panel">
        <div className="eyebrow">Novel Signal</div>
        <h1>Account not configured</h1>
        <p className="lede">
          You are logged in, but this account has no workspace access yet.
          Contact your administrator to assign workspace membership and a role.
        </p>
        <button className="button primary" type="button" onClick={() => void signOut()}>Log out</button>
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
