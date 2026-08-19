import Link from "next/link";
import type { Action } from "../app/work/types";

export function ActionTable({ actions }: { actions: Action[] }) {
  return <div className="table-wrap"><table className="data-table"><thead><tr><th>Action</th><th>Owner</th><th>Due</th><th>Status</th><th>Created</th><th /></tr></thead><tbody>
    {actions.map((action) => <tr key={action.id}><td><div className="primary-cell"><strong>{action.title}</strong><span>{action.reason ?? "No reason recorded"}</span></div></td><td>{action.owner_user_id ?? "Unassigned"}</td><td>{action.due_at ? new Date(action.due_at).toLocaleDateString() : "-"}</td><td><span className={`status ${action.status}`}>{action.status.replace("_", " ")}</span></td><td>{new Date(action.created_at).toLocaleString()}</td><td><Link className="evidence-link" href={`/actions/${action.id}`}>Open</Link></td></tr>)}
  </tbody></table></div>;
}

