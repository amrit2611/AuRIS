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
  const color =
    score >= 70
      ? "bg-status-crit/25 text-status-crit"
      : score >= 50
      ? "bg-status-warn/25 text-status-warn"
      : score >= 30
      ? "bg-series-1/25 text-series-1"
      : "bg-surface-border text-ink-muted";
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-semibold tabular ${color}`}
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
      <div className="rounded-xl border border-surface-border bg-surface-raised p-6 text-center text-ink-muted">
        No rows flagged under current thresholds.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4">
        <label className="text-sm">
          <span className="mr-2 text-ink-secondary">Min score</span>
          <input
            type="range"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="align-middle"
          />
          <span className="ml-2 inline-block w-8 text-right font-semibold tabular">
            {minScore}
          </span>
        </label>
        <label className="text-sm">
          <span className="mr-2 text-ink-secondary">Show top</span>
          <select
            value={maxRows}
            onChange={(e) => setMaxRows(Number(e.target.value))}
            className="rounded border border-surface-border bg-surface-raised px-2 py-1 text-sm"
          >
            {[20, 50, 100, 250, 500].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <div className="ml-auto text-xs text-ink-muted">
          Showing {filtered.length.toLocaleString()} of{" "}
          {scored.length.toLocaleString()} scored rows.
        </div>
      </div>

      <div className="custom-scroll max-h-[560px] overflow-auto rounded-xl border border-surface-border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface-raised text-ink-secondary">
            <tr className="text-left">
              <th className="px-3 py-2">Score</th>
              <th className="px-3 py-2">Vendor</th>
              <th className="px-3 py-2 text-right">Amount</th>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Reasons</th>
              <th className="px-3 py-2">Invoice ID</th>
            </tr>
          </thead>
          <tbody className="tabular">
            {filtered.map((row, i) => (
              <tr
                key={`${row.invoice_id}-${i}`}
                className="border-t border-surface-border/50 hover:bg-surface-raised/60"
              >
                <td className="px-3 py-2">
                  <ScorePill score={row.risk_score} />
                </td>
                <td className="px-3 py-2">{row.vendor}</td>
                <td className="px-3 py-2 text-right">
                  {fmtAmount(row.amount)}
                </td>
                <td className="px-3 py-2 text-ink-secondary">{row.date}</td>
                <td className="px-3 py-2 text-xs text-ink-secondary">
                  {row.reasons}
                </td>
                <td className="px-3 py-2 text-xs text-ink-muted">
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
