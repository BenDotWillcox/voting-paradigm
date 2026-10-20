/**
 * Every House size from today's 435 seats to the 30,000-person benchmark,
 * from the 2020 apportionment populations of the 50 states: seats per
 * state, both gaps at each size, and the claims for the next seat. One
 * module for the essay and the explorer, so the two can't disagree; the
 * sweep and the named sizes are parity-checked against the Python build
 * (scripts/check-apportionment-parity.mjs).
 */

import {
  SWEEP_START,
  SWEEP_STOP,
  awardOrder,
  seatsAtSize,
  sizeSweep,
  type SizeSpread,
} from "@/lib/apportionment-sweep";
import { ARTICLE_ONE_MAX_SEATS, CUBE_ROOT_SEATS, WYOMING_RULE_SEATS } from "@/lib/districting-cap-scale";
import { US_2020_APPORTIONMENT_POPULATIONS as POPULATIONS } from "@/lib/us-state-populations";

export { SWEEP_START, SWEEP_STOP };
export type { SizeSpread };

const STATES = Object.keys(POPULATIONS).sort();
export const TOTAL_POPULATION = STATES.reduce((sum, fips) => sum + POPULATIONS[fips], 0);
const SMALLEST = Math.min(...STATES.map((fips) => POPULATIONS[fips]));
const formatInt = (n: number) => n.toLocaleString("en-US");

export interface NamedSize {
  size: number;
  label: string;
  /** How the size is arrived at, in one sentence. */
  rule: string;
}

/** The House sizes the essay stops at, with the rule behind each. */
export const NAMED_SIZES: readonly NamedSize[] = [
  {
    size: SWEEP_START,
    label: "Today’s House",
    rule: "Reached under the 1911 act, and kept by the 1929 act as “the then existing number.”",
  },
  {
    size: WYOMING_RULE_SEATS,
    label: "The Wyoming Rule",
    rule: `Seats enough that the average equals the smallest state’s population: ${formatInt(TOTAL_POPULATION)} ÷ ${formatInt(SMALLEST)}.`,
  },
  {
    size: CUBE_ROOT_SEATS,
    label: "The cube-root rule",
    rule: `The cube root of the population, ∛${formatInt(TOTAL_POPULATION)}: the size the cube-root law predicts for a country this large.`,
  },
  { size: 1000, label: "A round thousand", rule: "A round number between the proposals and the benchmark." },
  {
    size: ARTICLE_ONE_MAX_SEATS,
    label: "The 30,000-person benchmark",
    rule: "The Constitution’s cap of one representative per 30,000 people, read as a national ratio.",
  },
];

/** A member's salary and the average Members' Representational Allowance (CRS, 2026). */
export const MEMBER_SALARY = 174_000;
export const MEMBER_ALLOWANCE = 1_928_107;
export const COST_PER_MEMBER = MEMBER_SALARY + MEMBER_ALLOWANCE;

let cache: { order: string[]; sweep: SizeSpread[] } | null = null;
/**
 * Every House size from 435 to 11,036 (computed once, on first use): the
 * award order and both gaps at each size. Matches house-sizes.json exactly.
 */
export function sweepData(): { order: string[]; sweep: SizeSpread[] } {
  if (!cache) {
    const order = awardOrder(POPULATIONS, SWEEP_STOP);
    cache = { order, sweep: sizeSweep(POPULATIONS, order, SWEEP_START, SWEEP_STOP) };
  }
  return cache;
}

/** Keep a House size inside the sweep, as a whole number of seats. */
export function clampSize(size: number): number {
  return Math.max(SWEEP_START, Math.min(SWEEP_STOP, Math.round(size)));
}

export function spreadAt(size: number): SizeSpread {
  return sweepData().sweep[size - SWEEP_START];
}

export function seatsFor(size: number): Record<string, number> {
  return seatsAtSize(POPULATIONS, sweepData().order, size);
}

/** People per seat on average across the country at a House size. */
export function averageAt(size: number): number {
  return TOTAL_POPULATION / size;
}

/** A state's claim to its `seat`-th seat (the Census Bureau's priority value). */
export function claimFor(population: number, seat: number): number {
  return population / Math.sqrt(seat * (seat - 1));
}

export interface Claim {
  fips: string;
  /** The seat claimed: which of the state's seats it would be. */
  seat: number;
  priority: number;
}

/** The claim that won House seat `size` (51 or more). */
export function winningClaim(size: number): Claim {
  const fips = sweepData().order[size - STATES.length - 1];
  const seat = seatsFor(size)[fips];
  return { fips, seat, priority: claimFor(POPULATIONS[fips], seat) };
}

/**
 * Every state's claim to its next seat once `size` seats are dealt,
 * strongest first: the first wins seat `size + 1`. Ties go to the lower
 * FIPS code, as in the award order.
 */
export function nextClaims(size: number): Claim[] {
  const seats = seatsFor(size);
  return STATES.map((fips) => ({ fips, seat: seats[fips] + 1, priority: claimFor(POPULATIONS[fips], seats[fips] + 1) })).sort(
    (a, b) => b.priority - a.priority || (a.fips < b.fips ? -1 : 1)
  );
}

/**
 * The House size at which a state wins its `seat`-th seat (2 or more), or
 * null past the benchmark.
 */
export function sizeForSeat(fips: string, seat: number): number | null {
  const { order } = sweepData();
  let held = 1;
  for (let i = 0; i < order.length; i++) {
    if (order[i] !== fips) continue;
    held += 1;
    if (held === seat) return STATES.length + 1 + i;
  }
  return null;
}
