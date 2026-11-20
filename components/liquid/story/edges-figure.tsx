"use client";

import * as React from "react";

import { StoryFigure } from "@/components/story/story-figure";
import { pct, resident, district } from "@/lib/liquid/format";
import { levelKey, type ArrangementMeasures } from "@/lib/liquid/story-types";
import { INK, seriesColor } from "@/lib/story/palette";

import { CityDots, type DotLook } from "./city-dots";
import { DialChart, DialLegend, type DialSeries } from "./dial-chart";
import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

/*
 * §6, the two edges. One color per thing across every panel and the city:
 * liquid in the first series color, the representative in the second,
 * residents with an empty record in the third, loops in the fourth.
 */
const LIQUID = seriesColor(0);
const REPRESENTATIVE = seriesColor(1);
const EMPTY = seriesColor(2);
const LOOP = seriesColor(3);

const percent = (value: number) => `${Number.isInteger(value) ? value : value.toFixed(1)}%`;

function Panel({ title, series, ...chart }: { title: string; series: DialSeries[] } & Omit<React.ComponentProps<typeof DialChart>, "series">) {
  return (
    <div>
      <div className="mb-1 font-sans text-sm font-medium text-story-ink">{title}</div>
      <DialLegend series={series} />
      <div className="mt-1">
        <DialChart series={series} {...chart} />
      </div>
    </div>
  );
}

/** Per-level values of one measure for one arrangement, in percent. */
function across(
  levels: readonly number[],
  measures: Record<string, Record<string, ArrangementMeasures>>,
  arrangement: string,
  field: keyof ArrangementMeasures
): Array<number | null> {
  return levels.map((l) => {
    const value = measures[levelKey(l)][arrangement][field];
    return value === null ? null : 100 * value;
  });
}

export function EdgesFigure() {
  const { measures } = useStoryData();
  const { levels } = useTurnout();
  const m = measures.levels;

  const lowEnd: DialSeries[] = [
    { key: "overhead", label: "Liquid's overhead", color: LIQUID, values: across(levels, m, "liquid", "overhead") },
    {
      key: "empty",
      label: "Residents with an empty record",
      color: EMPTY,
      values: across(levels, m, "liquid", "empty_record_share"),
    },
  ];
  const records: DialSeries[] = [
    {
      key: "liquid-light",
      label: "Light record, liquid",
      color: LIQUID,
      values: across(levels, m, "liquid", "light_record_fidelity"),
    },
    {
      key: "rep-light",
      label: "Light record, representative",
      color: REPRESENTATIVE,
      values: across(levels, m, "representative", "light_record_fidelity"),
    },
    {
      key: "liquid-empty",
      label: "Empty record, liquid",
      color: LIQUID,
      dashed: true,
      values: across(levels, m, "liquid", "empty_record_fidelity"),
    },
    {
      key: "rep-empty",
      label: "Empty record, representative",
      color: REPRESENTATIVE,
      dashed: true,
      values: across(levels, m, "representative", "empty_record_fidelity"),
    },
  ];
  const highEnd: DialSeries[] = [
    { key: "overhead", label: "Liquid's overhead", color: LIQUID, values: across(levels, m, "liquid", "overhead") },
    { key: "loops", label: "Pairs on a loop, liquid", color: LOOP, values: across(levels, m, "liquid", "loop_share") },
    {
      key: "proxy-loops",
      label: "Pairs on a loop, personal proxy",
      color: INK.secondary,
      dashed: true,
      values: across(levels, m, "proxy", "loop_share"),
    },
  ];
  const direct: DialSeries[] = [
    { key: "liquid", label: "Liquid delegation", color: LIQUID, values: across(levels, m, "liquid", "fidelity") },
    { key: "direct", label: "Direct voting", color: INK.secondary, values: across(levels, m, "direct", "fidelity") },
  ];

  return (
    <StoryFigure
      title="Why liquid cannot keep its overhead down at either end of the dial"
      subtitle={`Means over the ${measures.protocol.cities} primary cities, at every turnout level. A light record is under 10% of the past questions voted on; an empty record is none.`}
      source="eval/benchmarks/delegation_frontier_v1/measures.csv"
      table={{
        caption: "The two edges, per turnout level",
        columns: [
          { key: "level", label: "Turnout", numeric: true },
          { key: "overhead", label: "Liquid overhead", numeric: true },
          { key: "empty", label: "Empty records", numeric: true },
          { key: "loops", label: "On a loop", numeric: true },
          { key: "emptyFid", label: "Empty-record fidelity (liquid)", numeric: true },
          { key: "lightFid", label: "Light-record fidelity (liquid / rep.)", numeric: true },
          { key: "direct", label: "Direct / liquid fidelity", numeric: true },
        ],
        rows: levels.map((l) => {
          const at = m[levelKey(l)];
          return {
            level: l,
            overhead: pct(at.liquid.overhead),
            empty: pct(at.liquid.empty_record_share ?? 0),
            loops: pct(at.liquid.loop_share ?? 0),
            emptyFid: (at.liquid.empty_record_fidelity ?? 0).toFixed(3),
            lightFid: `${(at.liquid.light_record_fidelity ?? 0).toFixed(3)} / ${(at.representative.light_record_fidelity ?? 0).toFixed(3)}`,
            direct: `${at.direct.fidelity.toFixed(3)} / ${at.liquid.fidelity.toFixed(3)}`,
          };
        }),
      }}
    >
      <div className="grid gap-8 md:grid-cols-2">
        <Panel
          title="Low turnout: the overhead is residents with no record"
          series={lowEnd}
          yDomain={[0, 30]}
          yTicks={[0, 10, 20, 30]}
          yFormat={percent}
          yLabel="Share"
          height={210}
          lines={[{ y: 10, label: "10% cap", dashed: true }]}
          ariaLabel="Liquid's overhead and the share of residents with an empty record across the dial"
        />
        <Panel
          title="…and they are barely represented"
          series={records}
          yDomain={[0, 80]}
          yTicks={[0, 20, 40, 60, 80]}
          yFormat={percent}
          yLabel="Fidelity"
          height={210}
          ariaLabel="Fidelity of residents with light and empty records under liquid and the representative"
        />
        <Panel
          title="High turnout: the overhead is loops"
          series={highEnd}
          yDomain={[0, 30]}
          yTicks={[0, 10, 20, 30]}
          yFormat={percent}
          yLabel="Share"
          height={210}
          lines={[{ y: 10, label: "10% cap", dashed: true }]}
          ariaLabel="Liquid's overhead and its loop share, with the proxy's loop share, across the dial"
        />
        <Panel
          title="…and direct voting passes liquid"
          series={direct}
          yDomain={[0, 100]}
          yTicks={[0, 25, 50, 75, 100]}
          yFormat={percent}
          yLabel="Fidelity"
          height={210}
          ariaLabel="Fidelity of direct voting and liquid delegation across the dial"
        />
      </div>
      <TurnoutDial className="mt-6 max-w-xl" />
    </StoryFigure>
  );
}

