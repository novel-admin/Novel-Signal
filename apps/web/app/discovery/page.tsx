"use client";

import { useCallback, useEffect, useState } from "react";
import { request } from "@novel-signal/api-client";
import { WorkEmpty, WorkError, WorkLoading } from "../../components/WorkStates";

type Proposal = {
  id: string;
  marketplace: string;
  marketplace_product_id: string;
  brand: string | null;
  title: string | null;
  status: string;
  score: number | null;
  appearances: number;
  best_rank: number | null;
  evidence: Record<string, unknown> | null;
};

type ProposalPage = { items: Proposal[]; total: number };

export default function DiscoveryPage() {
  const [rows, setRows] = useState<Proposal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    try {
      const page = await request<ProposalPage>("/universe/competitor-proposals?status=pending");
      setRows(page.items);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load discovery queue");
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const build = async () => {
    setNotice(null);
    try {
      const result = await request<{ created: number; updated: number; pending: number }>(
        "/universe/competitor-proposals/build",
        { method: "POST", body: {} },
      );
      setNotice(`Scan complete: ${result.created} new, ${result.updated} updated, ${result.pending} pending review.`);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Discovery scan failed");
    }
  };

  const decide = async (id: string, action: "approve" | "reject" | "archive") => {
    setNotice(null);
    try {
      await request(`/universe/competitor-proposals/${id}/${action}`, {
        method: "POST",
        body: action === "approve" ? {} : {},
      });
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `Unable to ${action} proposal`);
    }
  };

  return (
    <>
      <div className="eyebrow">S1 · Competitor discovery</div>
      <h1>Discovery queue</h1>
      <p className="lede">
        Repeated appearances become proposals with evidence. Approval creates an active
        competitor; unapproved proposals stay out of scorecards and alerts.
      </p>
      <div className="universe-toolbar">
        <button className="button" onClick={() => void build()}>
          Run discovery scan
        </button>
        <button className="button" onClick={() => void refresh()}>
          Refresh
        </button>
      </div>
      {notice ? (
        <div className="screen-reader-status" role="status">
          {notice}
        </div>
      ) : null}
      {error ? (
        <WorkError message={error} />
      ) : rows === null ? (
        <WorkLoading />
      ) : rows.length === 0 ? (
        <WorkEmpty message="No pending competitor proposals. Run a discovery scan after collection." />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ASIN</th>
                <th>Brand</th>
                <th>Score</th>
                <th>Appearances</th>
                <th>Best rank</th>
                <th>Evidence</th>
                <th>Decision</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.marketplace_product_id}</td>
                  <td>{row.brand ?? "Unknown"}</td>
                  <td>{row.score ?? "—"}</td>
                  <td>{row.appearances}</td>
                  <td>{row.best_rank ?? "—"}</td>
                  <td>{row.evidence ? JSON.stringify(row.evidence) : "No evidence link"}</td>
                  <td>
                    <button onClick={() => void decide(row.id, "approve")}>Approve</button>{" "}
                    <button onClick={() => void decide(row.id, "reject")}>Reject</button>{" "}
                    <button onClick={() => void decide(row.id, "archive")}>Archive</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
