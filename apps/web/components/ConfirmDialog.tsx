"use client";

import { useState } from "react";

type ConfirmDialogProps = {
  label: string;
  title?: string;
  message?: string;
  onConfirm: () => void | Promise<void>;
  disabled?: boolean;
};

export function ConfirmDialog({ label, title = "Confirm action", message = "This action cannot be undone.", onConfirm, disabled }: ConfirmDialogProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  async function confirm() {
    setBusy(true);
    try { await onConfirm(); setOpen(false); } finally { setBusy(false); }
  }
  return <>
    <button type="button" className="button button-danger" disabled={disabled} onClick={() => setOpen(true)}>{label}</button>
    {open && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setOpen(false)}>
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
        <h2 id="confirm-title">{title}</h2>
        <p>{message}</p>
        <div className="dialog-actions"><button type="button" className="button" onClick={() => setOpen(false)} disabled={busy}>Cancel</button><button type="button" className="button button-danger" onClick={confirm} disabled={busy}>{busy ? "Working…" : "Confirm"}</button></div>
      </section>
    </div>}
  </>;
}
