/**
 * Parliament-diagram ("hemicycle") layout: N seats as dots on concentric
 * half-rings. Pure and deterministic, so the same seat count always yields
 * the same picture and animated transitions between counts are stable.
 *
 * Coordinates are normalized to the outer radius: x in [-1, 1] (left to
 * right), y in [0, 1] (baseline up).
 */

export interface SeatSlot {
  x: number;
  y: number;
}

export interface HemicycleLayout {
  /** Seat positions ordered left to right by angle (so blocks form wedges). */
  slots: SeatSlot[];
  /** Dot radius in the same normalized units. */
  dotRadius: number;
  rows: number;
}

/** Inner ring radius as a fraction of the outer radius. */
const INNER = 0.38;

/**
 * Rows are chosen so seat spacing along each arc roughly equals the spacing
 * between rows. With radii evenly spaced from INNER to 1, the total arc length
 * over row spacing gives N ≈ π(1 + k) m(m − 1) / (2(1 − k)) for m rows.
 */
export function hemicycleLayout(seatCount: number): HemicycleLayout {
  const n = Math.max(0, Math.floor(seatCount));
  if (n === 0) return { slots: [], dotRadius: 0, rows: 0 };

  const factor = (2 * (1 - INNER)) / (Math.PI * (1 + INNER));
  const rows = n < 4 ? 1 : Math.max(1, Math.round((1 + Math.sqrt(1 + 4 * factor * n)) / 2));
  const radii =
    rows === 1
      ? [(1 + INNER) / 2]
      : Array.from({ length: rows }, (_, i) => INNER + ((1 - INNER) * i) / (rows - 1));

  // Seats per row proportional to row length, largest remainder to hit n.
  const totalRadius = radii.reduce((sum, r) => sum + r, 0);
  const exact = radii.map((r) => (n * r) / totalRadius);
  const perRow = exact.map(Math.floor);
  let remaining = n - perRow.reduce((sum, count) => sum + count, 0);
  const byRemainder = exact
    .map((value, index) => ({ index, remainder: value - Math.floor(value) }))
    .sort((a, b) => b.remainder - a.remainder || b.index - a.index);
  for (const { index } of byRemainder) {
    if (remaining === 0) break;
    perRow[index] += 1;
    remaining -= 1;
  }

  const placed: Array<SeatSlot & { angle: number; radius: number }> = [];
  radii.forEach((radius, row) => {
    const count = perRow[row];
    for (let j = 0; j < count; j++) {
      const angle = count === 1 ? Math.PI / 2 : Math.PI * (1 - j / (count - 1));
      placed.push({ x: radius * Math.cos(angle), y: radius * Math.sin(angle), angle, radius });
    }
  });
  placed.sort((a, b) => b.angle - a.angle || a.radius - b.radius);

  const rowGap = rows === 1 ? 1 - INNER : (1 - INNER) / (rows - 1);
  const arcGap = Math.min(
    ...radii.map((r, i) => (perRow[i] > 1 ? (Math.PI * r) / (perRow[i] - 1) : Infinity))
  );
  const spacing = Math.min(rowGap, Number.isFinite(arcGap) ? arcGap : rowGap);

  return {
    slots: placed.map(({ x, y }) => ({ x, y })),
    dotRadius: spacing * 0.42,
    rows,
  };
}

export interface SeatDot extends SeatSlot {
  /** Stable identity across layouts: `${fips}-${k}` for a state's k-th seat. */
  key: string;
  fips: string;
}

/**
 * Assign consecutive slots to states in `order`, so each state occupies a
 * contiguous wedge. States with no seats (not yet admitted) are skipped.
 */
export function assignSeats(
  layout: HemicycleLayout,
  order: readonly string[],
  seatsByState: Readonly<Record<string, number>>
): SeatDot[] {
  const dots: SeatDot[] = [];
  let slot = 0;
  for (const fips of order) {
    const count = seatsByState[fips] ?? 0;
    for (let k = 0; k < count; k++) {
      const position = layout.slots[slot++];
      if (!position) {
        throw new Error("Seat counts exceed the layout's slots");
      }
      dots.push({ key: `${fips}-${k}`, fips, x: position.x, y: position.y });
    }
  }
  return dots;
}
