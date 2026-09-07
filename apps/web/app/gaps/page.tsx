"use client";

import { useEffect, useState } from "react";
import { WorkEmpty, WorkError, WorkLoading } from "../../components/WorkStates";
import { loadRows, type IntelligenceRow } from "../intelligence/api";

export default function GapsPage() {
  const [rows, setRows] = useState<IntelligenceRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    loadRows("/gaps")
      .then(setRows)
      .catch((cause: Error) => setError(cause.message));
  }, []);
  return (
    <>
      <div className="eyebrow">S10 · Gaps</div>
      <h1>Gaps</h1>
      <p className="lede">
        Lagging scorecard cells with evidence, revenue at stake, and linked actions.
      </p>
      {error ? (
        <WorkError message={error} />
      ) : rows === null ? (
        <WorkLoading />
      ) : rows.length === 0 ? (
        <WorkEmpty message="No open gaps. Gaps appear when a scorecard cell turns lagging or critical." />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Dimension</th>
                <th>Entity</th>
                <th>Status</th>
                <th>Revenue at stake</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={String(row.id)}>
                  <td>{String(row.dimension)}</td>
                  <td>{String(row.entity_id)}</td>
                  <td>{String(row.status)}</td>
                  <td>{row.revenue_at_stake == null ? "Unknown" : String(row.revenue_at_stake)}</td>
                  <td>{row.evidence ? JSON.stringify(row.evidence) : "No evidence link"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
