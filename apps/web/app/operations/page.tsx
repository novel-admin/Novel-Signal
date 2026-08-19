"use client";

import { useEffect, useState } from "react";
import { loadCaptures, loadJobs, loadOperations } from "../work/api";
import { WorkError, WorkLoading } from "../../components/WorkStates";
import type { OperationsModule } from "../work/api";

export default function OperationsPage() {
  const [module, setModule] = useState<OperationsModule | null>(null);
  const [jobs, setJobs] = useState<Awaited<ReturnType<typeof loadJobs>>>([]);
  const [captures, setCaptures] = useState<Awaited<ReturnType<typeof loadCaptures>>>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { Promise.all([loadOperations(), loadJobs(), loadCaptures()]).then(([meta, jobItems, captureItems]) => { setModule(meta); setJobs(jobItems); setCaptures(captureItems); }).catch((cause: Error) => setError(cause.message)); }, []);
  return <><div className="eyebrow">Collection health</div><h1>Operations</h1><p className="lede">Check collection status before trusting the latest data.</p>{error ? <WorkError message={error} /> : module === null ? <WorkLoading /> : <><section className="grid"><article className="card"><span>Collection module</span><strong>{module.status}</strong></article><article className="card"><span>Scheduled jobs</span><strong>{jobs.length}</strong></article><article className="card"><span>Captured pages</span><strong>{captures.length}</strong></article></section><section className="card detail-card"><h2>Recent jobs</h2>{jobs.length === 0 ? <p className="muted">No jobs have been scheduled.</p> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Type</th><th>Target</th><th>Status</th><th>Attempts</th><th>Scheduled</th><th>Failure</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td>{job.page_type}</td><td>{job.target_id}</td><td>{job.status}</td><td>{job.attempts}</td><td>{new Date(job.scheduled_at).toLocaleString()}</td><td>{job.failure_reason ?? "-"}</td></tr>)}</tbody></table></div>}</section></> }</>;
}
