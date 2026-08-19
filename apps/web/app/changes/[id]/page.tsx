"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createAction, loadChange } from "../../work/api";
import type { ChangeEvent } from "../../work/types";
import { WorkError, WorkLoading } from "../../../components/WorkStates";

export default function ChangeDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [change, setChange] = useState<ChangeEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => { loadChange(params.id).then(setChange).catch((cause: Error) => setError(cause.message)); }, [params.id]);
  async function makeAction() {
    if (!change) return;
    setSubmitting(true);
    try { await createAction(change, { title: `Review ${change.event_type} on ${change.target_id}`, reason: `Detected ${change.event_type} from evidence.` }); router.push("/actions"); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not create action"); }
    finally { setSubmitting(false); }
  }
  if (error) return <WorkError message={error} />;
  if (!change) return <WorkLoading />;
  return <><div className="eyebrow">Change evidence</div><h1>{change.event_type}</h1><p className="lede">{change.target_type} / {change.target_id} · detected {new Date(change.detected_at).toLocaleString()}</p><section className="detail-grid"><article className="card"><span>Before</span><strong>{JSON.stringify(change.old_value) ?? "-"}</strong></article><article className="card"><span>After</span><strong>{JSON.stringify(change.new_value) ?? "-"}</strong></article></section><section className="card detail-card"><h2>Evidence</h2><p>Old observation: {change.old_observation_id ?? "Not linked"}</p><p>New observation: {change.new_observation_id ?? "Not linked"}</p><p>Field: {change.field_name ?? "Not specified"}</p><button className="button primary" disabled={submitting} onClick={makeAction}>{submitting ? "Creating..." : "Create action"}</button></section></>;
}

