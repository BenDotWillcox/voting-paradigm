"use client";

import * as React from "react";

import { StoryFigure } from "@/components/story/story-figure";
import { pct } from "@/lib/liquid/format";
import {
  ARRANGEMENT_LABEL,
  topicLabel,
  type Arrangement,
  type BallotCode,
} from "@/lib/liquid/story-types";
import { cn } from "@/lib/utils";

import { BallotTooltip } from "./ballot-text";
import { BallotLegend, CityDots, OUTCOME_COLOR, ballotLook, tally } from "./city-dots";
import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

/** What the reader can show the city under, in the order the text takes them. */
const SHOWN: readonly Arrangement[] = ["full_turnout", "direct", "representative", "liquid"];
const STRIPS: readonly Arrangement[] = ["direct", "representative", "liquid"];

/**
 * §0, three ways to be represented. Strips give the average resident's three
 * shares over the 200 cities; the city below shows one real city on one
 * question, under the arrangement the reader picks.
 */
export function ThreeWaysFigure() {
  const { measures, city } = useStoryData();
  const { key, level, swiss } = useTurnout();
  const [shown, setShown] = React.useState<Arrangement>("direct");
  const codes = city.levels[key].codes[shown];
  const looks = React.useMemo(() => Array.from(codes, (code) => ballotLook(code as BallotCode)), [codes]);
  const counts = tally(codes);
  const shares = measures.levels[key];

  return (
    <StoryFigure
      title={`${level === swiss ? "Swiss turnout" : "Turnout"} ${level}: ${ARRANGEMENT_LABEL[shown].toLowerCase()}`}
      subtitle={
        <>
          The bars: an average resident&apos;s {city.design.topics * city.design.evaluation_per_topic} scored
          questions, over {measures.protocol.cities} cities. The dots: one city&apos;s residents on one question
          ({topicLabel(city.topics[city.question.topic])}).
        </>
      }
      source="eval/benchmarks/delegation_frontier_v1 (bars); primary city 1, recomputed with the frozen code (dots)"
      table={{
        caption: `Shares of an average resident's questions at turnout ${level}`,
        columns: [
          { key: "arrangement", label: "Arrangement" },
          { key: "match", label: "Ballot matches them", numeric: true },
          { key: "contrary", label: "Ballot against them", numeric: true },
          { key: "none", label: "No ballot", numeric: true },
        ],
        rows: STRIPS.map((name) => {
          const m = shares[name];
          return {
            arrangement: ARRANGEMENT_LABEL[name],
            match: pct(m.fidelity),
            contrary: pct(m.contrary_share),
            none: pct(m.none_share),
          };
        }),
      }}
    >
      <div role="group" aria-label="Show the city under" className="mb-4 flex flex-wrap gap-1.5 font-sans text-xs">
        {SHOWN.map((name) => (
          <button
            key={name}
            type="button"
            aria-pressed={name === shown}
            onClick={() => setShown(name)}
            className={cn(
              "rounded-md px-2.5 py-1 ring-1 ring-story-rule",
              name === shown ? "bg-story-ink font-medium text-story-page" : "text-story-ink-2 hover:text-story-ink"
            )}
          >
            {ARRANGEMENT_LABEL[name]}
          </button>
        ))}
      </div>
      <div className="space-y-2">
        {STRIPS.map((name) => {
          const m = shares[name];
          const active = name === shown;
          return (
            <div
              key={name}
              className={cn(
                "grid grid-cols-[8.5rem_minmax(0,1fr)] items-center gap-3 font-sans text-xs",
                active || shown === "full_turnout" ? "opacity-100" : "opacity-40"
              )}
            >
              <span className={cn("text-story-ink-2", active && "font-semibold text-story-ink")}>
                {ARRANGEMENT_LABEL[name]}
              </span>
              <div>
                <div className="flex h-3.5 gap-[2px] overflow-hidden rounded-[3px]" aria-hidden="true">
                  <Segment share={m.fidelity} color={OUTCOME_COLOR.match} />
                  <Segment share={m.contrary_share} color={OUTCOME_COLOR.contrary} />
                  <Segment share={m.none_share} color={OUTCOME_COLOR.none} />
                </div>
                <div className="mt-0.5 flex justify-between text-[0.7rem] text-story-muted tabular-nums">
                  <span>{pct(m.fidelity)} match</span>
                  <span>
                    {pct(m.contrary_share)} against · {pct(m.none_share)} none
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-5">
        <CityDots
          city={city}
          looks={looks}
          markRepresentatives={shown === "representative"}
          ariaLabel={`One city's ${city.design.residents} residents under ${ARRANGEMENT_LABEL[shown].toLowerCase()}: ${counts.match} ballots match their resident, ${counts.contrary} are against them, ${counts.none} residents have no ballot.`}
          tooltip={(voter) => <BallotTooltip city={city} levelKey={key} arrangement={shown} voter={voter} />}
        />
        <p className="mt-2 font-sans text-xs text-story-ink-2 tabular-nums">
          On this question: {counts.match} match, {counts.contrary} against, {counts.none} no ballot
          {shown === "representative" ? ". Ringed: each district's representative." : "."}
        </p>
        <BallotLegend className="mt-2" compact />
      </div>
      <TurnoutDial className="mt-4" />
    </StoryFigure>
  );
}

function Segment({ share, color }: { share: number; color: string }) {
  // Direct voting never casts a contrary ballot: no empty segment for it
  if (share < 0.0005) return null;
  return (
    <span className="h-full" style={{ width: `${share * 100}%`, background: color }} />
  );
}