/** Why each resident's liquid ballot is or is not their own, by the code in city.json. */
const REASONS = [
  { code: "l", label: "Delegated, but on a loop: decides", look: { color: LOOP, ring: false } },
  { code: "e", label: "Empty record: decides", look: { color: EMPTY, ring: false } },
  { code: "k", label: "No candidate good enough: decides", look: { color: INK.secondary, ring: false } },
  { code: "d", label: "Handed to a delegate", look: { color: INK.empty, ring: true } },
] as const;

/** §6's city: who decides their own question under liquid, and why. */
export function KeepCityFigure() {
  const { city } = useStoryData();
  const { key, level } = useTurnout();
  const reasons = city.levels[key].liquid_reason;
  const looks = React.useMemo<DotLook[]>(
    () => Array.from(reasons, (code) => REASONS.find((r) => r.code === code)?.look ?? REASONS[3].look),
    [reasons]
  );
  const counts = REASONS.map((r) => Array.from(reasons).filter((code) => code === r.code).length);

  return (
    <StoryFigure
      title={`Who decides their own question under liquid, at turnout ${level}`}
      subtitle={`One city's residents on one question. ${counts[0]} decide because their delegation loops back, ${counts[1]} because they have no record, ${counts[2]} because no candidate was good enough.`}
      source="Primary city 1, recomputed with the frozen code"
      table={{
        caption: `Why residents decide their own question at turnout ${level}`,
        columns: [
          { key: "reason", label: "Reason" },
          { key: "residents", label: "Residents", numeric: true },
        ],
        rows: REASONS.map((r, i) => ({ reason: r.label, residents: counts[i] })),
      }}
    >
      <CityDots
        city={city}
        looks={looks}
        ariaLabel={`Residents by why they decide their own question: ${REASONS.map((r, i) => `${counts[i]} ${r.label.toLowerCase()}`).join(", ")}.`}
        tooltip={(voter) => {
          const reason = REASONS.find((r) => r.code === reasons[voter]);
          return (
            <div className="font-sans">
              <div className="font-semibold">
                {resident(voter)} · {district(city.district[voter])}
              </div>
              <div>{reason?.label}</div>
            </div>
          );
        }}
      />
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 font-sans text-xs text-story-ink-2">
        {REASONS.map((r) => (
          <span key={r.code} className="inline-flex items-center gap-1.5">
            <svg width={12} height={12} aria-hidden="true">
              <circle
                cx={6}
                cy={6}
                r={r.look.ring ? 4.2 : 5}
                strokeWidth={r.look.ring ? 2 : 0}
                style={{ fill: r.look.ring ? "transparent" : r.look.color, stroke: r.look.color }}
              />
            </svg>
            {r.label}
          </span>
        ))}
      </div>
      <TurnoutDial className="mt-4 max-w-xl" />
    </StoryFigure>
  );
}
