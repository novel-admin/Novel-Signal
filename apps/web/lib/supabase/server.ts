import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/** Create a new Supabase server client per request (cookie-based SSR, PKCE). */
export async function createClient() {
  const cookieStore = await cookies();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error("Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL/ANON_KEY).");
  }
  return createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      setAll(cookiesToSet: any) {
        try {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          cookiesToSet.forEach(({ name, value, options }: any) =>
            cookieStore.set(name, value, options),
          );
        } catch {
          // Called from a Server Component where set is not allowed;
          // middleware refreshes cookies instead.
        }
      },
    },
  });
}
