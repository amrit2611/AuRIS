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
    <div
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
        const file = e.dataTransfer.files?.[0];
        handleFile(file);
      }}
      className={[
        "cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition",
        dragOver ? "border-series-1 bg-series-1/5" : "border-surface-border",
        disabled ? "cursor-not-allowed opacity-40" : "hover:border-series-1",
      ].join(" ")}
    >
      <div className="mx-auto flex flex-col items-center gap-2">
        <div className="text-2xl">📥</div>
        <div className="text-lg font-semibold">
          Drop a transaction CSV here, or click to browse
        </div>
        <div className="text-sm text-ink-muted">
          Any CSV works. If your columns are not
          <span className="mx-1 rounded bg-surface-raised px-1 py-0.5 text-ink-secondary">
            vendor / amount / date / invoice_id
          </span>
          Llama 3.3 70B will auto-map them.
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
          disabled={disabled}
        />
      </div>
    </div>
  );
}
