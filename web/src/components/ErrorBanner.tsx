"use client";

import { classifyError } from "@/lib/errors";

interface Props {
  /** The raw error message caught from the API/network layer. */
  message: string;
  /** Optional dismiss callback. When present, renders a close button. */
  onDismiss?: () => void;
}

export function ErrorBanner({ message, onDismiss }: Props) {
  const { headline, hint, technical } = classifyError(message);
  const showTechnical = technical && technical !== hint;

  return (
    <div
      role="alert"
      className="rise-in rounded-xl border border-status-crit/40 bg-status-crit/[0.06] p-5 shadow-[0_1px_2px_rgba(0,0,0,0.3),0_8px_20px_-8px_rgba(208,59,59,0.35)]"
    >
      <div className="flex items-start gap-3">
        <div
          aria-hidden
          className="mt-0.5 flex h-6 w-6 flex-none items-center justify-center rounded-full bg-status-crit/20 text-status-crit"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 9v4" />
            <path d="M12 17h.01" />
            <circle cx="12" cy="12" r="10" />
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <div className="font-semibold text-status-crit">{headline}</div>
          <p className="mt-1 text-sm leading-relaxed text-ink-secondary">
            {hint}
          </p>
          {showTechnical && (
            <details className="group mt-3">
              <summary className="focus-ring inline-flex cursor-pointer items-center gap-1 rounded-sm text-xs text-ink-muted transition hover:text-ink-secondary">
                <svg
                  width="10"
                  height="10"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="transition-transform group-open:rotate-90"
                >
                  <path d="m9 18 6-6-6-6" />
                </svg>
                Technical details
              </summary>
              <pre className="custom-scroll mt-2 max-h-40 overflow-auto rounded-md border border-surface-border bg-surface p-3 text-[11px] leading-relaxed text-ink-muted">
                {technical}
              </pre>
            </details>
          )}
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            aria-label="Dismiss error"
            className="focus-ring flex-none rounded-md p-1 text-ink-muted transition hover:bg-status-crit/10 hover:text-status-crit"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
