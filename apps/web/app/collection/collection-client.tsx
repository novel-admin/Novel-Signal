"use client";

import { useCallback, useEffect, useState } from "react";
import { loadCollection, planCollection } from "./api";
import type {
  CollectionJob,
  DataQualityCheck,
  Health,
  QuarantineRecord,
  RawEvidence,
  Readiness,
  Retention,
} from "./types";

type Tab =
  | "jobs"
  | "evidence"
  | "quarantine"
  | "quality"
  | "failures"
  | "retention";

type Data = {
  health: Health | null;
  readiness: Readiness | null;
  jobs: CollectionJob[];
  evidence: RawEvidence[];
  quarantine: QuarantineRecord[];
  quality: DataQualityCheck[];
  failures: CollectionJob[];
  retention: Retention | null;
};

const emptyData: Data = {
  health: null,
  readiness: null,
  jobs: [],
  evidence: [],
  quarantine: [],
  quality: [],
  failures: [],
  retention: null,
};

export default function CollectionClient() {
  const [data, setData] = useState<Data>(emptyData);
  const [tab, setTab] = useState<Tab>("jobs");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      setData(await loadCollection());
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Unable to load collection data",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function plan() {
    setBusy(true);
    setError("");
    setNotice("");

    try {
      const result = await planCollection();

      setNotice(
        result.created > 0
          ? `${result.created} collection job(s) planned successfully · ${result.existing} already scheduled`
          : `No new jobs required · ${result.existing} job(s) already scheduled for this window`,
      );

      const refreshed = await loadCollection();
      setData(refreshed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to plan jobs");
    } finally {
      setBusy(false);
    }
  }

  const health = data.health;
  const readiness = data.readiness;

  return (
    <div className="collection-panel">
      <div className="collection-actions">
        <div>
          <strong>Runtime operations</strong>
          <span>Live state from the S12 backend.</span>
        </div>

        <div className="toolbar-actions">
          <button className="button" onClick={() => void reload()}>
            Refresh
          </button>

          <button
            className="button primary"
            disabled={busy}
            onClick={() => void plan()}
          >
            {busy ? "Planning…" : "Plan jobs"}
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {notice && <div className="success-banner">{notice}</div>}

      {loading ? (
        <div className="loading-state">
          <span className="spinner" />
          Loading collection infrastructure…
        </div>
      ) : (
        <>
          <div className="collection-metrics">
            <Metric
              label="Runtime"
              value={readiness?.status ?? "unknown"}
              state={readiness?.status}
            />

            <Metric
              label="24h jobs"
              value={String(health?.scheduled ?? 0)}
            />

            <Metric
              label="Success ratio"
              value={
                health?.success_ratio == null
                  ? "No data"
                  : `${Math.round(health.success_ratio * 100)}%`
              }
            />

            <Metric
              label="Parser canaries"
              value={String(health?.parser_canary_failures ?? 0)}
              state={
                health?.parser_canary_failures === 0
                  ? "ready"
                  : "warn"
              }
            />
          </div>

          {readiness && (
            <div className="readiness-grid">
              <Readiness label="PostgreSQL" value={readiness.postgres.status} />
              <Readiness label="Redis" value={readiness.redis.status} />
              <Readiness
                label="Object store"
                value={readiness.object_store.status}
              />
              <Readiness label="Celery" value={readiness.celery.status} />
            </div>
          )}

          {health && (
            <div className="health-strip">
              <span>
                Freshness: <strong>{health.freshness_status}</strong>
              </span>
              <span>
                Completeness: <strong>{health.completeness_status}</strong>
              </span>
              <span>
                Challenges: <strong>{health.challenge_count}</strong>
              </span>
              <span>
                Quarantined: <strong>{health.quarantined}</strong>
              </span>
            </div>
          )}

          <div className="tabs collection-tabs">
            <TabButton current={tab} value="jobs" label="Jobs" />
            <TabButton current={tab} value="evidence" label="Raw evidence" />
            <TabButton current={tab} value="quarantine" label="Quarantine" />
            <TabButton current={tab} value="quality" label="Data quality" />
            <TabButton current={tab} value="failures" label="Failures" />
            <TabButton current={tab} value="retention" label="Retention" />
          </div>

          <div className="table-wrap">
            {tab === "jobs" && <Jobs rows={data.jobs} />}
            {tab === "evidence" && <Evidence rows={data.evidence} />}
            {tab === "quarantine" && (
              <Quarantine rows={data.quarantine} />
            )}
            {tab === "quality" && <Quality rows={data.quality} />}
            {tab === "failures" && <Jobs rows={data.failures} />}
            {tab === "retention" && (
              <RetentionView value={data.retention} />
            )}
          </div>
        </>
      )}
    </div>
  );

  function TabButton({
    current,
    value,
    label,
  }: {
    current: Tab;
    value: Tab;
    label: string;
  }) {
    return (
      <button
        className={`tab ${current === value ? "active" : ""}`}
        onClick={() => setTab(value)}
      >
        {label}
      </button>
    );
  }
}

