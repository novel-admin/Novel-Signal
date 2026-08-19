"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { loadAction, transitionAction } from "../../work/api";
import type { ActionDetail } from "../../work/types";
import { WorkError, WorkLoading } from "../../../components/WorkStates";

export default function ActionDetailPage() {
  const params = useParams<{ id: string }>();
  const [action, setAction] = useState<ActionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { loadAction(params.id).then(setAction).catch((cause: Error) => setError(cause.message)); }, [params.id]);
  async function update(status: ActionDetail["status"]) {
    try { setAction(await transitionAction(params.id, status, status === "done" ? "Completed after review." : undefined).then(() => loadAction(params.id))); } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not update action"); }
  }
  if (error) return <WorkError message={error} />;
  if (!action) return <WorkLoading />;
  return <><div className="eyebrow">Owned action</div><h1>{action.title}</h1><p className="lede">{action.reason ?? "No reason recorded."}</p><section className="card detail-card"><p>Owner: {action.owner_user_id ?? "Unassigned"}</p><p>Due: {action.due_at ? new Date(action.due_at).toLocaleString() : "No due date"}</p><p>Status: <span className={`status ${action.status}`}>{action.status.replace("_", " ")}</span></p><div className="toolbar-actions"><button className="button" disabled={action.status !== "open"} onClick={() => update("in_progress")}>Start</button><button className="button primary" disabled={action.status !== "in_progress"} onClick={() => update("done")}>Complete</button><button className="button button-danger" disabled={action.status === "done"} onClick={() => update("dismissed")}>Dismiss</button></div></section><section className="card detail-card"><h2>Status history</h2>{action.history.length === 0 ? <p className="muted">No status history.</p> : <ul>{action.history.map((entry) => <li key={entry.id}>{entry.from_status ?? "new"} → {entry.to_status} ({new Date(entry.changed_at).toLocaleString()})</li>)}</ul>}</section></>;
}

