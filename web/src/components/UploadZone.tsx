"use client";

import { useCallback, useRef, useState } from "react";

interface Props {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}

export function UploadZone({ onFileSelected, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = useCallback(
    (file: File | null | undefined) => {
      if (!file) return;
      if (!file.name.toLowerCase().endsWith(".csv")) {
        alert("Please upload a .csv file.");
        return;
      }
      onFileSelected(file);
    },
    [onFileSelected],
  );

  return (
    <button
      type="button"
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        if (disabled) return;
        handleFile(e.dataTransfer.files?.[0]);
      }}
      disabled={disabled}
      className={[
        "focus-ring group relative w-full overflow-hidden rounded-2xl border-2 border-dashed p-10 text-center transition-all duration-200",
        dragOver
          ? "border-series-1 bg-series-1/[0.06] scale-[1.01]"
          : "border-surface-border bg-surface-raised/40",
        disabled
          ? "cursor-not-allowed opacity-40"
          : "cursor-pointer hover:border-series-1/60 hover:bg-series-1/[0.03]",
      ].join(" ")}
    >
      <div className="pointer-events-none mx-auto flex max-w-md flex-col items-center gap-3">
        <div
          className={[
            "flex h-14 w-14 items-center justify-center rounded-2xl transition-all duration-200",
            dragOver
              ? "bg-series-1 text-white scale-110"
              : "bg-surface-border text-ink-secondary group-hover:bg-series-1/20 group-hover:text-series-1",
          ].join(" ")}
        >
          <svg
            width="26"
            height="26"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <path d="m17 8-5-5-5 5" />
            <path d="M12 3v13" />
          </svg>
        </div>
        <div className="text-lg font-semibold text-ink-primary">
          {dragOver
            ? "Release to analyse"
            : "Drop a transaction CSV, or click to browse"}
        </div>
        <div className="text-xs leading-relaxed text-ink-muted">
          Any CSV works. If your columns are not{" "}
          <span className="mx-0.5 rounded bg-surface-border px-1.5 py-0.5 font-mono text-[11px] text-ink-secondary">
            vendor / amount / date / invoice_id
          </span>{" "}
          an open-weight LLM will auto-map them.
        </div>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0])}
        disabled={disabled}
      />
    </button>
  );
}
