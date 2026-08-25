"use client";

import { useEffect, useState } from "react";
import { WorkLoading } from "../components/WorkStates";
import { loadRows } from "./intelligence/api";

type Summary = { scorecards: number; gaps: number; actions: number; alerts: number; partial: boolean };

export default function OverviewPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  useEffect(() => {
    Promise.allSettled([loadRows("/scorecards"), loadRows("/gaps"), loadRows("/actions"), loadRows("/alerts")])
      .then(results => setSummary({
        scorecards: results[0].status === "fulfilled" ? results[0].value.length : 0,
        gaps: results[1].status === "fulfilled" ? results[1].value.length : 0,
        actions: results[2].status === "fulfilled" ? results[2].value.length : 0,
        alerts: results[3].status === "fulfilled" ? results[3].value.length : 0,
        partial: results.some(result => result.status === "rejected"),
      }));
  }, []);
  return (
    <>
      <div className="eyebrow">Evidence-first overview</div>
      <h1>Competitive watchtower</h1>
      <p className="lede">See where Novel leads or lags, inspect evidence, and act on important changes.</p>
      {!summary ? <WorkLoading /> : <><div role="status">{summary.partial ? "Some intelligence services are unavailable. Available results are shown below." : "All intelligence summaries loaded."}</div>
        <section className="grid"><Card label="Scorecard cells" value={summary.scorecards}/><Card label="Open gaps" value={summary.gaps}/><Card label="Actions" value={summary.actions}/><Card label="Alerts" value={summary.alerts}/></section></>}
    </>
  );
}

function Card({ label, value }: { label: string; value: number }) {
  return <article className="card"><span>{label}</span><strong>{value}</strong></article>;
}