function Metric({
  label,
  value,
  state,
}: {
  label: string;
  value: string;
  state?: string;
}) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong className={state ? `state ${state}` : ""}>{value}</strong>
    </div>
  );
}

function Readiness({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="readiness-item">
      <span>{label}</span>
      <strong className={`state ${value}`}>{value}</strong>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>;
}

function Jobs({ rows }: { rows: CollectionJob[] }) {
  if (!rows.length) return <Empty text="No collection jobs found." />;

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Type</th>
          <th>Platform</th>
          <th>Status</th>
          <th>Attempts</th>
          <th>Scheduled</th>
          <th>Error</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{row.job_type.replaceAll("_", " ")}</td>
            <td>{row.platform}</td>
            <td>
              <span className={`state ${row.status}`}>{row.status}</span>
            </td>
            <td>
              {row.attempt_count}/{row.max_attempts}
            </td>
            <td>{new Date(row.scheduled_for).toLocaleString()}</td>
            <td>{row.last_error_message ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Evidence({ rows }: { rows: RawEvidence[] }) {
  if (!rows.length) return <Empty text="No raw evidence captured yet." />;

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Type</th>
          <th>SHA-256</th>
          <th>Bytes</th>
          <th>Challenge</th>
          <th>Captured</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{row.evidence_type}</td>
            <td className="mono">{row.sha256.slice(0, 14)}…</td>
            <td>{row.byte_length.toLocaleString()}</td>
            <td>{row.challenge_detected ? "Yes" : "No"}</td>
            <td>{new Date(row.captured_at).toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Quarantine({
  rows,
}: {
  rows: QuarantineRecord[];
}) {
  if (!rows.length) return <Empty text="No quarantined records." />;

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Status</th>
          <th>Reason code</th>
          <th>Reason</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{row.status}</td>
            <td>{row.reason_code}</td>
            <td>{row.reason}</td>
            <td>{new Date(row.created_at).toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Quality({ rows }: { rows: DataQualityCheck[] }) {
  if (!rows.length) return <Empty text="No data-quality checks recorded." />;

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Check</th>
          <th>Status</th>
          <th>Scope</th>
          <th>Observed</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{row.check_type.replaceAll("_", " ")}</td>
            <td>
              <span className={`state ${row.status}`}>{row.status}</span>
            </td>
            <td>
              {row.scope_type} · {row.scope_key}
            </td>
            <td className="mono">
              {JSON.stringify(row.observed_value)}
            </td>
            <td>{new Date(row.created_at).toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RetentionView({
  value,
}: {
  value: Retention | null;
}) {
  if (!value) return <Empty text="Retention information unavailable." />;

  return (
    <div className="retention-view">
      <div className="metric-card">
        <span>Retention window</span>
        <strong>{value.retention_days} days</strong>
      </div>

      <div className="metric-card">
        <span>Deletion candidates</span>
        <strong>{value.candidate_count}</strong>
      </div>

      <div className="metric-card">
        <span>Cutoff</span>
        <strong>{new Date(value.cutoff).toLocaleDateString()}</strong>
      </div>
    </div>
  );
}
