import type { AnalysisMetrics, PerCheckCounts } from "@/lib/types";

interface Props {
  metrics: AnalysisMetrics;
  perCheck: PerCheckCounts;
}

function Tile({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="tile tile-hover relative p-4">
      {accent && (
        <span
          className="absolute inset-x-0 top-0 h-0.5 rounded-t-xl"
          style={{ background: accent }}
          aria-hidden
        />
      )}
      <div className="text-[11px] uppercase tracking-wider text-ink-muted">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular">{value}</div>
      {sub && <div className="mt-1 text-xs text-ink-muted">{sub}</div>}
    </div>
  );
}

const CHECK_COLORS: Record<keyof PerCheckCounts, string> = {
  duplicates: "#3987e5", // series-1 blue
  anomalies: "#d95926", // series-8 orange
  missing: "#c98500", // series-3 yellow
  high_frequency: "#199e70", // series-2 aqua
  amount_deviation: "#9085e9", // series-5 violet
};

export function MetricsRow({ metrics, perCheck }: Props) {
  const flagPct =
    metrics.total_transactions > 0
      ? (
          (metrics.flagged_pool_unique / metrics.total_transactions) *
          100
        ).toFixed(1)
      : "0.0";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Tile
          label="Flagged pool"
          value={metrics.flagged_pool_unique.toLocaleString()}
          sub={`${flagPct}% of dataset (candidates)`}
        />
        <Tile
          label="Total transactions"
          value={metrics.total_transactions.toLocaleString()}
        />
        <Tile
          label="Unique vendors"
          value={metrics.unique_vendors.toLocaleString()}
        />
        <Tile
          label="Flagged $ exposure"
          value={`$${Math.round(
            metrics.total_flagged_amount,
          ).toLocaleString()}`}
        />
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-5">
        <Tile
          label="Duplicates"
          value={perCheck.duplicates.toLocaleString()}
          accent={CHECK_COLORS.duplicates}
        />
        <Tile
          label="Anomalies"
          value={perCheck.anomalies.toLocaleString()}
          accent={CHECK_COLORS.anomalies}
        />
        <Tile
          label="Missing data"
          value={perCheck.missing.toLocaleString()}
          accent={CHECK_COLORS.missing}
        />
        <Tile
          label="High frequency"
          value={perCheck.high_frequency.toLocaleString()}
          accent={CHECK_COLORS.high_frequency}
        />
        <Tile
          label="Amount deviation"
          value={perCheck.amount_deviation.toLocaleString()}
          accent={CHECK_COLORS.amount_deviation}
        />
      </div>
      <p className="text-xs leading-relaxed text-ink-muted">
        <span className="font-medium text-ink-secondary">
          Industry reference:
        </span>{" "}
        1-5% flagged is a healthy review pool (ISA 320, PCAOB). Wide real-world
        CSVs with concentrated vendors routinely land in the 20-50% band; that
        is data shape, not a problem. The priority queue narrows it back down.
      </p>
    </div>
  );
}
