"use client";

import { DRAWER_WIDTH_CSS } from "@/lib/config";

interface Props {
  open: boolean;
  overrideCount: number;
  onToggle: () => void;
}

/**
 * Floating tab anchored to the left edge of the viewport. Slides right in
 * lockstep with the drawer when opened (both use translateX with the same
 * duration and easing) so it always sits at the drawer's right edge and
 * doubles as a close affordance.
 *
 * Closed state:  ⚙  Customize  » »   (+ optional override-count badge)
 * Open state:                  « «
 *
 * The chevrons are a single SVG that rotates 180° on open; the icon,
 * label, and badge collapse via max-width + opacity so the transition
 * is one continuous motion.
 */
export function CustomizeToggle({ open, overrideCount, onToggle }: Props) {
  return (
    <div
      className="pointer-events-none fixed left-0 top-1/2 z-50 will-change-transform"
      style={{
        // translateY(-50%) centres the pill vertically; translateX shifts
        // it by the drawer width when open so it "rides" the drawer's edge.
        transform: `translateY(-50%) translateX(${open ? DRAWER_WIDTH_CSS : "0px"})`,
        transition: "transform 250ms cubic-bezier(0.2, 0.7, 0.3, 1)",
      }}
    >
      <button
        onClick={onToggle}
        aria-label={open ? "Close settings" : "Open settings"}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="focus-ring pointer-events-auto flex items-center gap-2 rounded-r-xl border border-l-0 border-surface-border bg-surface-raised py-2.5 pl-2.5 pr-3 text-ink-secondary shadow-[4px_0_16px_rgba(0,0,0,0.35)] transition-colors duration-150 hover:border-series-1/60 hover:bg-series-1/[0.08] hover:text-series-1"
      >
        {/* Gear icon: hidden when open */}
        <span
          aria-hidden
          className="flex items-center overflow-hidden transition-all duration-250 ease-[cubic-bezier(0.2,0.7,0.3,1)]"
          style={{
            width: open ? "0px" : "16px",
            opacity: open ? 0 : 1,
          }}
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
          >
            <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        </span>

        {/* Label: hidden when open */}
        <span
          className="overflow-hidden whitespace-nowrap text-sm font-medium transition-all duration-250 ease-[cubic-bezier(0.2,0.7,0.3,1)]"
          style={{
            maxWidth: open ? "0px" : "120px",
            opacity: open ? 0 : 1,
          }}
        >
          Customize
        </span>

        {/* Override badge: hidden when open */}
        <span
          aria-hidden={open || overrideCount === 0}
          className="overflow-hidden whitespace-nowrap rounded-full text-xs font-semibold text-white tabular transition-all duration-250 ease-[cubic-bezier(0.2,0.7,0.3,1)]"
          style={{
            maxWidth: open || overrideCount === 0 ? "0px" : "40px",
            opacity: open || overrideCount === 0 ? 0 : 1,
            marginRight: open || overrideCount === 0 ? "0px" : "2px",
            padding: open || overrideCount === 0 ? "0" : "0.125rem 0.375rem",
            backgroundColor:
              open || overrideCount === 0 ? "transparent" : "#3987e5",
          }}
        >
          {overrideCount}
        </span>

        {/* Double chevron: rotates 180° when open (» » -> « «) */}
        <span
          aria-hidden
          className="flex items-center transition-transform duration-250 ease-[cubic-bezier(0.2,0.7,0.3,1)]"
          style={{
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
          }}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m6 17 5-5-5-5" />
            <path d="m13 17 5-5-5-5" />
          </svg>
        </span>
      </button>
    </div>
  );
}
