import type { AmazonShareOfVoice, BadgeEvent, BrandPresence, Capture, CaptureDetail, GoogleDomainComparison, KeywordCoverageSummary, KeywordGapAnalysis, KeywordOption, ListResponse, NewEntrant, RankHistory, ReverseAsinIntelligence, Visibility } from "./types";

// Keep browser traffic same-origin. Next.js proxies /api locally and deployments can route the
// same path without exposing a backend host in the client bundle.
const base = "/api/v1";

function errorMessage(body: unknown, status: number) {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
    if (Array.isArray(detail)) return detail.map((item) => typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item)).join(" · ");
  }
  return `Request failed (${status})`;
}

export async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${base}${path}`, { cache: "no-store" });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorMessage(body, response.status));
  return body as T;
}

export const loadDashboard = async () => {
  const [captures, keywords, badges, entrants] = await Promise.all([
    request<ListResponse<Capture>>("/rank-visibility/captures?limit=100"),
    request<ListResponse<KeywordOption>>("/keywords?limit=200"),
    request<ListResponse<BadgeEvent>>("/rank-visibility/badge-events?limit=100"),
    request<ListResponse<NewEntrant>>("/rank-visibility/new-entrants?limit=100"),
  ]);
  return { captures, keywords: keywords.items, badges, entrants };
};
export const loadCapture = (id: string) => request<CaptureDetail>(`/rank-visibility/captures/${id}`);
export const loadHistory = (query: string) => request<RankHistory>(`/rank-visibility/rank-history?${query}`);
export const loadVisibility = (query: string) => request<Visibility>(`/rank-visibility/visibility?${query}`);
export const loadBrandPresence = (query: string) => request<BrandPresence>(`/rank-visibility/brand-presence?${query}`);
export const loadReverseAsin = (query: string) => request<ReverseAsinIntelligence>(`/rank-visibility/reverse-asin?${query}`);
export const loadShareOfVoice = (query: string) => request<AmazonShareOfVoice>(`/rank-visibility/amazon-share-of-voice?${query}`);
export const loadKeywordGaps = (query: string) => request<KeywordGapAnalysis>(`/rank-visibility/keyword-gaps?${query}`);
export const loadKeywordCoverage = (query: string) => request<KeywordCoverageSummary>(`/rank-visibility/keyword-coverage?${query}`);
export const loadGoogleDomainComparison = (query: string) => request<GoogleDomainComparison>(`/rank-visibility/google-domain-comparison?${query}`);
