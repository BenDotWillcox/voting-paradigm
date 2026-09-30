/**
 * House-size cap configuration for the districting demo.
 *
 * Earlier iterations of this module shipped a logarithmic slider scale; we
 * now expose only the discrete educational anchors via a toggle group, so
 * the runtime path only ever has to compute (or precompute) maps at five
 * cap values — not 10,600 of them. The Python API still accepts any
 * integer in [CAP_MIN, CAP_MAX] for flexibility, but the UI deliberately
 * doesn't let users pick something we don't plan to render.
 */

import { US_2020_APPORTIONMENT_POPULATIONS } from "@/lib/us-state-populations";
import type { CapAnchor } from "@/types/districting";

// Rule-defined House sizes are computed from the 2020 apportionment
// populations, never typed in, and mirror apportionment/analysis.py (the
// parity script compares them). Every rule uses apportionment populations
// consistently; mixing in resident populations is how the commonly quoted
// "574" arises.
const POPULATIONS = Object.values(US_2020_APPORTIONMENT_POPULATIONS);
const TOTAL_POPULATION = POPULATIONS.reduce((sum, population) => sum + population, 0);
const SMALLEST_STATE = Math.min(...POPULATIONS);

/** Wyoming Rule: the House whose average district is closest to the smallest state. */
export const WYOMING_RULE_SEATS = Math.round(TOTAL_POPULATION / SMALLEST_STATE);
/** Taagepera's cube-root law. */
export const CUBE_ROOT_SEATS = Math.round(Math.cbrt(TOTAL_POPULATION));
/**
 * Article I §2: "The Number of Representatives shall not exceed one for every
 * thirty Thousand." The largest compliant House rounds down.
 */
export const ARTICLE_ONE_MAX_SEATS = Math.floor(TOTAL_POPULATION / 30_000);

/** Inclusive lower bound — current US House size, set by the 1929 cap. */
export const CAP_MIN = 435;
/** Inclusive upper bound — the largest House Article I §2 allows. */
export const CAP_MAX = ARTICLE_ONE_MAX_SEATS;

const formatInt = (value: number) => value.toLocaleString("en-US");

/**
 * Anchor values shown in the picker.
 *
 * Each anchor is a cap value with educational meaning. Order is the
 * left-to-right rendering order in the toggle group; ascending by cap.
 */
export const CAP_ANCHORS: readonly CapAnchor[] = [
  {
    cap: 435,
    label: "Current",
    description:
      "The current US House size, set by the Reapportionment Act of 1929.",
  },
  {
    cap: WYOMING_RULE_SEATS,
    label: "Wyoming Rule",
    description:
      "Average district size matches the smallest state's population: " +
      `${formatInt(TOTAL_POPULATION)} / ${formatInt(SMALLEST_STATE)} ≈ ` +
      `${formatInt(WYOMING_RULE_SEATS)} seats.`,
  },
  {
    cap: CUBE_ROOT_SEATS,
    label: "Cube Root",
    description:
      `Cube root of the apportionment population: ∛${formatInt(TOTAL_POPULATION)} ≈ ` +
      `${formatInt(CUBE_ROOT_SEATS)}. An empirical regularity across many democracies.`,
  },
  {
    cap: 1_000,
    label: "Expanded",
    description:
      "A round-number anchor for orientation between policy proposals " +
      "and the constitutional ceiling.",
  },
  {
    cap: ARTICLE_ONE_MAX_SEATS,
    label: "Article I §2",
    description:
      "The largest House the Constitution allows, at most one representative " +
      `per 30,000 people: ⌊${formatInt(TOTAL_POPULATION)} / 30,000⌋ = ` +
      `${formatInt(ARTICLE_ONE_MAX_SEATS)} seats.`,
  },
] as const;

/** Set of anchor cap values, for fast membership checks. */
const ANCHOR_CAPS: ReadonlySet<number> = new Set(CAP_ANCHORS.map((a) => a.cap));

/** True iff `cap` is one of the picker's anchor values. */
export function isAnchorCap(cap: number): boolean {
  return ANCHOR_CAPS.has(cap);
}

/**
 * Snap an arbitrary cap value to the nearest anchor.
 *
 * Used to sanitize `?cap=` URL params: if someone deep-links a value that
 * isn't one of the five anchors (or pastes an old slider-era URL), we
 * route them to the closest one rather than 404-ing or showing an empty
 * selection in the toggle group.
 */
export function getNearestAnchor(cap: number): CapAnchor {
  let best = CAP_ANCHORS[0];
  let bestDist = Math.abs(cap - best.cap);
  for (const anchor of CAP_ANCHORS) {
    const dist = Math.abs(cap - anchor.cap);
    if (dist < bestDist) {
      best = anchor;
      bestDist = dist;
    }
  }
  return best;
}
