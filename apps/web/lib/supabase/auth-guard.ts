import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";
export const revalidate = 0;

/** Returns "/login" when there is no valid Supabase session, else null.
 *  Internal tool: no email-verification or MFA routing. */
export async function routeForSession(): Promise<string | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return "/login";
  return null;
}

export async function requireSession(): Promise<void> {
  const next = await routeForSession();
  if (next) redirect(next);
}
