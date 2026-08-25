"use client";

import { useEffect, useState } from "react";
import { loadRows, type IntelligenceRow } from "../app/intelligence/api";
import { WorkEmpty, WorkError, WorkLoading } from "./WorkStates";

type Column = { key: string; label: string };

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Unknown";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function IntelligencePage({
  eyebrow,
  title,
  description,
  endpoint,
  empty,
  columns,
}: {
  eyebrow: string;
  title: string;
  description: string;
  endpoint: string;
  empty: string;
  columns: Column[];
}) {
  const [rows, setRows] = useState<IntelligenceRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    loadRows(endpoint).then(setRows).catch((cause: Error) => setError(cause.message));
  }, [endpoint]);

  return <><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p className="lede">{description}</p>
    {error ? <WorkError message={error} /> : rows === null ? <WorkLoading /> : rows.length === 0 ? <WorkEmpty message={empty} /> :
      <div className="table-wrap"><table><thead><tr>{columns.map(column => <th key={column.key}>{column.label}</th>)}</tr></thead>
      <tbody>{rows.map((row, index) => <tr key={String(row.id ?? index)}>{columns.map(column =>
        <td key={column.key}>{show(row[column.key])}</td>)}</tr>)}</tbody></table></div>}
  </>;
}
