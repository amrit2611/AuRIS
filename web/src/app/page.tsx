"use client";

import { useState } from "react";
import { postAnalyze } from "@/lib/api";
import type { AnalysisResponse } from "@/lib/types";
import { UploadZone } from "@/components/UploadZone";
import { PriorityQueueHero } from "@/components/PriorityQueueHero";
import { MetricsRow } from "@/components/MetricsRow";
import { FindingsTable } from "@/components/FindingsTable";
import { AiSummary } from "@/components/AiSummary";

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
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-3xl font-bold">
          🔍 AuRIS - Audit Risk Identification System
        </h1>
        <p className="mt-2 text-sm text-ink-secondary">
          Upload any transactions CSV. AuRIS uses an LLM to auto-map your
          column names, runs six risk checks, scores every row 0-100, ranks
          the highest-risk rows into a priority queue, and writes a
          CFO-readable executive summary.{" "}
          <strong>
            Demo tool: do not upload sensitive or production data.
          </strong>
        </p>
      </header>

      <section className="mb-8">
        <UploadZone onFileSelected={handleFile} disabled={loading} />
        {fileName && !loading && !error && analysis && (
          <div className="mt-3 text-xs text-ink-muted">
            Analysed <span className="text-ink-secondary">{fileName}</span>.
            Drop another file to run again.
          </div>
        )}
      </section>

      {loading && (
        <section className="mb-8 rounded-xl border border-surface-border bg-surface-raised p-6">
          <div className="flex items-center gap-3">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-series-1 border-t-transparent" />
            <span>Analysing {fileName ?? "your CSV"}…</span>
          </div>
          <p className="mt-2 text-xs text-ink-muted">
            LLM column detection (if needed) plus six risk checks plus scoring.
            On a wide CSV like the 286-column USASpending export this runs in
            about 3-6 seconds; most CSVs finish under 2 seconds.
          </p>
        </section>
      )}

      {error && (
        <section className="mb-8 rounded-lg border border-status-crit/40 bg-status-crit/10 p-4 text-sm text-status-crit">
          <div className="font-semibold">Analysis failed</div>
          <div className="mt-1">{error}</div>
        </section>
      )}

      {analysis && (
        <>
          {analysis.column_mapping.used && (
            <section className="mb-6 rounded-lg border border-series-2/40 bg-series-2/5 p-4 text-sm">
              <div className="mb-2 font-semibold text-series-2">
                🤖 LLM column mapping applied
              </div>
              <div className="grid grid-cols-2 gap-1 text-xs md:grid-cols-4">
                {Object.entries(analysis.column_mapping.mapping).map(
                  ([field, source]) => (
                    <div key={field}>
                      <span className="text-ink-muted">{field}</span>
                      <span className="mx-1 text-ink-muted">→</span>
                      <span className="text-ink-primary">
                        {source ?? "(none)"}
                      </span>
                    </div>
                  ),
                )}
              </div>
            </section>
          )}

          <section className="mb-8 space-y-6">
            <PriorityQueueHero metrics={analysis.metrics} />
            <MetricsRow
              metrics={analysis.metrics}
              perCheck={analysis.per_check_counts}
            />
          </section>

          <section className="mb-8">
            <h2 className="mb-3 text-xl font-semibold">
              🚩 Findings: scored triage queue
            </h2>
            <FindingsTable scored={analysis.scored_rows} />
          </section>

          <section className="mb-8">
            <h2 className="mb-3 text-xl font-semibold">🤖 AI executive summary</h2>
            <p className="mb-4 text-sm text-ink-muted">
              Groq&apos;s free tier (14,400 requests/day, no credit card)
              generates a CFO-readable summary. Groups by risk type,
              quantifies dollar exposure, names specific vendors, ends with
              prioritised actions from the scored queue.
            </p>
            <AiSummary
              reportRows={analysis.report_rows}
              scoredRows={analysis.scored_rows}
            />
          </section>
        </>
      )}

      <footer className="mt-16 border-t border-surface-border pt-4 text-xs text-ink-muted">
        Built with FastAPI + Next.js 15. Source and docs at{" "}
        <a
          href="https://github.com/amrit2611/AuRIS"
          className="text-series-1 hover:underline"
        >
          github.com/amrit2611/AuRIS
        </a>
        .
      </footer>
    </main>
  );
}
