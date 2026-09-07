import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(__dirname, "..");

function read(path: string): string {
  return readFileSync(join(root, path), "utf-8");
}

describe("Supabase-only frontend auth", () => {
  it("has no public signup route or page", () => {
    expect(existsSync(join(root, "app/signup/page.tsx"))).toBe(false);
    expect(existsSync(join(root, "app/signup"))).toBe(false);
    expect(existsSync(join(root, "app/register/page.tsx"))).toBe(false);
  });

  it("implements all required auth routes", () => {
    for (const route of [
      "app/login/page.tsx",
      "app/verify-email/page.tsx",
      "app/first-login/page.tsx",
      "app/mfa/setup/page.tsx",
      "app/mfa/challenge/page.tsx",
      "app/settings/security/page.tsx",
      "app/auth/callback/route.ts",
    ]) {
      expect(existsSync(join(root, route)), route).toBe(true);
    }
  });

  it("login never offers signup and uses generic errors", () => {
    const login = read("app/login/page.tsx");
    expect(login.toLowerCase()).not.toContain("sign up");
    expect(login).toContain("Invalid email or password.");
    expect(login).toContain("signInWithPassword");
    expect(login).not.toContain("signUp");
  });

  it("enforces email verification, mandatory TOTP, and AAL2 before app data", () => {
    const gate = read("components/AuthGate.tsx");
    expect(gate).toContain("email_confirmed_at");
    expect(gate).toContain("/verify-email");
    expect(gate).toContain("/mfa/setup");
    expect(gate).toContain("/mfa/challenge");
    expect(gate).toContain("aal2");
    expect(gate.toLowerCase()).not.toContain("sign up");
  });

  it("uses cookie-based SSR with per-request clients and PKCE callback", () => {
    expect(read("lib/supabase/server.ts")).toContain("createServerClient");
    expect(read("lib/supabase/client.ts")).toContain("createBrowserClient");
    expect(read("lib/supabase/middleware.ts")).toContain("getUser");
    expect(read("app/auth/callback/route.ts")).toContain("exchangeCodeForSession");
  });

  it("never caches authenticated pages across users", () => {
    expect(read("lib/supabase/middleware.ts")).toContain("no-store");
    expect(read("components/AuthGate.tsx")).toContain("Redirecting");
  });

  it("uses TOTP MFA enrollment and challenge flows", () => {
    expect(read("app/mfa/setup/page.tsx")).toContain("mfa.enroll");
    expect(read("app/mfa/challenge/page.tsx")).toContain("mfa.challenge");
    expect(read("app/settings/security/page.tsx")).toContain("mfa.unenroll");
  });

  it("documents owner-controlled recovery without self-service signup", () => {
    const security = read("app/settings/security/page.tsx");
    expect(security.toLowerCase()).toContain("owner");
    expect(security.toLowerCase()).toContain("recovery");
  });

  it("never references a service-role key in frontend code", () => {
    for (const file of [
      "lib/supabase/client.ts",
      "lib/supabase/server.ts",
      "lib/supabase/middleware.ts",
      "app/login/page.tsx",
    ]) {
      expect(read(file).toLowerCase()).not.toContain("service_role");
    }
  });
});
