import type { AnalysisMetrics, PerCheckCounts } from "@/lib/types";

interface Props {
  metrics: AnalysisMetrics;
  perCheck: PerCheckCounts;
}

function Tile({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-raised p-4">
      <div className="text-xs uppercase tracking-wider text-ink-muted">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular">{value}</div>
      {sub && <div className="mt-1 text-xs text-ink-muted">{sub}</div>}
    </div>
  );
}

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
      <div className="grid grid-cols-5 gap-4">
        <Tile label="Duplicates" value={perCheck.duplicates.toLocaleString()} />
        <Tile label="Anomalies" value={perCheck.anomalies.toLocaleString()} />
        <Tile
          label="Missing Data"
          value={perCheck.missing.toLocaleString()}
        />
        <Tile
          label="High Frequency"
          value={perCheck.high_frequency.toLocaleString()}
        />
        <Tile
          label="Amount Deviation"
          value={perCheck.amount_deviation.toLocaleString()}
        />
      </div>
      <p className="text-xs text-ink-muted">
        Industry reference: 1-5% flagged is a healthy review pool (ISA 320,
        PCAOB). Wide real-world CSVs with concentrated vendors routinely land
        in the 20-50% band; that is data shape, not a problem. The priority
        queue narrows it back down.
      </p>
    </div>
  );
}
