import {
  SPECTRUM_SD_MAX,
  SPECTRUM_SD_MIN,
  type AcceptableRange,
  type ReportedUncertainty,
  type SpectrumQuestion,
} from "@/lib/validations/elicitation-schemas";

export type SpectrumDraft = {
  position: number | null;
  reported_uncertainty: ReportedUncertainty | null;
  acceptable_range: AcceptableRange | null;
};

// A preview width only: never added to an answer without participant input.
export const DEFAULT_UNCERTAINTY_SD = 0.15;

// Even the narrowest curve at a scale endpoint remains below this fixed limit.
export const SPECTRUM_DENSITY_MAX = 11;

export function emptySpectrumDraft(): SpectrumDraft {
  return { position: null, reported_uncertainty: null, acceptable_range: null };
}

export function formatSpectrumValue(
  value: number,
  scale: SpectrumQuestion["scale"],
): string {
  if (scale.format === "clock_hour") {
    return `${value % 12 || 12}:00 ${value >= 12 ? "pm" : "am"}`;
  }
  if (scale.unit === "%") return `${value}%`;
  const singularUnits: Record<string, string> = { days: "day", weeks: "week" };
  const unit = value === 1 ? singularUnits[scale.unit] ?? scale.unit : scale.unit;
  return `${value} ${unit}`;
}

export type SpectrumAxisTick = {
  value: number;
  fraction: number;
  label: string | null;
};

/**
 * Preserve the validated scale's step grid; thin only labels, never tick positions.
 * Numeric units belong in the axis caption rather than on every tick.
 */
export function spectrumAxisTicks(
  scale: SpectrumQuestion["scale"],
  plotWidth: number,
): SpectrumAxisTick[] {
  if (!Number.isFinite(plotWidth) || plotWidth < 0) {
    throw new RangeError("Spectrum plot width must be finite and nonnegative.");
  }
  const intervalCount = Math.round((scale.max - scale.min) / scale.step);
  const ticks = Array.from({ length: intervalCount + 1 }, (_, index) => {
    const value = spectrumValueAtFraction(index / intervalCount, scale);
    return {
      value,
      fraction: (value - scale.min) / (scale.max - scale.min),
      label: scale.format === "clock_hour"
        ? `${value % 12 || 12} ${value >= 12 ? "pm" : "am"}`
        : String(value),
    };
  });
  // Approximate compact labels at 12px, with space between neighboring labels.
  const minimumLabelGap = Math.max(44, ...ticks.map((tick) => tick.label.length * 7 + 16));
  const stride = plotWidth === 0
    ? intervalCount
    : Math.max(1, Math.ceil(minimumLabelGap * intervalCount / plotWidth));
  return ticks.map((tick, index) => ({
    ...tick,
    label: index === 0 || index === intervalCount ||
      (index % stride === 0 && (1 - tick.fraction) * plotWidth >= minimumLabelGap)
      ? tick.label
      : null,
  }));
}

export function initialSpectrumPosition(scale: SpectrumQuestion["scale"]): number {
  return spectrumValueAtFraction(0.5, scale);
}

export function formatSpectrumUncertainty(uncertainty: ReportedUncertainty): string {
  return `${Number((uncertainty.sd_fraction * 100).toFixed(1))}% of scale`;
}

function decimalPlaces(value: number): number {
  const [mantissa, exponent = "0"] = value.toString().split("e");
  return Math.max(0, (mantissa.split(".")[1]?.length ?? 0) - Number(exponent));
}

/** Convert pointer position into the exact decimal step values the API accepts. */
export function spectrumValueAtFraction(
  fraction: number,
  scale: SpectrumQuestion["scale"],
): number {
  if (!Number.isFinite(fraction)) throw new RangeError("Spectrum fraction must be finite.");
  const clamped = Math.min(1, Math.max(0, fraction));
  const stepIndex = Math.round(clamped * (scale.max - scale.min) / scale.step);
  const precision = Math.min(100, Math.max(decimalPlaces(scale.min), decimalPlaces(scale.step)));
  const snapped = Number((scale.min + stepIndex * scale.step).toFixed(precision));
  return Math.min(scale.max, Math.max(scale.min, snapped));
}

