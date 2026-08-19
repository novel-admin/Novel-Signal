"use client";

import { useEffect, useState } from "react";
import { loadOperations } from "../work/api";
import { WorkError, WorkLoading } from "../../components/WorkStates";
import type { OperationsModule } from "../work/api";

export default function OperationsPage() {
  const [module, setModule] = useState<OperationsModule | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { loadOperations().then(setModule).catch((cause: Error) => setError(cause.message)); }, []);
  return <><div className="eyebrow">Collection health</div><h1>Operations</h1><p className="lede">Check whether collection infrastructure is connected before trusting the latest data.</p>{error ? <WorkError message={error} /> : module === null ? <WorkLoading /> : <section className="grid"><article className="card"><span>Collection module</span><strong>{module.status}</strong></article><article className="card"><span>Owner</span><strong>{module.owner}</strong></article><article className="card"><span>Current scope</span><strong>Week 1</strong></article></section>}</>;
}

