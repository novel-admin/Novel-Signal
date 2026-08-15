export function EvidenceLink({ href, label = "View evidence" }: { href?: string | null; label?: string }) {
  if (!href) return <span className="muted">No evidence link</span>;
  return <a className="evidence-link" href={href} target="_blank" rel="noreferrer">{label} ↗</a>;
}

export function Freshness({ capturedAt, stale = false }: { capturedAt?: string | null; stale?: boolean }) {
  return <span className={stale ? "badge badge-stale" : "badge badge-fresh"}>{stale ? "Stale" : "Current"}{capturedAt ? ` · ${capturedAt}` : ""}</span>;
}
