"use client";

import { useEffect, useState } from "react";
import { request } from "@novel-signal/api-client";
import { WorkEmpty, WorkError, WorkLoading } from "../../components/WorkStates";

type Keyword = { id: string; text: string; source: string; intent: string | null; tier: string; active: boolean };

export default function KeywordsPage() {
  const [items, setItems] = useState<Keyword[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { request<{ items: Keyword[] }>("/keywords").then((data) => setItems(data.items)).catch((cause: Error) => setError(cause.message)); }, []);
  return <><div className="eyebrow">S2 Keyword Intelligence</div><h1>Keywords</h1><p className="lede">Review the active keywords used for Week 1 marketplace captures.</p>{error ? <WorkError message={error} /> : items === null ? <WorkLoading /> : items.length === 0 ? <WorkEmpty message="No keywords have been configured yet." /> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Keyword</th><th>Source</th><th>Intent</th><th>Tier</th><th>Status</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{item.text}</td><td>{item.source}</td><td>{item.intent ?? "-"}</td><td>{item.tier}</td><td>{item.active ? "Active" : "Inactive"}</td></tr>)}</tbody></table></div>}</>;
}

