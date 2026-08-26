"use client";

import { useEffect, useState } from "react";
import { WorkLoading } from "../components/WorkStates";
import { loadRows } from "./intelligence/api";
import { OverviewChart } from "../components/OverviewChart";
import { Badge } from "../components/ui/badge";
import { Card, CardHeader, CardTitle } from "../components/ui/card";

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
      <div className="page-heading">
        <div><div className="eyebrow">Evidence-first overview</div><h1>Competitive watchtower</h1><p className="lede">See where Novel leads or lags, inspect the source evidence, and act on important changes.</p></div>
        <Badge variant={summary?.partial ? "warning" : "success"}>{summary?.partial ? "Partial data" : "Data connected"}</Badge>
      </div>
      {!summary ? <WorkLoading /> : <>
        <div className="screen-reader-status" role="status">{summary.partial ? "Some intelligence services are unavailable. Available results are shown below." : "All intelligence summaries loaded."}</div>
        <section className="metric-grid"><MetricCard label="Scorecard cells" value={summary.scorecards}/><MetricCard label="Open gaps" value={summary.gaps}/><MetricCard label="Actions" value={summary.actions}/><MetricCard label="Alerts" value={summary.alerts}/></section>
        <Card className="overview-chart-card"><CardHeader><div><CardTitle>Decision workload</CardTitle><p className="muted">Current published records. Use the module pages to inspect freshness and evidence.</p></div></CardHeader><OverviewChart data={[{ label: "Scorecards", value: summary.scorecards }, { label: "Gaps", value: summary.gaps }, { label: "Actions", value: summary.actions }, { label: "Alerts", value: summary.alerts }]} /></Card>
      </>}
    </>
  );
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return <Card className="metric-card"><span>{label}</span><strong>{value}</strong></Card>;
}
