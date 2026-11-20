"use client";

import * as React from "react";

import { StoryFigure } from "@/components/story/story-figure";
import { SEQUENTIAL } from "@/lib/story/palette";

import { CityDots, type DotLook } from "./city-dots";
import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

/** Own turnout rate, binned light to dark (the validated sequential ramp). */
const BINS = [
  { upTo: 200, label: "Under 20%", color: SEQUENTIAL[100] },
  { upTo: 400, label: "20–40%", color: SEQUENTIAL[200] },
  { upTo: 600, label: "40–60%", color: SEQUENTIAL[400] },
  { upTo: 800, label: "60–80%", color: SEQUENTIAL[500] },
  { upTo: 1001, label: "80% or more", color: SEQUENTIAL[700] },
] as const;

function bin(rate: number): number {
  return BINS.findIndex((b) => rate < b.upTo);
}

/**
 * §1: the city's residents by how often they vote themselves. The dial sets
 * the mean; the spread around it is the frozen design's (fitted to Geneva's
 * register), so at every mean some residents almost never vote and some
 * almost always do.
 */
export function TurnoutCity() {
  const { city } = useStoryData();
  const { key, level } = useTurnout();
  const rates = city.turnout[key];
  const looks = React.useMemo<DotLook[]>(
    () => rates.map((rate) => ({ color: BINS[bin(rate)].color, ring: false })),
    [rates]
  );
  const counts = BINS.map((_, index) => rates.filter((rate) => bin(rate) === index).length);
  const rarely = rates.filter((rate) => rate < 100).length;
  const nearlyAlways = rates.filter((rate) => rate >= 900).length;

  return (
    <StoryFigure
      title={`How often each resident votes at mean turnout ${level}`}
      subtitle={`One dot per resident of one city: ${rarely} vote on fewer than one question in ten, ${nearlyAlways} on more than nine in ten.`}
      source="Primary city 1, recomputed with the frozen code; turnout spread fitted to Geneva's register"
      table={{
        caption: `Residents by own turnout rate at mean turnout ${level}`,
        columns: [
          { key: "rate", label: "Votes on" },
          { key: "residents", label: "Residents", numeric: true },
        ],
        rows: BINS.map((b, index) => ({ rate: b.label, residents: counts[index] })),
      }}
    >
      <CityDots
        city={city}
        looks={looks}
        ariaLabel={`Residents by own turnout rate: ${BINS.map((b, i) => `${counts[i]} vote on ${b.label.toLowerCase()} of questions`).join(", ")}.`}
        tooltip={(voter) => (
          <span className="font-sans">
            Resident {voter} votes on {Math.round(rates[voter] / 10)}% of questions
          </span>
        )}
      />
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 font-sans text-xs text-story-ink-2">
        <span>Votes on:</span>
        {BINS.map((b) => (
          <span key={b.label} className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: b.color }} />
            {b.label}
          </span>
        ))}
      </div>
      <TurnoutDial className="mt-4 max-w-xl" />
    </StoryFigure>
  );
}
