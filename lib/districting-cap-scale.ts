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

import type { CapAnchor } from "@/types/districting";

/** Inclusive lower bound — current US House size, set by the 1929 cap. */
export const CAP_MIN = 435;
/** Inclusive upper bound — Article I §2 ratio of 1 representative per 30,000. */
export const CAP_MAX = 11_037;

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
    cap: 574,
    label: "Wyoming Rule",
    description:
      "Smallest state's population sets the average district size. " +
      "≈ 331.1M / 576,851 ≈ 574 seats.",
  },
  {
    cap: 692,
    label: "Cube Root",
    description:
      "Cube root of the apportionment population. ∛331.1M ≈ 692. " +
      "An empirical regularity observed across many democracies.",
  },
  {
    cap: 1_000,
    label: "Expanded",
    description:
      "A round-number anchor for orientation between policy proposals " +
      "and the constitutional ceiling.",
  },
  {
    cap: 11_037,
    label: "Article I §2",
    description:
      "One representative per 30,000 people — the original constitutional " +
      "minimum-district-size that the 1929 cap abandoned.",
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
