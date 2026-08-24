"use client";

import { useState } from "react";
import { postSummarize } from "@/lib/api";
import type { ReportRow, ScoredRow } from "@/lib/types";

interface Props {
  reportRows: ReportRow[];
  scoredRows: ScoredRow[];
}

/**
 * Very small Markdown renderer: enough for the AuRIS summary shape
 * (headings, bullets, paragraphs, bold). No dependency on remark/marked
 * so the frontend bundle stays tiny.
 */
function renderMarkdown(md: string): React.ReactNode {
  const lines = md.split("\n");
  const nodes: React.ReactNode[] = [];
  let listBuffer: string[] = [];
  let paraBuffer: string[] = [];
  const flushList = () => {
    if (listBuffer.length) {
      nodes.push(
        <ul
          key={`ul-${nodes.length}`}
          className="ml-5 list-disc space-y-1.5 text-sm leading-relaxed text-ink-secondary marker:text-series-1/70"
        >
          {listBuffer.map((item, i) => (
            <li key={i} dangerouslySetInnerHTML={{ __html: inlineFormat(item) }} />
          ))}
        </ul>,
      );
      listBuffer = [];
    }
  };
  const flushPara = () => {
    if (paraBuffer.length) {
      nodes.push(
        <p
          key={`p-${nodes.length}`}
          className="text-sm leading-relaxed text-ink-secondary"
          dangerouslySetInnerHTML={{
            __html: inlineFormat(paraBuffer.join(" ")),
          }}
        />,
      );
      paraBuffer = [];
    }
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (line.startsWith("# ")) {
      flushList();
      flushPara();
      nodes.push(
        <h1
          key={`h1-${nodes.length}`}
          className="text-xl font-bold tracking-tight text-ink-primary"
        >
          {line.slice(2)}
        </h1>,
      );
    } else if (line.startsWith("## ")) {
      flushList();
      flushPara();
      nodes.push(
        <h2
          key={`h2-${nodes.length}`}
          className="mt-5 text-base font-semibold text-series-1"
        >
          {line.slice(3)}
        </h2>,
      );
    } else if (line.startsWith("### ")) {
      flushList();
      flushPara();
      nodes.push(
        <h3
          key={`h3-${nodes.length}`}
          className="mt-4 text-sm font-semibold text-series-8"
        >
          {line.slice(4)}
        </h3>,
      );
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      flushPara();
      listBuffer.push(line.slice(2));
    } else if (line === "") {
      flushList();
      flushPara();
    } else {
      flushList();
      paraBuffer.push(line);
    }
  }
  flushList();
  flushPara();
  return nodes;
}

function inlineFormat(s: string): string {
  return s.replace(/\*\*(.+?)\*\*/g, '<strong class="text-ink-primary">$1</strong>');
}

export function AiSummary({ reportRows, scoredRows }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [markdown, setMarkdown] = useState<string | null>(null);

  const canRun = reportRows.length > 0;

  const run = async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await postSummarize({
        report_rows: reportRows,
        scored_rows: scoredRows,
      });
      setMarkdown(res.summary_markdown);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <button
        onClick={run}
        disabled={!canRun || loading}
        className="focus-ring group relative flex w-full items-center justify-center gap-2 rounded-xl bg-series-1 px-5 py-3 font-semibold text-white shadow-[0_1px_2px_rgba(0,0,0,0.3),0_8px_20px_-6px_rgba(57,135,229,0.5)] transition-all duration-150 hover:-translate-y-px hover:bg-series-1/95 hover:shadow-[0_1px_2px_rgba(0,0,0,0.3),0_12px_28px_-6px_rgba(57,135,229,0.6)] active:translate-y-0 active:shadow-[0_1px_2px_rgba(0,0,0,0.3),0_4px_10px_-4px_rgba(57,135,229,0.5)] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
      >
        {loading ? (
          <>
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/70 border-t-transparent" />
            Generating executive summary…
          </>
        ) : (
          <>
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
            >
              <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.582a.5.5 0 0 1 0 .962L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z" />
            </svg>
            Generate AI Summary
          </>
        )}
      </button>
      {error && (
        <div className="rounded-xl border border-status-crit/40 bg-status-crit/10 p-4 text-sm text-status-crit">
          {error}
        </div>
      )}
      {markdown && (
        <div className="rise-in tile relative overflow-hidden bg-gradient-to-br from-series-1/[0.05] via-transparent to-series-5/[0.04] p-6 md:p-7">
          <div className="space-y-3">{renderMarkdown(markdown)}</div>
          <div className="mt-6 flex justify-end">
            <a
              href={`data:text/markdown;charset=utf-8,${encodeURIComponent(markdown)}`}
              download="risk_summary.md"
              className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-surface-border bg-surface-raised px-3 py-1.5 text-xs text-ink-secondary transition hover:border-series-1/60 hover:text-series-1"
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <path d="m7 10 5 5 5-5" />
                <path d="M12 15V3" />
              </svg>
              Download as Markdown
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
