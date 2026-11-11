import type { ScalarBallotState, ScalarPreviewResponse } from "@/types/expressive-scalar";

export type ScalarGraphRange = { minimum: number; maximum: number };
export const SCALAR_DOMAIN: ScalarGraphRange = { minimum: 0, maximum: 100 };
const DOMAIN_MIN = SCALAR_DOMAIN.minimum;
const DOMAIN_MAX = SCALAR_DOMAIN.maximum;

export function scalarFocusRange(ideal: number): ScalarGraphRange {
  if (!isPolicyValue(ideal)) throw new RangeError("The focus rate must lie between 0 and 100.");
  return { minimum: Math.max(DOMAIN_MIN, Math.floor(ideal - 5)), maximum: Math.min(DOMAIN_MAX, Math.ceil(ideal + 5)) };
}

function validateRange(range: ScalarGraphRange): void {
  if (!isPolicyValue(range.minimum) || !isPolicyValue(range.maximum) || range.minimum >= range.maximum) {
    throw new RangeError("A graph range must increase within 0–100.");
  }
}

/** Include the exact viewport endpoints and evenly spaced, readable interior ticks. */
export function scalarGraphTicks(range: ScalarGraphRange, narrow = false): number[] {
  validateRange(range);
  const span = range.maximum - range.minimum;
  const target = span / (narrow ? 3 : 5);
  const step = [1, 2, 2.5, 5, 10, 20, 25, 50].find((value) => value >= target) ?? 50;
  const ticks = [range.minimum];
  for (let value = Math.ceil(range.minimum / step) * step; value < range.maximum; value += step) {
    if (value - range.minimum >= step * 0.45 && range.maximum - value >= step * 0.45) ticks.push(value);
  }
  ticks.push(range.maximum);
  return ticks;
}

/** Keep tick values stable while their positions follow the animated viewport. */
export function scalarTransitionTicks(from: ScalarGraphRange, target: ScalarGraphRange, progress: number, narrow = false): { value: number; opacity: number }[] {
  const oldTicks = new Set(scalarGraphTicks(from, narrow));
  const newTicks = new Set(scalarGraphTicks(target, narrow));
  return [...new Set([...oldTicks, ...newTicks])].sort((a, b) => a - b).map((value) => ({
    value,
    opacity: oldTicks.has(value) && newTicks.has(value) ? 1 : newTicks.has(value) ? progress : 1 - progress,
  }));
}

function isPolicyValue(value: number): boolean {
  return Number.isFinite(value) && value >= DOMAIN_MIN && value <= DOMAIN_MAX;
}

function validateBallot(ballot: ScalarBallotState): void {
  if (
    !isPolicyValue(ballot.ideal) ||
    !isPolicyValue(ballot.approval_min) ||
    !isPolicyValue(ballot.approval_max) ||
    ballot.approval_min > ballot.ideal || ballot.ideal > ballot.approval_max ||
    !Number.isFinite(ballot.lower_half_width) || ballot.lower_half_width <= 0 || ballot.lower_half_width > DOMAIN_MAX ||
    !Number.isFinite(ballot.upper_half_width) || ballot.upper_half_width <= 0 || ballot.upper_half_width > DOMAIN_MAX
  ) throw new RangeError("A scalar ballot needs an ideal inside its 0–100 approval interval and positive half-widths at most 100.");
}

/**
 * Presentation-only mirror of expressive.scalar.scalar_unclipped_score.
 * Python remains the domain/API reference. Cross-language tests compare the
 * actual Python evaluator against every sampled point and probe below.
 */
function unclippedPresentationScore(ballot: ScalarBallotState, value: number): number {
  const delta = value - ballot.ideal;
  const width = delta < 0 ? ballot.lower_half_width : ballot.upper_half_width;
  const ratio = Math.abs(delta) / width;
  return ratio > 40 ? 0 : Math.exp(-Math.LN2 * ratio * ratio);
}

function presentationProbe(ballot: ScalarBallotState, value: number): ScalarPreviewResponse["probe"] {
  const approved = value >= ballot.approval_min && value <= ballot.approval_max;
  return { value, score: approved ? unclippedPresentationScore(ballot, value) : 0, approved };
}

/** Immediate continuous graph readout; no rounding, transport, or interpolation. */
export function scalarPresentationScore(
  ballot: ScalarBallotState,
  value: number,
): ScalarPreviewResponse["probe"] {
  validateBallot(ballot);
  if (!isPolicyValue(value)) throw new RangeError("The inspected rate must lie between 0 and 100.");
  return presentationProbe(ballot, value);
}

/**
 * Sample the current presentation synchronously, including exact clipping and
 * control landmarks. Ideal-relative samples keep narrow tapers smooth as their
 * peak moves across the visible grid. Rendering density is independent of the
 * API payload; the underlying function and model version are the same.
 */
