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
          className="ml-5 list-disc space-y-1.5 text-sm leading-relaxed"
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
          className="text-sm leading-relaxed text-ink-primary"
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
          className="text-xl font-bold text-ink-primary"
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
          className="mt-4 text-base font-semibold text-series-1"
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
          className="mt-3 text-sm font-semibold text-series-8"
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
  // Bold: **text** -> <strong>text</strong>
  return s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
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
        className="w-full rounded-lg bg-series-1 px-4 py-2 font-semibold text-white transition hover:bg-series-1/85 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading
          ? "Asking Llama 3.3 70B to summarise…"
          : "🤖 Generate AI Summary"}
      </button>
      {error && (
        <div className="rounded-lg border border-status-crit/40 bg-status-crit/10 p-4 text-sm text-status-crit">
          {error}
        </div>
      )}
      {markdown && (
        <div className="rounded-xl border border-series-1/25 bg-gradient-to-b from-series-1/5 to-transparent p-6">
          <div className="space-y-3">{renderMarkdown(markdown)}</div>
          <div className="mt-6 flex justify-end">
            <a
              href={`data:text/markdown;charset=utf-8,${encodeURIComponent(markdown)}`}
              download="risk_summary.md"
              className="rounded-md border border-surface-border bg-surface-raised px-3 py-1 text-xs text-ink-secondary hover:border-series-1 hover:text-series-1"
            >
              ⬇️ Download as Markdown
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
