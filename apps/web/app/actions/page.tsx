"use client";

import { useEffect, useState } from "react";
import { ActionTable } from "../../components/ActionTable";
import { WorkEmpty, WorkError, WorkLoading } from "../../components/WorkStates";
import { loadActions } from "../work/api";
import type { Action } from "../work/types";

export default function ActionsPage() {
  const [actions, setActions] = useState<Action[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { loadActions().then(setActions).catch((cause: Error) => setError(cause.message)); }, []);
  return <><div className="eyebrow">Owned work</div><h1>Actions</h1><p className="lede">Track work created from competitive changes, including its owner, due date, status, and outcome.</p>{error ? <WorkError message={error} /> : actions === null ? <WorkLoading /> : actions.length === 0 ? <WorkEmpty message="No actions have been created yet." /> : <ActionTable actions={actions} />}</>;
}

