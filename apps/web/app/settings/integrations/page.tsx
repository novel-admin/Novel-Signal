"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiBaseUrl } from "@novel-signal/api-client";

type Connection = {
  provider: string;
  status: string;
  account_identifiers: Record<string, unknown> | null;
  scopes: string[] | null;
  last_verified_at: string | null;
  error_summary: string | null;
};

const providers = ["amazon_sp", "amazon_ads", "google_ads", "meta_ads", "amazon_public"];
const api = apiBaseUrl;

export default function IntegrationsPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [provider, setProvider] = useState(providers[0]);
  const [account, setAccount] = useState("");
  const [credentials, setCredentials] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const response = await fetch(`${api}/sources/connections`, { credentials: "include" });
    if (!response.ok) throw new Error("Unable to load integrations");
    setConnections((await response.json()) as Connection[]);
  }, []);

  useEffect(() => { void load().catch((cause) => setError(cause instanceof Error ? cause.message : "Unable to load integrations")); }, [load]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const parsed = JSON.parse(credentials) as Record<string, string>;
      const response = await fetch(`${api}/sources/connections/${provider}`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_identifiers: account ? { account } : {}, credentials: parsed }),
      });
      if (!response.ok) throw new Error("Unable to save integration");
      setCredentials("");
      setMessage(`${provider} configuration saved. Verification is still required.`);
      await load();
    } catch (cause) {
      setError(cause instanceof SyntaxError ? "Credentials must be valid JSON." : cause instanceof Error ? cause.message : "Unable to save integration");
    }
  }

  async function disconnect(name: string) {
    setError("");
    const response = await fetch(`${api}/sources/connections/${name}`, { method: "DELETE", credentials: "include" });
    if (!response.ok) { setError("Unable to disconnect integration"); return; }
    setMessage(`${name} disconnected.`);
    await load();
  }

  return <div className="universe-panel">
    <div className="eyebrow">Settings</div><h1>Integrations</h1>
    <p className="lede">Credentials are encrypted on the server. They are write-only and never returned to this page.</p>
    {error && <div className="error-banner" role="alert">{error}</div>}
    {message && <div className="success-banner" role="status">{message}</div>}
    <form className="auth-form" onSubmit={save}>
      <label htmlFor="provider">Provider</label>
      <select id="provider" value={provider} onChange={(event) => setProvider(event.target.value)}>{providers.map((name) => <option key={name} value={name}>{name.replaceAll("_", " ")}</option>)}</select>
      <label htmlFor="account">Account or profile identifier</label>
      <input id="account" value={account} onChange={(event) => setAccount(event.target.value)} placeholder="Optional account ID" />
      <label htmlFor="credentials">Credentials JSON</label>
      <textarea id="credentials" value={credentials} onChange={(event) => setCredentials(event.target.value)} placeholder='{"refresh_token":"..."}' required rows={5} />
      <button className="button primary" type="submit">Save encrypted credentials</button>
    </form>
    <h2 className="section-heading">Saved connections</h2>
    {!connections.length ? <p className="lede">No workspace integrations configured.</p> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Provider</th><th>Status</th><th>Account</th><th>Last verified</th><th /></tr></thead><tbody>{connections.map((item) => <tr key={item.provider}><td>{item.provider}</td><td>{item.status}</td><td>{item.account_identifiers?.account as string ?? "—"}</td><td>{item.last_verified_at ?? "Not verified"}</td><td><button className="button" type="button" onClick={() => void disconnect(item.provider)}>Disconnect</button></td></tr>)}</tbody></table></div>}
  </div>;
}
