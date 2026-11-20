"use client";

import type { Arrangement, ArrangementMeasures, CityLevel } from "@/lib/liquid/story-types";

import { useStoryData } from "./story-data";
import { useTurnout } from "./turnout";

/**
 * What a figure is showing: a turnout level of the frozen benchmark, or the
 * everyone-votes reference point (exploratory) where the provider holds it.
 * Figures read their shares and the city through this, so one figure serves
 * both the story's first parts and the dial.
 */
export interface Setting {
  everyone: boolean;
  /** "Everyone votes", "Swiss turnout 0.45" or "Turnout 0.2". */
  label: string;
  /** Each arrangement's measures, averaged over the 200 primary cities. */
  shares: Record<Arrangement, ArrangementMeasures>;
  /** The illustrative city in this setting. */
  city: CityLevel;
  /** A resident's own turnout rate, in thousandths. */
  turnoutOf: (voter: number) => number;
  /** Where the shares come from, for a figure's source line. */
  source: string;
}

export function useSetting(): Setting {
  const { measures, exploratory, city } = useStoryData();
  const { everyone, key, level, swiss } = useTurnout();
  if (everyone) {
    return {
      everyone,
      label: "Everyone votes",
      shares: exploratory.everyone_votes.measures,
      city: city.everyone,
      turnoutOf: () => 1000,
      source: "eval/benchmarks/delegation_everyone_votes_v1 (exploratory)",
    };
  }
  return {
    everyone,
    label: `${level === swiss ? "Swiss turnout" : "Turnout"} ${level}`,
    shares: measures.levels[key],
    city: city.levels[key],
    turnoutOf: (voter) => city.turnout[key][voter],
    source: "eval/benchmarks/delegation_frontier_v1",
  };
}
