/**
 * District-size inequality at every House size, for the essay's "just add
 * seats?" act. Mirror of `apportionment/analysis.py` (`award_order` and
 * `house_size_sweep`); `scripts/check-apportionment-parity.mjs` fails if the
 * award order or the ratio and median deviation at any size from 435 to
 * 11,036 drift from the build's `house-sizes.json`.
 */

/** The House sizes the essay sweeps: today's House to Article I's limit. */
export const SWEEP_START = 435;
export const SWEEP_STOP = 11_036;

/**
 * The state receiving each seat after every state's guaranteed first seat:
 * element i is the recipient of seat (state count + 1 + i). Ties go to the
 * lower FIPS code, as in the Python heap.
 */
export function awardOrder(populations: Readonly<Record<string, number>>, stop: number): string[] {
  const states = Object.keys(populations).sort();
  const seats = new Map(states.map((fips) => [fips, 1]));
  const order: string[] = [];
  for (let size = states.length + 1; size <= stop; size++) {
    let best = states[0];
    let bestPriority = -1;
    for (const fips of states) {
      const n = seats.get(fips) ?? 1;
      const priority = populations[fips] / Math.sqrt(n * (n + 1));
      if (priority > bestPriority) {
        best = fips;
        bestPriority = priority;
      }
    }
    seats.set(best, (seats.get(best) ?? 1) + 1);
    order.push(best);
  }
  return order;
}

/** Seats per state at `size`, from a prefix of the award order. */
export function seatsAtSize(
  populations: Readonly<Record<string, number>>,
  order: readonly string[],
  size: number
): Record<string, number> {
  const seats: Record<string, number> = {};
  for (const fips of Object.keys(populations)) seats[fips] = 1;
  for (const fips of order.slice(0, size - Object.keys(populations).length)) seats[fips] += 1;
  return seats;
}

export interface SizeSpread {
  size: number;
  largest: { fips: string; seats: number; perSeat: number };
  smallest: { fips: string; seats: number; perSeat: number };
  /** Largest people per seat divided by smallest. */
  ratio: number;
  /** The largest and smallest as shares from the national average (0.3 = 30% above). */
  high: number;
  low: number;
  /** Median over states of |people per seat / national average − 1|. */
  typical: number;
}

/** Inequality at every House size from `start` to `stop`. */
export function sizeSweep(
  populations: Readonly<Record<string, number>>,
  order: readonly string[],
  start: number,
  stop: number
): SizeSpread[] {
  const states = Object.keys(populations).sort();
  const total = states.reduce((sum, fips) => sum + populations[fips], 0);
  const seats = seatsAtSize(populations, order, start);
  const results: SizeSpread[] = [];
  for (let size = start; size <= stop; size++) {
    if (size > start) seats[order[size - states.length - 1]] += 1;
    const average = total / size;
    let largest = states[0];
    let smallest = states[0];
    const deviations: number[] = [];
    for (const fips of states) {
      const perSeat = populations[fips] / seats[fips];
      // Ties go to the higher FIPS code, as Python's max/min over (value, fips).
      const top = populations[largest] / seats[largest];
      const bottom = populations[smallest] / seats[smallest];
      if (perSeat > top || (perSeat === top && fips > largest)) largest = fips;
      if (perSeat < bottom || (perSeat === bottom && fips < smallest)) smallest = fips;
      deviations.push(Math.abs(perSeat / average - 1));
    }
    deviations.sort((a, b) => a - b);
    const mid = deviations.length / 2;
    const typical =
      deviations.length % 2 === 0 ? (deviations[mid - 1] + deviations[mid]) / 2 : deviations[Math.floor(mid)];
    const high = populations[largest] / seats[largest];
    const low = populations[smallest] / seats[smallest];
    results.push({
      size,
      largest: { fips: largest, seats: seats[largest], perSeat: high },
      smallest: { fips: smallest, seats: seats[smallest], perSeat: low },
      ratio: high / low,
      high: high / average - 1,
      low: low / average - 1,
      typical,
    });
  }
  return results;
}
