import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";
export const revalidate = 0;

/** Decides where an authenticated user must go: verify-email -> mfa/setup -> mfa/challenge -> app. */
export async function routeForSession(): Promise<string | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return "/login";
  if (!user.email_confirmed_at && !user.confirmed_at) return "/verify-email";
  const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
  const { data: factors } = await supabase.auth.mfa.listFactors();
  const verified = (factors?.totp ?? []).filter((factor) => factor.status === "verified");
  if (verified.length === 0) return "/mfa/setup";
  if (aal?.currentLevel !== "aal2") return "/mfa/challenge";
  return null;
}

export async function requireAal2(): Promise<void> {
  const next = await routeForSession();
  if (next) redirect(next);
}