function quantizedUncertainty(value: number): number {
  return Math.min(SPECTRUM_SD_MAX, Math.max(SPECTRUM_SD_MIN, Number(value.toFixed(3))));
}

/** Match vertical pointer travel to the displayed peak, including at axis ends. */
export function uncertaintyFromVerticalDrag(
  startSd: number,
  deltaY: number,
  graphHeight: number,
  position = 0.5,
): number {
  if (![startSd, deltaY, graphHeight, position].every(Number.isFinite) || graphHeight <= 0 ||
    startSd < SPECTRUM_SD_MIN || startSd > SPECTRUM_SD_MAX || position < 0 || position > 1) {
    throw new RangeError("Uncertainty drag requires a valid width and positive graph height.");
  }
  if (deltaY === 0) return startSd;
  const peakDensity = (sd_fraction: number) => Math.max(
    ...sampleSpectrumCurve(position, { sd_fraction }).map((point) => point.density),
  );
  const targetDensity = peakDensity(startSd) - deltaY / graphHeight * SPECTRUM_DENSITY_MAX;
  if (targetDensity >= peakDensity(SPECTRUM_SD_MIN)) return SPECTRUM_SD_MIN;
  if (targetDensity <= peakDensity(SPECTRUM_SD_MAX)) return SPECTRUM_SD_MAX;
  let lower = SPECTRUM_SD_MIN;
  let upper = SPECTRUM_SD_MAX;
  for (let iteration = 0; iteration < 16; iteration += 1) {
    const midpoint = (lower + upper) / 2;
    if (peakDensity(midpoint) > targetDensity) lower = midpoint;
    else upper = midpoint;
  }
  return quantizedUncertainty((lower + upper) / 2);
}

/** Update only the selected signal; absent acceptance bounds stay absent. */
export function updateSpectrumHandle(
  draft: SpectrumDraft,
  handle: "position" | "uncertainty" | "lower" | "upper",
  value: number,
): SpectrumDraft {
  if (!Number.isFinite(value)) throw new RangeError("Spectrum handle value must be finite.");
  if (handle === "position") return { ...draft, position: value };
  if (handle === "uncertainty") {
    return { ...draft, reported_uncertainty: { sd_fraction: quantizedUncertainty(value) } };
  }
  if (draft.acceptable_range === null) return draft;
  return {
    ...draft,
    acceptable_range: handle === "lower"
      ? { ...draft.acceptable_range, lower: Math.min(value, draft.acceptable_range.upper) }
      : { ...draft.acceptable_range, upper: Math.max(value, draft.acceptable_range.lower) },
  };
}

export type SpectrumCurvePoint = { position: number; density: number };

/** Illustrative Gaussian kernel, normalized only within the question's axis. */
export function sampleSpectrumCurve(
  position: number,
  uncertainty: ReportedUncertainty,
): SpectrumCurvePoint[] {
  if (!Number.isFinite(position) || position < 0 || position > 1) {
    throw new RangeError("Spectrum curve position must lie within [0, 1].");
  }
  const width = uncertainty.sd_fraction;
  if (!Number.isFinite(width) || width < SPECTRUM_SD_MIN || width > SPECTRUM_SD_MAX) {
    throw new RangeError("Spectrum curve width must lie within the illustrative limits.");
  }
  // Include the selected point so the mode never shifts to a sampling neighbor.
  const positions = [...new Set([
    ...Array.from({ length: 257 }, (_, index) => index / 256),
    position,
  ])].sort((a, b) => a - b);
  const points = positions.map((x) => ({
    position: x,
    density: Math.exp(-0.5 * ((x - position) / width) ** 2),
  }));
  let area = 0;
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    area += (current.position - previous.position)
      * (current.density + previous.density) / 2;
  }
  return points.map((point) => ({ ...point, density: point.density / area }));
}

export function spectrumDraftCurve(
  draft: SpectrumDraft,
  scale: SpectrumQuestion["scale"],
): SpectrumCurvePoint[] {
  if (draft.position === null || draft.reported_uncertainty === null) return [];
  return sampleSpectrumCurve(
    (draft.position - scale.min) / (scale.max - scale.min),
    draft.reported_uncertainty,
  );
}
