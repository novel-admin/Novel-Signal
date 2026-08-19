export type ListResponse<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type CollectionJob = {
  id: string;
  idempotency_key: string;
  job_type: string;
  platform: string;
  keyword_id: string | null;
  product_id: string | null;
  competitor_product_id: string | null;
  tracking_target_id: string | null;
  status: string;
  scheduled_for: string;
  not_before: string | null;
  attempt_count: number;
  max_attempts: number;
  started_at: string | null;
  completed_at: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type RawEvidence = {
  id: string;
  job_id: string;
  evidence_type: string;
  sha256: string;
  storage_bucket: string;
  object_key: string;
  content_type: string;
  byte_length: number;
  challenge_detected: boolean;
  captured_at: string;
};

export type QuarantineRecord = {
  id: string;
  job_id: string;
  status: string;
  reason_code: string;
  reason: string;
  created_at: string;
};

export type DataQualityCheck = {
  id: string;
  check_type: string;
  status: string;
  scope_type: string;
  scope_key: string;
  observed_value: unknown;
  expected_value: unknown;
  created_at: string;
};

export type Health = {
  window_hours: number;
  scheduled: number;
  succeeded: number;
  failed: number;
  quarantined: number;
  running: number;
  pending: number;
  terminal: number;
  success_ratio: number | null;
  challenge_count: number;
  challenge_ratio: number | null;
  parser_canary_failures: number;
  latest_success_at: string | null;
  freshness_minutes: number | null;
  freshness_status: string;
  completeness_status: string;
  overall_status: string;
};

export type ReadinessItem = {
  status: string;
  detail: string | null;
};

export type Readiness = {
  status: string;
  postgres: ReadinessItem;
  redis: ReadinessItem;
  object_store: ReadinessItem;
  celery: ReadinessItem;
};

export type Retention = {
  retention_days: number;
  cutoff: string;
  candidates: Array<{
    id: string;
    job_id: string;
    captured_at: string;
    storage_bucket: string;
    object_key: string;
    byte_length: number;
  }>;
  candidate_count: number;
};
