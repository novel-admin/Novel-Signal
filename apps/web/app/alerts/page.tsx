"use client";

import { useEffect, useState } from "react";
import { WorkEmpty, WorkError, WorkLoading } from "../../components/WorkStates";
import { loadRows, transitionAlert, type IntelligenceRow } from "../intelligence/api";

export default function AlertsPage() {
  const [rows, setRows] = useState<IntelligenceRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => loadRows("/alerts").then(setRows).catch((cause: Error) => setError(cause.message));
  useEffect(() => { void refresh(); }, []);
  const transition = async (id: string, status: "acknowledged" | "resolved") => { await transitionAlert(id, status); await refresh(); };
  return <><div className="eyebrow">S11 · War room</div><h1>Alerts</h1><p className="lede">Review evidence-backed threats by severity and acknowledge or resolve them.</p>
    {error ? <WorkError message={error} /> : rows === null ? <WorkLoading /> : rows.length === 0 ? <WorkEmpty message="No active alerts." /> :
    <div className="table-wrap"><table><thead><tr><th>Severity</th><th>Alert</th><th>Status</th><th>Opened</th><th>Evidence</th><th>Action</th></tr></thead><tbody>
    {rows.map(row => <tr key={String(row.id)}><td>{String(row.severity)}</td><td>{String(row.title)}</td><td>{String(row.status)}</td><td>{String(row.opened_at)}</td><td>{JSON.stringify(row.evidence)}</td><td>{row.status === "open" ? <button onClick={() => void transition(String(row.id), "acknowledged")}>Acknowledge</button> : row.status === "acknowledged" ? <button onClick={() => void transition(String(row.id), "resolved")}>Resolve</button> : "Closed"}</td></tr>)}</tbody></table></div>}</>;
}
