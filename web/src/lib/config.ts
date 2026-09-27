/**
 * Client-side risk-config surface: the four sliders the SettingsDrawer
 * exposes, matching the Streamlit dashboard's tunables exactly. Values
 * are stored in localStorage so tuning persists across page loads for
 * this browser, but never leaves the machine and is never read back by
 * the backend beyond the /analyze request itself.
 *
 * Defaults intentionally match the Streamlit slider defaults, not the
 * Python RiskConfig() defaults, so the two hosted surfaces produce the
 * same numbers out of the box (Streamlit's dashboard picked tighter
 * thresholds anchored to industry practice: a 1-5% flag rate).
 */
import type { AurisConfig, RiskConfigOverrides } from "./types";

/**
 * Drawer width in px. Shared between the drawer itself and the floating
 * "Customize" toggle so both animate in lockstep. `min(...)` caps at the
 * design width on desktop and lets mobile go edge-to-edge without the
 * toggle sliding offscreen behind the drawer.
 */
export const DRAWER_WIDTH_CSS = "min(420px, 100vw)";

/**
 * Only the numeric fields of AurisConfig can be driven by a range slider.
 * Narrowing here (rather than `keyof AurisConfig`) keeps `overrides[key] = value`
 * type-safe: TS knows both sides are `number` for a NumericConfigKey.
 */
type NumericConfigKey = {
  [K in keyof AurisConfig]: AurisConfig[K] extends number ? K : never;
}[keyof AurisConfig];

export interface SliderSpec {
  /** Numeric field name on RiskConfig (backend). */
  key: NumericConfigKey;
  /** Human-readable label shown above the slider. */
  label: string;
  /** One-line explanation shown below the slider. */
  help: string;
  /** Min value in the raw units the backend expects. */
  min: number;
  /** Max value in the raw units the backend expects. */
  max: number;
  /** Slider step. */
  step: number;
  /** Default value; matches the Streamlit sidebar. */
  default: number;
  /** How to render a raw value for a human. */
  format: (v: number) => string;
}

export const SLIDERS: readonly SliderSpec[] = [
  {
    key: "anomaly_quantile",
    label: "Anomaly percentile",
    help: "Flag transactions above this percentile by amount.",
    min: 0.9,
    max: 0.99,
    step: 0.01,
    default: 0.99,
    format: (v) => `${Math.round(v * 100)}%`,
  },
  {
    key: "vendor_frequency_quantile",
    label: "Vendor frequency percentile",
    help: "Flag vendors above this percentile by transaction count.",
    min: 0.9,
    max: 0.99,
    step: 0.01,
    default: 0.95,
    format: (v) => `${Math.round(v * 100)}%`,
  },
  {
    key: "deviation_low_multiplier",
    label: "Amount deviation, low",
    help: "Flag payments below this fraction of a vendor's average.",
    min: 0.0,
    max: 1.0,
    step: 0.05,
    default: 0.1,
    format: (v) => `${v.toFixed(2)}x`,
  },
  {
    key: "deviation_high_multiplier",
    label: "Amount deviation, high",
    help: "Flag payments above this multiple of a vendor's average.",
    min: 1.5,
    max: 5.0,
    step: 0.1,
    default: 3.0,
    format: (v) => `${v.toFixed(1)}x`,
  },
];

/** Values keyed by slider spec, in the raw units the backend expects. */
export type SliderValues = Record<SliderSpec["key"], number>;

export const DEFAULT_SLIDER_VALUES: SliderValues = SLIDERS.reduce(
  (acc, s) => ({ ...acc, [s.key]: s.default }),
  {} as SliderValues,
);

/**
 * Rounded compare — floating-point equality on stepped slider values is
 * flaky (0.1 + 0.2 !== 0.3), so we snap to the nearest step before
 * comparing. Returns true when the value is within half a step of the
 * default.
 */
function isAtDefault(value: number, spec: SliderSpec): boolean {
  return Math.abs(value - spec.default) < spec.step / 2;
}

/** How many sliders diverge from their defaults. Drives the trigger-chip badge. */
export function countOverrides(values: SliderValues): number {
  return SLIDERS.filter((s) => !isAtDefault(values[s.key], s)).length;
}

/**
 * Only send values that actually differ from the defaults. Cuts request
 * payload and, more importantly, keeps the backend's own defaults
 * authoritative where the user hasn't opted out.
 */
export function toOverrides(values: SliderValues): RiskConfigOverrides {
  const overrides: RiskConfigOverrides = {};
  for (const spec of SLIDERS) {
    if (!isAtDefault(values[spec.key], spec)) {
      overrides[spec.key] = values[spec.key];
    }
  }
  return overrides;
}

const STORAGE_KEY = "auris.slider_values.v1";

export function loadSliderValues(): SliderValues {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_SLIDER_VALUES };
    const parsed = JSON.parse(raw) as Partial<SliderValues>;
    // Merge over defaults so a schema drift (someone added a slider) still
    // yields a complete object.
    return { ...DEFAULT_SLIDER_VALUES, ...parsed };
  } catch {
    return { ...DEFAULT_SLIDER_VALUES };
  }
}

export function saveSliderValues(values: SliderValues): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(values));
  } catch {
    // Private-browsing quotas can throw; a lost persistence write is not
    // a user-facing failure.
  }
}
