"use client";

import { useCallback, useEffect, useState } from "react";
import { WorkEmpty, WorkError, WorkLoading } from "../../components/WorkStates";
import { apiBaseUrl } from "@novel-signal/api-client";

type Source = { source_type: string; owner: string; purpose: string; configured: boolean };
type Readiness = { status: string; postgres: Item; redis: Item; object_store: Item; celery: Item };
type Item = { status: string; detail: string | null };

const api = apiBaseUrl;

function sourceLabel(value: string) {
  return value.replaceAll("_", " ");
}

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setError("");
    try {
      const [sourceResponse, readinessResponse] = await Promise.all([
        fetch(`${api}/sources`, { cache: "no-store", credentials: "include" }),
        fetch(`${api}/collection/readiness`, { cache: "no-store", credentials: "include" }),
      ]);
      if (!sourceResponse.ok || !readinessResponse.ok) throw new Error("Unable to load source readiness");
      setSources(await sourceResponse.json() as Source[]);
      setReadiness(await readinessResponse.json() as Readiness);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load source readiness");
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return <>
    <div className="eyebrow">Source readiness</div><h1>Sources</h1>
    <p className="lede">Configuration readiness is read from the server. “Configured” does not claim that a live credential verification has run.</p>
    <div className="universe-panel">
      <div className="universe-toolbar"><strong>Configured sources</strong><button className="button" onClick={() => void load()}>Refresh</button></div>
      {error ? <WorkError message={error} /> : sources === null || readiness === null ? <WorkLoading /> : !sources.length ? <WorkEmpty message="No source definitions are registered." /> : <>
        <div className="rank-summary"><Card label="Configured" value={sources.filter((source) => source.configured).length} /><Card label="Pending configuration" value={sources.filter((source) => !source.configured).length} /><Card label="Runtime readiness" value={readiness.status} /></div>
        <div className="table-wrap"><table className="data-table"><thead><tr><th>Source</th><th>Owner</th><th>Purpose</th><th>Configuration</th><th>Evidence type</th></tr></thead><tbody>{sources.map((source) => <tr key={source.source_type}><td>{sourceLabel(source.source_type)}</td><td>{source.owner}</td><td>{source.purpose}</td><td><span className={`status ${source.configured ? "approved" : "draft"}`}>{source.configured ? "Configured" : "Not configured"}</span></td><td>{source.source_type === "amazon_public_pages" ? "Measured public-page evidence" : "Configured API source"}</td></tr>)}</tbody></table></div>
        <h2 className="section-heading">Collection dependencies</h2><div className="rank-summary">{(["postgres", "redis", "object_store", "celery"] as const).map((key) => <Card key={key} label={key.replaceAll("_", " ")} value={`${readiness[key].status}${readiness[key].detail ? ` · ${readiness[key].detail}` : ""}`} />)}</div>
      </>}
    </div>
  </>;
}

function Card({ label, value }: { label: string; value: string | number }) { return <div className="card"><span>{label}</span><strong>{value}</strong></div>; }
