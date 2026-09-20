import type { AmazonShareOfVoice, BadgeEvent, BrandPresence, Capture, CaptureDetail, GoogleDomainComparison, KeywordCoverageSummary, KeywordGapAnalysis, KeywordOption, ListResponse, NewEntrant, RankHistory, ReverseAsinIntelligence, Visibility } from "./types";
import { request as authenticatedRequest } from "@novel-signal/api-client";

export function request<T>(path: string): Promise<T> {
  return authenticatedRequest<T>(path, { cache: "no-store" });
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
