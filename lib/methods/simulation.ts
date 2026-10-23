/**
 * Reading the methods simulation's summary (public/data/methods/simulation.json,
 * written by python -m eval.run_methods_simulation). Display only.
 */

import type { SimulationGroup, SimulationRate, VotingMethod } from "@/types/methods";

/** Column-width names for the disagreement matrix. */
export const SHORT_LABELS: Record<VotingMethod, string> = {
  plurality: "Plur.",
  irv: "IRV",
  borda: "Borda",
  ranked_pairs: "RP",
  approval: "Appr.",
  score: "Score",
  quadratic: "QV",
};

export function disagreement(group: SimulationGroup, a: VotingMethod, b: VotingMethod): SimulationRate | null {
  return group.disagreement.find((d) => (d.a === a && d.b === b) || (d.a === b && d.b === a)) ?? null;
}

/** A rate as a percentage, e.g. "84.0%". */
export function percent(rate: SimulationRate, digits = 1): string {
  return rate.rate === null ? "–" : `${(rate.rate * 100).toFixed(digits)}%`;
}

/** A rate with its interval, e.g. "84.0% (83.3–84.7)". */
export function withInterval(rate: SimulationRate, digits = 1): string {
  const [low, high] = rate.interval;
  return `${percent(rate, digits)} (${(low * 100).toFixed(digits)}–${(high * 100).toFixed(digits)})`;
}
