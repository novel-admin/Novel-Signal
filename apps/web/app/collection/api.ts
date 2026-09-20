import type {
  CollectionJob,
  DataQualityCheck,
  Health,
  ListResponse,
  QuarantineRecord,
  RawEvidence,
  Readiness,
  Retention,
} from "./types";

import { request as authenticatedRequest } from "@novel-signal/api-client";

export async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  return authenticatedRequest<T>(path, {
    ...init,
    body: init?.body,
    headers: init?.headers,
  });
}

export async function loadCollection() {
  const [
    health,
    readiness,
    jobs,
    evidence,
    quarantine,
    quality,
    failures,
    retention,
  ] = await Promise.all([
    request<Health>("/collection/health"),
    request<Readiness>("/collection/readiness"),
    request<ListResponse<CollectionJob>>("/collection/jobs"),
    request<ListResponse<RawEvidence>>("/collection/raw-evidence"),
    request<ListResponse<QuarantineRecord>>("/collection/quarantine"),
    request<ListResponse<DataQualityCheck>>("/collection/data-quality"),
    request<ListResponse<CollectionJob>>("/collection/failures"),
    request<Retention>("/collection/retention"),
  ]);

  return {
    health,
    readiness,
    jobs: jobs.items,
    evidence: evidence.items,
    quarantine: quarantine.items,
    quality: quality.items,
    failures: failures.items,
    retention,
  };
}

export function planCollection() {
  return request<{
    created: number;
    existing: number;
    job_ids: string[];
  }>("/collection/plan", {
    method: "POST",
  });
}

export function resyncCollection() {
  return request<{
    created: number;
    existing: number;
    job_ids: string[];
  }>("/collection/resync", {
    method: "POST",
    body: JSON.stringify({}),
  });
}
