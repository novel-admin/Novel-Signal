import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(__dirname, "..");

function read(path: string): string {
  return readFileSync(join(root, path), "utf-8");
}

describe("Supabase-only frontend auth (internal tool)", () => {
  it("has no public signup route or page", () => {
    expect(existsSync(join(root, "app/signup/page.tsx"))).toBe(false);
    expect(existsSync(join(root, "app/signup"))).toBe(false);
    expect(existsSync(join(root, "app/register/page.tsx"))).toBe(false);
  });

  it("has no MFA routes", () => {
    expect(existsSync(join(root, "app/mfa"))).toBe(false);
    expect(existsSync(join(root, "app/mfa/setup/page.tsx"))).toBe(false);
    expect(existsSync(join(root, "app/mfa/challenge/page.tsx"))).toBe(false);
  });

  it("implements all required auth routes", () => {
    for (const route of [
      "app/login/page.tsx",
      "app/verify-email/page.tsx",
      "app/first-login/page.tsx",
      "app/forgot-password/page.tsx",
      "app/reset-password/page.tsx",
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

  it("login performs no MFA, AAL, or verification branching", () => {
    const login = read("app/login/page.tsx");
    expect(login).not.toContain("listFactors");
    expect(login).not.toContain("getAuthenticatorAssuranceLevel");
    expect(login).not.toContain("email_confirmed_at");
    expect(login).not.toContain("/mfa/");
    expect(login).not.toContain("aal2");
  });

  it("gate checks session plus backend mapping, without MFA or AAL", () => {
    const gate = read("components/AuthGate.tsx");
    expect(gate).toContain("getSession");
    expect(gate).toContain("/auth/me");
    expect(gate).toContain("not-configured");
    expect(gate).not.toContain("listFactors");
    expect(gate).not.toContain("getAuthenticatorAssuranceLevel");
    expect(gate).not.toContain("/mfa/");
    expect(gate).not.toContain("aal2");
    expect(gate.toLowerCase()).not.toContain("sign up");
  });

  it("shows no MFA as required anywhere in the UI", () => {
    for (const file of [
      "app/login/page.tsx",
      "app/settings/security/page.tsx",
      "app/first-login/page.tsx",
      "app/verify-email/page.tsx",
      "app/reset-password/page.tsx",
      "components/AuthGate.tsx",
      "lib/supabase/auth-guard.ts",
    ]) {
      const content = read(file);
      expect(content, file).not.toContain("mfa.");
      expect(content, file).not.toContain("MFA is mandatory");
      expect(content, file).not.toContain("authenticator");
    }
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
