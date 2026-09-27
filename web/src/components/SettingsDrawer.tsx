"use client";

import { useEffect, useRef } from "react";
import {
  DEFAULT_SLIDER_VALUES,
  SLIDERS,
  SliderValues,
  countOverrides,
} from "@/lib/config";

interface Props {
  open: boolean;
  values: SliderValues;
  /** True when the user has already analysed a file, so we can offer re-run. */
  canReRun: boolean;
  /** True while an analysis is in flight from a previous apply. */
  applying: boolean;
  onChange: (values: SliderValues) => void;
  onClose: () => void;
  /** Called when the user clicks the primary action button. */
  onApply: () => void;
}

export function SettingsDrawer({
  open,
  values,
  canReRun,
  applying,
  onChange,
  onClose,
  onApply,
}: Props) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const overrideCount = countOverrides(values);

  // Escape closes.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Prevent background scroll while the drawer is open.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Move keyboard focus into the drawer when it opens; return it on close.
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const first = drawerRef.current?.querySelector<HTMLElement>(
      "button, input, [tabindex]:not([tabindex='-1'])",
    );
    first?.focus();
    return () => previous?.focus();
  }, [open]);

  const handleReset = () => onChange({ ...DEFAULT_SLIDER_VALUES });

  const handleSlider = (key: keyof SliderValues, raw: string) => {
    const next = Number(raw);
    if (Number.isNaN(next)) return;
    onChange({ ...values, [key]: next });
  };

  const primaryLabel = applying
    ? "Applying…"
    : canReRun
      ? "Apply and re-run"
      : "Save settings";

  return (
    <>
      {/* Backdrop */}
      <div
        aria-hidden={!open}
        onClick={onClose}
        className={[
          "fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity duration-200",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        ].join(" ")}
      />

      {/* Panel */}
      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-drawer-title"
        aria-hidden={!open}
        className={[
          "fixed inset-y-0 right-0 z-50 flex w-full max-w-[420px] flex-col",
          "border-l border-surface-border bg-surface shadow-[-8px_0_32px_rgba(0,0,0,0.4)]",
          "transition-transform duration-250 ease-[cubic-bezier(0.2,0.7,0.3,1)]",
          open ? "translate-x-0" : "translate-x-full",
        ].join(" ")}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-surface-border px-6 py-5">
          <div>
            <h2
              id="settings-drawer-title"
              className="text-lg font-semibold tracking-tight"
            >
              Tune analysis
            </h2>
            <p className="mt-1 text-xs text-ink-muted">
              Adjust the same four thresholds as the Streamlit dashboard.{" "}
              {overrideCount > 0 ? (
                <>
                  <span className="text-series-1">{overrideCount}</span>{" "}
                  {overrideCount === 1 ? "override" : "overrides"} active.
                </>
              ) : (
                "Currently at defaults."
              )}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close settings"
            className="focus-ring flex-none rounded-md p-1 text-ink-muted transition hover:bg-surface-raised hover:text-ink-primary"
          >
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
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Sliders (scrollable in case the viewport is short) */}
        <div className="custom-scroll flex-1 space-y-6 overflow-y-auto px-6 py-5">
          {SLIDERS.map((spec) => {
            const value = values[spec.key];
            const isDefault =
              Math.abs(value - spec.default) < spec.step / 2;
            return (
              <div key={spec.key} className="tile p-4">
                <div className="mb-2 flex items-baseline justify-between gap-3">
                  <label
                    htmlFor={`slider-${spec.key}`}
                    className="text-sm font-medium text-ink-primary"
                  >
                    {spec.label}
                  </label>
                  <span
                    className={[
                      "rounded-md px-2 py-0.5 text-xs font-semibold tabular",
                      isDefault
                        ? "bg-surface-border text-ink-secondary"
                        : "bg-series-1/20 text-series-1 ring-1 ring-inset ring-series-1/30",
                    ].join(" ")}
                  >
                    {spec.format(value)}
                  </span>
                </div>
                <input
                  id={`slider-${spec.key}`}
                  type="range"
                  min={spec.min}
                  max={spec.max}
                  step={spec.step}
                  value={value}
                  onChange={(e) => handleSlider(spec.key, e.target.value)}
                  className="focus-ring h-1 w-full cursor-pointer appearance-none rounded-full bg-surface-border accent-series-1"
                />
                <div className="mt-2 flex items-center justify-between text-[11px] text-ink-muted">
                  <span>{spec.help}</span>
                  <span className="flex-none tabular">
                    default {spec.format(spec.default)}
                  </span>
                </div>
              </div>
            );
          })}

          <p className="text-xs leading-relaxed text-ink-muted">
            <span className="font-medium text-ink-secondary">
              Industry reference:
            </span>{" "}
            1-5% flagged is a healthy review pool (ISA 320, PCAOB). Wide
            real-world CSVs with concentrated vendors routinely land in
            the 20-50% band; that is data shape, not a problem.
          </p>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 border-t border-surface-border px-6 py-4">
          <button
            onClick={handleReset}
            disabled={overrideCount === 0}
            className="focus-ring rounded-md px-2 py-1 text-xs text-ink-muted transition hover:text-ink-primary disabled:cursor-not-allowed disabled:opacity-40"
          >
            Reset to defaults
          </button>
          <button
            onClick={onApply}
            disabled={applying}
            className="focus-ring inline-flex items-center gap-2 rounded-lg bg-series-1 px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_2px_rgba(0,0,0,0.3),0_6px_14px_-4px_rgba(57,135,229,0.45)] transition-all duration-150 hover:-translate-y-px hover:bg-series-1/95 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
          >
            {applying && (
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/70 border-t-transparent" />
            )}
            {primaryLabel}
          </button>
        </div>
      </aside>
    </>
  );
}
