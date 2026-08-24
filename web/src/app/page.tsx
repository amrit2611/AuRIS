"use client";

import { useState } from "react";
import { postAnalyze } from "@/lib/api";
import type { AnalysisResponse } from "@/lib/types";
import { UploadZone } from "@/components/UploadZone";
import { PriorityQueueHero } from "@/components/PriorityQueueHero";
import { MetricsRow } from "@/components/MetricsRow";
import { FindingsTable } from "@/components/FindingsTable";
import { AiSummary } from "@/components/AiSummary";

const PIPELINE_STEPS: Array<{ label: string; detail: string }> = [
  { label: "Map columns", detail: "LLM aligns any CSV to vendor / amount / date / invoice_id" },
  { label: "Run six risk checks", detail: "Duplicates, anomalies, missing data, frequency, deviation, ML" },
  { label: "Score every row 0-100", detail: "Weighted contributions across all checks, reason codes attached" },
  { label: "Rank priority queue", detail: "Rows scoring at least 50 land in the triage queue" },
  { label: "Write executive summary", detail: "Open-weight LLM via Groq, CFO-readable Markdown, one click" },
];

export default function Home() {
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setLoading(true);
    setError(null);
    setAnalysis(null);
    setFileName(file.name);
    try {
      const res = await postAnalyze(file);
      setAnalysis(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="mx-auto max-w-6xl px-4 py-10 md:py-14">
      <header className="mb-10">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-series-1/15 text-series-1 ring-1 ring-inset ring-series-1/25">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
            AuRIS
            <span className="ml-2 text-ink-muted font-normal">
              Audit Risk Identification System
            </span>
          </h1>
        </div>
        <p className="mt-4 max-w-3xl text-sm leading-relaxed text-ink-secondary md:text-base">
          Upload any transactions CSV. AuRIS uses an LLM to auto-map your column
          names, runs six risk checks, scores every row 0-100, ranks the
          highest-risk rows into a priority queue, and writes a CFO-readable
          executive summary.
        </p>
        <p className="mt-2 text-xs text-ink-muted">
          <span className="inline-block rounded bg-status-warn/15 px-1.5 py-0.5 font-medium text-status-warn">
            Demo tool
          </span>{" "}
          do not upload sensitive or production data.
        </p>
      </header>

      <section className="mb-10">
        <UploadZone onFileSelected={handleFile} disabled={loading} />
        {fileName && !loading && !error && analysis && (
          <div className="mt-3 text-xs text-ink-muted">
            Analysed{" "}
            <span className="text-ink-secondary">{fileName}</span>. Drop
            another file to run again.
          </div>
        )}
      </section>

      {!analysis && !loading && !error && (
        <section className="mb-10 tile rise-in p-6">
          <div className="mb-4 flex items-center gap-2 text-sm text-ink-secondary">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-series-1" />
            What happens when you drop a CSV
          </div>
          <ol className="space-y-3">
            {PIPELINE_STEPS.map((step, i) => (
              <li key={step.label} className="flex items-start gap-3">
                <span className="mt-0.5 flex h-6 w-6 flex-none items-center justify-center rounded-full bg-surface-border text-xs font-semibold text-ink-secondary tabular">
                  {i + 1}
                </span>
                <div>
                  <div className="text-sm font-medium text-ink-primary">
                    {step.label}
                  </div>
                  <div className="text-xs text-ink-muted">{step.detail}</div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {loading && (
        <section className="mb-10 tile rise-in p-6">
          <div className="flex items-center gap-3">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-series-1 border-t-transparent" />
            <span className="text-sm font-medium">
              Analysing {fileName ?? "your CSV"}…
            </span>
          </div>
          <p className="mt-2 text-xs text-ink-muted">
            LLM column detection (if needed) plus six risk checks plus scoring.
            Most CSVs finish under 2 seconds; a wide 286-column USASpending
            export takes 3-6 seconds.
          </p>
        </section>
      )}

      {error && (
        <section className="mb-10 rise-in rounded-xl border border-status-crit/40 bg-status-crit/10 p-5 text-sm text-status-crit">
          <div className="font-semibold">Analysis failed</div>
          <div className="mt-1 text-status-crit/90">{error}</div>
        </section>
      )}

      {analysis && (
        <div className="rise-in">
          {analysis.column_mapping.used && (
            <section className="mb-6 rounded-xl border border-series-2/40 bg-series-2/5 p-5 text-sm">
              <div className="mb-2 flex items-center gap-2 font-semibold text-series-2">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden
                >
                  <path d="M12 8V4H8" />
                  <rect x="4" y="8" width="16" height="12" rx="2" />
                  <path d="M2 14h2M20 14h2M15 13v2M9 13v2" />
                </svg>
                LLM column mapping applied
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
                {Object.entries(analysis.column_mapping.mapping).map(
                  ([field, source]) => (
                    <div
                      key={field}
                      className="rounded-md border border-series-2/20 bg-series-2/[0.04] px-2 py-1.5"
                    >
                      <div className="text-ink-muted">{field}</div>
                      <div className="mt-0.5 font-medium text-ink-primary">
                        {source ?? "(none)"}
                      </div>
                    </div>
                  ),
                )}
              </div>
            </section>
          )}

          <section className="mb-10 space-y-6">
            <PriorityQueueHero metrics={analysis.metrics} />
            <MetricsRow
              metrics={analysis.metrics}
              perCheck={analysis.per_check_counts}
            />
          </section>

          <section className="mb-10">
            <div className="mb-4 flex items-baseline justify-between gap-3">
              <h2 className="text-xl font-semibold tracking-tight">
                Findings
                <span className="ml-2 text-sm font-normal text-ink-muted">
                  scored triage queue
                </span>
              </h2>
            </div>
            <FindingsTable scored={analysis.scored_rows} />
          </section>

          <section className="mb-10">
            <div className="mb-4">
              <h2 className="text-xl font-semibold tracking-tight">
                AI executive summary
              </h2>
              <p className="mt-1 text-sm text-ink-muted">
                Groq&apos;s free tier (14,400 requests/day, no credit card)
                generates a CFO-readable summary. Groups by risk type,
                quantifies dollar exposure, names specific vendors, ends with
                prioritised actions from the scored queue.
              </p>
            </div>
            <AiSummary
              reportRows={analysis.report_rows}
              scoredRows={analysis.scored_rows}
            />
          </section>
        </div>
      )}

      <footer className="mt-16 border-t border-surface-border pt-6 text-xs text-ink-muted">
        Built with FastAPI + Next.js 15. Source and docs at{" "}
        <a
          href="https://github.com/amrit2611/AuRIS"
          className="text-series-1 transition hover:text-series-1/80 hover:underline focus-ring rounded-sm"
        >
          github.com/amrit2611/AuRIS
        </a>
        .
      </footer>
    </main>
  );
}
