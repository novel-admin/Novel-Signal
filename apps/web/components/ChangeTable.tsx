import Link from "next/link";
import type { ChangeEvent } from "../app/work/types";

export function ChangeTable({ changes }: { changes: ChangeEvent[] }) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead><tr><th>Detected</th><th>Change</th><th>Target</th><th>Before</th><th>After</th><th>Priority</th><th /></tr></thead>
        <tbody>
          {changes.map((change) => (
            <tr key={change.id}>
              <td>{new Date(change.detected_at).toLocaleString()}</td>
              <td>{change.event_type}</td>
              <td>{change.target_type} / {change.target_id}</td>
              <td>{formatValue(change.old_value)}</td>
              <td>{formatValue(change.new_value)}</td>
              <td><span className={`status ${change.severity}`}>{change.severity}</span></td>
              <td><Link className="evidence-link" href={`/changes/${change.id}`}>Open</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatValue(value: unknown) {
  if (value === null || value === undefined) return "-";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

