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
    <div className="tile overflow-hidden p-6 md:p-8">
      <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
        <div className="flex flex-col justify-between">
          <div>
            <div className="text-xs uppercase tracking-wider text-ink-muted">
              Priority queue
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span
                className={[
                  "text-6xl font-bold text-series-1 tabular md:text-7xl",
                  priority_queue_count > 0
                    ? "inline-block rounded-full pulse-ring"
                    : "",
                ].join(" ")}
              >
                {priority_queue_count.toLocaleString()}
              </span>
              <span className="text-sm text-ink-muted">
                / {flagged_pool_unique.toLocaleString()}
              </span>
            </div>
            <div className="mt-3 text-xs text-ink-muted">
              rows scoring ≥ 50/100
            </div>
          </div>
          <div className="mt-6 flex gap-6">
            <div>
              <div className="text-xs uppercase tracking-wider text-ink-muted">
                Top score
              </div>
              <div className="mt-0.5 text-2xl font-semibold tabular">
                {top_score.toFixed(0)}
                <span className="text-sm text-ink-muted">/100</span>
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-ink-muted">
                Median
              </div>
              <div className="mt-0.5 text-2xl font-semibold tabular">
                {median_score.toFixed(0)}
                <span className="text-sm text-ink-muted">/100</span>
              </div>
            </div>
          </div>
        </div>

        <div className="md:col-span-2 md:border-l md:border-surface-border md:pl-8">
          <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-series-1" />
            How to read this dashboard
          </div>
          <ul className="space-y-3 text-sm leading-relaxed text-ink-secondary">
            <li>
              <span className="text-ink-primary">
                Investigate the{" "}
                <strong className="text-series-1">
                  {priority_queue_count.toLocaleString()} rows
                </strong>{" "}
                in the priority queue first
              </span>{" "}
              (see the <em>Findings</em> section below).
            </li>
            <li>
              The larger flagged pool (
              {flagged_pool_unique.toLocaleString()} rows) is the candidate
              set scoring drew from. It is not your homework list; wide
              real-world CSVs routinely produce broad pools by design.
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
