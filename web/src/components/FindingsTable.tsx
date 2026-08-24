"use client";

import { useMemo, useState } from "react";
import type { ScoredRow } from "@/lib/types";

interface Props {
  scored: ScoredRow[];
}

function fmtAmount(a: number | null | undefined): string {
  if (a === null || a === undefined || Number.isNaN(a)) return "-";
  return `$${a.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function ScorePill({ score }: { score: number }) {
  const styles =
    score >= 70
      ? "bg-status-crit/20 text-status-crit ring-status-crit/30"
      : score >= 50
        ? "bg-status-warn/20 text-status-warn ring-status-warn/30"
        : score >= 30
          ? "bg-series-1/20 text-series-1 ring-series-1/30"
          : "bg-surface-border text-ink-muted ring-surface-border";
  return (
    <span
      className={`inline-flex min-w-[2.25rem] items-center justify-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset tabular ${styles}`}
    >
      {score.toFixed(0)}
    </span>
  );
}

export function FindingsTable({ scored }: Props) {
  const [minScore, setMinScore] = useState(30);
  const [maxRows, setMaxRows] = useState(50);

  const filtered = useMemo(
    () => scored.filter((r) => r.risk_score >= minScore).slice(0, maxRows),
    [scored, minScore, maxRows],
  );

  if (!scored.length) {
    return (
      <div className="tile p-8 text-center text-ink-muted">
        No rows flagged under current thresholds.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <label className="flex items-center gap-3 text-sm">
          <span className="text-ink-secondary">Min score</span>
          <input
            type="range"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="focus-ring h-1 w-40 cursor-pointer appearance-none rounded-full bg-surface-border accent-series-1"
          />
          <span className="inline-block w-8 text-right text-sm font-semibold tabular">
            {minScore}
          </span>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-ink-secondary">Show top</span>
          <select
            value={maxRows}
            onChange={(e) => setMaxRows(Number(e.target.value))}
            className="focus-ring cursor-pointer rounded-md border border-surface-border bg-surface-raised px-2 py-1 text-sm transition hover:border-series-1/50"
          >
            {[20, 50, 100, 250, 500].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <div className="ml-auto text-xs text-ink-muted">
          Showing{" "}
          <span className="text-ink-secondary tabular">
            {filtered.length.toLocaleString()}
          </span>{" "}
          of{" "}
          <span className="text-ink-secondary tabular">
            {scored.length.toLocaleString()}
          </span>{" "}
          scored rows.
        </div>
      </div>

      <div className="custom-scroll tile max-h-[560px] overflow-auto p-0">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-surface-raised/95 backdrop-blur text-ink-secondary">
            <tr className="text-left">
              <th className="px-4 py-3 text-xs uppercase tracking-wider">
                Score
              </th>
              <th className="px-4 py-3 text-xs uppercase tracking-wider">
                Vendor
              </th>
              <th className="px-4 py-3 text-right text-xs uppercase tracking-wider">
                Amount
              </th>
              <th className="px-4 py-3 text-xs uppercase tracking-wider">
                Date
              </th>
              <th className="px-4 py-3 text-xs uppercase tracking-wider">
                Reasons
              </th>
              <th className="px-4 py-3 text-xs uppercase tracking-wider">
                Invoice ID
              </th>
            </tr>
          </thead>
          <tbody className="tabular">
            {filtered.map((row, i) => (
              <tr
                key={`${row.invoice_id}-${i}`}
                className="border-t border-surface-border/60 transition-colors hover:bg-series-1/[0.04]"
              >
                <td className="px-4 py-2.5">
                  <ScorePill score={row.risk_score} />
                </td>
                <td className="px-4 py-2.5 text-ink-primary">{row.vendor}</td>
                <td className="px-4 py-2.5 text-right text-ink-primary">
                  {fmtAmount(row.amount)}
                </td>
                <td className="px-4 py-2.5 text-ink-secondary">{row.date}</td>
                <td className="px-4 py-2.5 text-xs text-ink-secondary">
                  {row.reasons}
                </td>
                <td className="px-4 py-2.5 text-xs text-ink-muted">
                  {String(row.invoice_id)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
