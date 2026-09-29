/**
 * Chart color roles for story figures, as CSS custom properties defined on
 * `.story` in app/globals.css. SVG marks use these directly; canvas code
 * must resolve them with getComputedStyle.
 *
 * Categorical slots are assigned in fixed order and never cycled: a ninth
 * series folds into "Other" or small multiples. Color follows the entity,
 * never its rank. Text never wears a series color.
 */

export const SERIES_SLOTS = 8;

export function seriesColor(slot: number): string {
  if (!Number.isInteger(slot) || slot < 0 || slot >= SERIES_SLOTS) {
    throw new RangeError(
      `Series slot ${slot} is out of range; fold extra series into "Other" or facet.`
    );
  }
  return `var(--story-series-${slot + 1})`;
}

/** Single-hue sequential ramp (blue), light to dark. */
export const SEQUENTIAL = {
  100: "var(--story-seq-100)",
  200: "var(--story-seq-200)",
  300: "var(--story-seq-300)",
  400: "var(--story-seq-400)",
  500: "var(--story-seq-500)",
  600: "var(--story-seq-600)",
  700: "var(--story-seq-700)",
} as const;

/** Diverging poles with a neutral gray midpoint. */
export const DIVERGING = {
  negative: "var(--story-div-neg)",
  midpoint: "var(--story-div-mid)",
  positive: "var(--story-div-pos)",
} as const;

/** Chart chrome and ink roles. */
export const INK = {
  primary: "var(--story-ink)",
  secondary: "var(--story-ink-2)",
  muted: "var(--story-muted)",
  grid: "var(--story-grid)",
  axis: "var(--story-axis)",
  surface: "var(--story-surface)",
} as const;
