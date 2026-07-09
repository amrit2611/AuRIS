import type { AnalysisMetrics } from "@/lib/types";

interface Props {
  metrics: AnalysisMetrics;
}

export function PriorityQueueHero({ metrics }: Props) {
  const {
    priority_queue_count,
    top_score,
    median_score,
    flagged_pool_unique,
  } = metrics;
  return (
    <div className="rounded-xl border border-surface-border bg-surface-raised p-6">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <div>
          <div className="text-sm text-ink-secondary">Priority queue</div>
          <div className="mt-1 text-6xl font-bold text-series-1 tabular">
            {priority_queue_count.toLocaleString()}
          </div>
          <div className="mt-2 text-xs text-ink-muted">
            rows scoring ≥ 50/100
          </div>
        </div>
        <div className="md:col-span-2">
          <div className="mb-2 text-sm text-ink-secondary">
            How to read this dashboard
          </div>
          <ul className="space-y-2 text-sm leading-relaxed">
            <li>
              <span className="text-ink-primary">
                Investigate the{" "}
                <strong>{priority_queue_count.toLocaleString()} rows</strong>{" "}
                in the priority queue first
              </span>{" "}
              (see the <em>Findings</em> section). Top score is{" "}
              <strong>{top_score.toFixed(0)}/100</strong>; median across all
              flagged rows is <strong>{median_score.toFixed(0)}/100</strong>.
            </li>
            <li>
              The larger flagged pool (
              {flagged_pool_unique.toLocaleString()} rows) is the candidate set
              scoring drew from. It is not your homework list; wide real-world
              CSVs routinely produce broad pools by design.
            </li>
            <li>
              The <em>AI Summary</em> button below writes a CFO-readable
              narrative over the ranked queue.
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