export function scalarPresentationPreview(ballot: ScalarBallotState, range: ScalarGraphRange = SCALAR_DOMAIN): ScalarPreviewResponse {
  validateBallot(ballot);
  validateRange(range);
  if (!isPolicyValue(ballot.probe)) throw new RangeError("The inspected rate must lie between 0 and 100.");
  // A fixed rendering budget keeps full-range manipulation as light as a close-up.
  // Exact landmarks and ideal-relative samples preserve very narrow peaks.
  const values = new Set(Array.from({ length: 321 }, (_, index) => range.minimum + (range.maximum - range.minimum) * index / 320));
  const addVisible = (value: number) => { if (value >= range.minimum && value <= range.maximum) values.add(value); };
  [ballot.ideal, ballot.approval_min, ballot.approval_max, ballot.probe].forEach(addVisible);
  for (let step = 1; step <= 32; step += 1) {
    const lower = ballot.ideal - ballot.lower_half_width * step / 8;
    const upper = ballot.ideal + ballot.upper_half_width * step / 8;
    addVisible(lower);
    addVisible(upper);
  }
  return {
    model: "clipped-asymmetric-gaussian-v2",
    points: [...values].sort((a, b) => a - b).map((value) => ({
      value,
      unclipped_score: unclippedPresentationScore(ballot, value),
    })),
    probe: presentationProbe(ballot, ballot.probe),
  };
}

/**
 * Keep the true half-value location separate from an edge control's display location.
 * A half-width may extend beyond the feasible policy domain; clamping its handle
 * must not shrink that width or suggest the boundary itself has utility 0.5.
 */
export function taperAnchor(
  ideal: number,
  width: number,
  direction: "lower" | "upper",
): { value: number; displayValue: number; offScale: boolean } {
  if (
    !isPolicyValue(ideal) ||
    !Number.isFinite(width) || width <= 0 || width > DOMAIN_MAX ||
    (direction !== "lower" && direction !== "upper")
  ) throw new RangeError("Taper anchors require an ideal in 0–100 and a positive half-width at most 100.");
  const value = ideal + (direction === "lower" ? -width : width);
  return {
    value,
    displayValue: Math.max(DOMAIN_MIN, Math.min(DOMAIN_MAX, value)),
    offScale: value < DOMAIN_MIN || value > DOMAIN_MAX,
  };
}

export type TaperRailBounds = { left: number; right: number; top: number; bottom: number; minimum?: number; maximum?: number };
export const TAPER_RAIL_TOP_INSET = 24;
type TaperDirection = "lower" | "upper";
type RailPoint = { x: number; y: number };
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));

function railGeometry(ideal: number, direction: TaperDirection, bounds: TaperRailBounds) {
  const minimum = bounds.minimum ?? DOMAIN_MIN;
  const maximum = bounds.maximum ?? DOMAIN_MAX;
  validateRange({ minimum, maximum });
  const span = maximum - minimum;
  const plotWidth = bounds.right - bounds.left;
  const halfHeight = (bounds.bottom - bounds.top) / 2;
  const railHeight = halfHeight - TAPER_RAIL_TOP_INSET;
  if (
    !isPolicyValue(ideal) || (direction !== "lower" && direction !== "upper") ||
    !Object.values(bounds).every(Number.isFinite) ||
    !Number.isFinite(plotWidth) || plotWidth <= 0 ||
    !Number.isFinite(railHeight) || railHeight <= 0
  ) throw new RangeError("Taper rails require an ideal in 0–100, a positive plot width, and plot height greater than 48.");
  return {
    plotWidth,
    span,
    railHeight,
    middleY: bounds.top + halfHeight,
    idealX: bounds.left + plotWidth * ((ideal - minimum) / span),
    distance: Math.max(0, direction === "lower" ? ideal - minimum : maximum - ideal),
    sign: direction === "lower" ? -1 : 1,
  };
}

/**
 * A taper control follows its half-value point horizontally, then travels up
 * the domain edge for the remaining width. A fixed vertical distance per unit
 * of overflow stays continuous as the ideal moves to either domain endpoint.
 * The rail stops 24 pixels below the top to separate its hit target from the peak.
 * Vertical travel is a control rail, not the curve's value at that edge.
 * Width zero is a geometric endpoint only.
 */
export function taperRailPoint(
  ideal: number,
  width: number,
  direction: TaperDirection,
  bounds: TaperRailBounds,
): RailPoint & { offScale: boolean } {
  const rail = railGeometry(ideal, direction, bounds);
  if (!isPolicyValue(width)) throw new RangeError("A taper rail width must lie between 0 and 100.");
  const offScale = width > rail.distance;
  return {
    x: width >= rail.distance
      ? (direction === "lower" ? bounds.left : bounds.right)
      : rail.idealX + rail.sign * rail.plotWidth * (width / rail.span),
    y: offScale
      ? rail.middleY - rail.railHeight * ((width - rail.distance) / DOMAIN_MAX)
      : rail.middleY,
    offScale,
  };
}

/**
 * Continuous inverse extension of the L-shaped control rail. Capped horizontal
 * progress and upward overflow add together, avoiding the discontinuous inside-
 * corner switch of nearest-segment projection. Exact rail points round-trip,
 * including when the ideal is on an edge. Callers apply their own minimum width.
 */
export function taperRailWidth(
  ideal: number,
  direction: TaperDirection,
  pointer: RailPoint,
  bounds: TaperRailBounds,
): number {
  const rail = railGeometry(ideal, direction, bounds);
  if (!Number.isFinite(pointer.x) || !Number.isFinite(pointer.y)) {
    throw new RangeError("A taper rail pointer needs finite coordinates.");
  }
  const horizontal = clamp(rail.sign * ((pointer.x - rail.idealX) / rail.plotWidth) * rail.span, 0, rail.distance);
  const vertical = clamp((rail.middleY - pointer.y) / rail.railHeight, 0, 1);
  return clamp(horizontal + vertical * DOMAIN_MAX, 0, DOMAIN_MAX);
}
