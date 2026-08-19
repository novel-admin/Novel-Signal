"use client";

import { useEffect, useState } from "react";
import { ChangeTable } from "../../components/ChangeTable";
import { WorkEmpty, WorkError, WorkLoading } from "../../components/WorkStates";
import { loadChanges } from "../work/api";
import type { ChangeEvent } from "../work/types";

export default function ChangesPage() {
  const [changes, setChanges] = useState<ChangeEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { loadChanges().then(setChanges).catch((cause: Error) => setError(cause.message)); }, []);
  return <><div className="eyebrow">Evidence-backed changes</div><h1>Changes</h1><p className="lede">Review changes detected between valid observations. Open a change to see its evidence and create owned work.</p>{error ? <WorkError message={error} /> : changes === null ? <WorkLoading /> : changes.length === 0 ? <WorkEmpty message="No changes have been recorded yet." /> : <ChangeTable changes={changes} />}</>;
}

