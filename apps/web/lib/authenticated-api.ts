"use client";

import { createClient } from "@/lib/supabase/client";
import { request } from "@novel-signal/api-client";
import { useCallback } from "react";

/** Backend calls always carry the Supabase access token; never trust UI state. */
export function useAuthenticatedRequest() {
  return useCallback(async <T,>(path: string, init?: RequestInit & { body?: unknown }): Promise<T> => {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    const token = session?.access_token;
    if (!token) throw new Error("Session has expired");
    return request<T>(path, { ...(init as object), token } as Parameters<typeof request>[1]);
  }, []);
}

export async function getAccessToken(): Promise<string | null> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}
