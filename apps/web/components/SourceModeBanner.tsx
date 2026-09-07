"use client";

import { useEffect, useState } from "react";
import { request } from "@novel-signal/api-client";

type SourceRow = { source_type: string; configured: boolean };

export function SourceModeBanner() {
  const [mode, setMode] = useState<string | null>(null);
  useEffect(() => {
    request<SourceRow[]>("/sources")
      .then((sources) => {
        const rows = Array.isArray(sources) ? sources : [];
        const apiConfigured = rows.some(
          (row) => row.configured && row.source_type !== "amazon_public_pages",
        );
        setMode(apiConfigured ? "api" : "public");
      })
      .catch(() => setMode("unknown"));
  }, []);
  if (mode === null) return null;
  if (mode === "api") {
    return (
      <div className="source-mode-banner" role="status">
        First-party Amazon mode: public evidence plus connected API imports. API-dependent
        values show freshness; unconnected values remain <strong>unknown</strong>, never zero.
      </div>
    );
  }
  if (mode === "unknown") {
    return (
      <div className="source-mode-banner" role="status">
        Source mode <strong>unknown</strong>: showing cached values only. Check freshness before
        acting.
      </div>
    );
  }
  return (
    <div className="source-mode-banner" role="status">
      Public Amazon mode: measured public-page evidence only. Spend, units, and revenue are{" "}
      <strong>not connected</strong> and shown as <strong>unknown</strong>, never zero.
    </div>
  );
}
