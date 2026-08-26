"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export type OverviewMetric = { label: string; value: number };

export function OverviewChart({ data }: { data: OverviewMetric[] }) {
  return (
    <div className="chart-shell" role="img" aria-label={data.map((item) => `${item.label}: ${item.value}`).join(", ")}>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 12, right: 8, bottom: 0, left: -22 }}>
          <CartesianGrid vertical={false} stroke="var(--line)" />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: "var(--muted)", fontSize: 12 }} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: "var(--muted)", fontSize: 12 }} />
          <Tooltip cursor={{ fill: "rgba(141, 212, 186, 0.08)" }} contentStyle={{ background: "var(--surface-raised)", border: "1px solid var(--line)", borderRadius: 8 }} />
          <Bar dataKey="value" fill="var(--accent)" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
