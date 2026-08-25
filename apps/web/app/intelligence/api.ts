import { request } from "@novel-signal/api-client";

export type IntelligenceRow = Record<string, unknown>;
type Page = { items: IntelligenceRow[] };

export async function loadRows(endpoint: string): Promise<IntelligenceRow[]> {
  const response = await request<IntelligenceRow[] | Page>(endpoint);
  return Array.isArray(response) ? response : response.items;
}

export function transitionAlert(id: string, status: "acknowledged" | "resolved") {
  return request<IntelligenceRow>(`/alerts/${id}/transition`, {
    method: "POST",
    body: { status },
  });
}
