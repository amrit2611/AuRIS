"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Treemap,
  XAxis,
  YAxis,
} from "recharts";
import type { AnalysisResponse, ReportRow, ScoredRow } from "@/lib/types";

interface Props {
  data: AnalysisResponse;
}

/** Number formatter for tooltip values. */
const fmtCount = (n: number) => n.toLocaleString();
const fmtUsd = (n: number) =>
  `$${Math.round(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

/* -------------------------------------------------------------
 * Data aggregations — every chart derives its shape from the
 * analysis response we already hold in state; no extra fetches.
 * ------------------------------------------------------------- */

function scoreHistogram(scored: ScoredRow[]) {
  const bins = Array.from({ length: 10 }, (_, i) => ({
    bucket: `${i * 10}-${i * 10 + 9}`,
    count: 0,
    below: 0,
    above: 0,
  }));
  for (const row of scored) {
    const s = Math.min(Math.max(row.risk_score, 0), 99.9);
    const idx = Math.floor(s / 10);
    bins[idx].count += 1;
    if (s >= 50) bins[idx].above += 1;
    else bins[idx].below += 1;
  }
  return bins;
}

function topVendorsByCount(report: ReportRow[]): { vendor: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const row of report) {
    if (!row.vendor) continue;
    counts.set(row.vendor, (counts.get(row.vendor) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([vendor, count]) => ({ vendor, count }));
}

function vendorFlaggedTreemap(
  report: ReportRow[],
): { name: string; size: number }[] {
  const sums = new Map<string, number>();
  for (const row of report) {
    if (!row.vendor || row.amount === null || row.amount === undefined) continue;
    sums.set(row.vendor, (sums.get(row.vendor) ?? 0) + row.amount);
  }
  return Array.from(sums.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .map(([vendor, value]) => ({
      name: vendor.length > 24 ? vendor.slice(0, 22) + "…" : vendor,
      size: value,
    }));
}

/* -------------------------------------------------------------
 * Recharts theme: matches the AuRIS token palette; every colour
 * reads on both the light and dark themes we actually ship.
 * ------------------------------------------------------------- */
const PALETTE = {
  primary: "#3987e5", // series-1 blue
  crit: "#d03b3b",    // priority-queue band
  muted: "#898781",   // ink-muted
  border: "#2c2c2a",
  ramp: [
    "#0e3a68", "#124d84", "#1660a0", "#1a72bc", "#2385d7",
    "#3987e5", "#5aa0eb", "#7cb8f0", "#9fd0f4", "#c1e2f7",
  ],
};

function ChartCard({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="tile p-4 md:p-5">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-ink-primary">{title}</h3>
        <p className="mt-1 text-xs text-ink-muted">{hint}</p>
      </div>
      <div className="h-[240px] w-full">{children}</div>
    </div>
  );
}

export default function VisualizationsPanel({ data }: Props) {
  const histData = useMemo(() => scoreHistogram(data.scored_rows), [data.scored_rows]);
  const vendorCounts = useMemo(() => topVendorsByCount(data.report_rows), [data.report_rows]);
  const treemapData = useMemo(() => vendorFlaggedTreemap(data.report_rows), [data.report_rows]);

  return (
    <div className="rise-in space-y-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Score distribution"
          hint="Where the flagged pool sits on the 0-100 scale. The red segment on each bar marks rows already in the priority queue (≥ 50)."
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={histData} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
              <CartesianGrid stroke={PALETTE.border} strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="bucket"
                stroke={PALETTE.muted}
                tick={{ fontSize: 11, fill: PALETTE.muted }}
                axisLine={{ stroke: PALETTE.border }}
                tickLine={false}
              />
              <YAxis
                stroke={PALETTE.muted}
                tick={{ fontSize: 11, fill: PALETTE.muted }}
                axisLine={{ stroke: PALETTE.border }}
                tickLine={false}
                tickFormatter={(v) => fmtCount(v as number)}
              />
              <Tooltip
                cursor={{ fill: "rgba(57,135,229,0.08)" }}
                contentStyle={{
                  backgroundColor: "#1a1a19",
                  border: `1px solid ${PALETTE.border}`,
                  borderRadius: 8,
                  color: "#fff",
                  fontSize: 12,
                }}
                formatter={(v) => [fmtCount(Number(v)), "Rows"]}
                labelFormatter={(l) => `Score ${l}`}
              />
              <Bar dataKey="below" stackId="a" fill={PALETTE.primary} radius={[0, 0, 0, 0]} />
              <Bar dataKey="above" stackId="a" fill={PALETTE.crit} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Top 10 vendors by flag count"
          hint="Which vendors triggered the most check hits. Not the same as risk score, but usually correlated."
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={vendorCounts}
              layout="vertical"
              margin={{ top: 8, right: 24, left: 4, bottom: 4 }}
            >
              <CartesianGrid stroke={PALETTE.border} strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                stroke={PALETTE.muted}
                tick={{ fontSize: 11, fill: PALETTE.muted }}
                axisLine={{ stroke: PALETTE.border }}
                tickLine={false}
                tickFormatter={(v) => fmtCount(v as number)}
              />
              <YAxis
                type="category"
                dataKey="vendor"
                stroke={PALETTE.muted}
                tick={{ fontSize: 11, fill: PALETTE.muted }}
                axisLine={{ stroke: PALETTE.border }}
                tickLine={false}
                width={110}
              />
              <Tooltip
                cursor={{ fill: "rgba(57,135,229,0.08)" }}
                contentStyle={{
                  backgroundColor: "#1a1a19",
                  border: `1px solid ${PALETTE.border}`,
                  borderRadius: 8,
                  color: "#fff",
                  fontSize: 12,
                }}
                formatter={(v) => [fmtCount(Number(v)), "Flag hits"]}
              />
              <Bar dataKey="count" fill={PALETTE.primary} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <ChartCard
        title="Flagged $ exposure by vendor (top 15)"
        hint="Area proportional to the total flagged dollars attributed to each vendor. Darker = higher exposure."
      >
        <ResponsiveContainer width="100%" height="100%">
          <Treemap
            data={treemapData}
            dataKey="size"
            nameKey="name"
            stroke={PALETTE.border}
            isAnimationActive={false}
          >
            {treemapData.map((entry, i) => (
              <Cell
                key={`cell-${i}`}
                fill={PALETTE.ramp[Math.min(9, Math.floor((i / Math.max(1, treemapData.length - 1)) * 9))]}
              />
            ))}
            <Tooltip
              contentStyle={{
                backgroundColor: "#1a1a19",
                border: `1px solid ${PALETTE.border}`,
                borderRadius: 8,
                color: "#fff",
                fontSize: 12,
              }}
              formatter={(v) => [fmtUsd(Number(v)), "Flagged $"]}
            />
          </Treemap>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}
