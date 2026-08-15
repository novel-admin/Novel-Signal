type StateProps = { message?: string };

export function LoadingState({ message = "Loading" }: StateProps) {
  return <div className="state state-loading" role="status" aria-live="polite">{message}…</div>;
}

export function EmptyState({ message = "No records yet" }: StateProps) {
  return <div className="state state-empty">{message}</div>;
}

export function ErrorState({ message = "We could not load this data" }: StateProps) {
  return <div className="state state-error" role="alert">{message}</div>;
}

export function UnknownState({ label = "Unknown" }: { label?: string }) {
  return <span className="unknown">{label}</span>;
}

export function StaleState({ updatedAt }: { updatedAt?: string | null }) {
  const text = updatedAt ? `Stale · last updated ${updatedAt}` : "Stale data";
  return <span className="badge badge-stale" title={text}>{text}</span>;
}
