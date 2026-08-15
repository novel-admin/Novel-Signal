import type { ReactNode } from "react";

export type TableColumn<T> = { key: string; label: string; render?: (row: T) => ReactNode };

export function DataTable<T extends Record<string, unknown>>({ columns, rows, rowKey }: { columns: TableColumn<T>[]; rows: T[]; rowKey: (row: T) => string }) {
  return <div className="table-wrap"><table><thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={rowKey(row)}>{columns.map((column) => <td key={column.key}>{column.render ? column.render(row) : String(row[column.key] ?? "—")}</td>)}</tr>)}</tbody></table></div>;
}
