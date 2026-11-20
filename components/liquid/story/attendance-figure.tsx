"use client";

import { StoryFigure } from "@/components/story/story-figure";
import { pct, pointsLabel } from "@/lib/liquid/format";
import { levelKey } from "@/lib/liquid/story-types";
import { SEQUENTIAL, seriesColor } from "@/lib/story/palette";

import { DialChart, DialLegend, type DialSeries } from "./dial-chart";
import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

const percent = (value: number) => `${Number.isInteger(value) ? value : value.toFixed(1)}%`;

/**
 * §8, delegates who don't show up: the benchmark's Figure 2. How often the
 * people deciding for others vote, liquid's lead with them at their own rate
 * against every delegate always voting, and what each floor adds.
 */
export function AttendanceFigure() {
  const { measures, results, city } = useStoryData();
  const { levels } = useTurnout();
  const frontier = (floor: number) =>
    levels.map((l) => results.levels[levelKey(l)].frontier.find((f) => f.floor === floor)?.estimate ?? null);
  const own = frontier(0);
  const always = frontier(1);
  const office = frontier(city.design.office_rate);

  const attendance: DialSeries[] = [
    {
      key: "attendance",
      label: "Liquid: whoever holds a vote votes",
      color: seriesColor(0),
      values: levels.map((l) => 100 * (measures.levels[levelKey(l)].liquid.resolver_attendance ?? 0)),
    },
  ];
  const lead: DialSeries[] = [
    { key: "own", label: "Delegates at their own rate", color: seriesColor(0), values: own.map((v) => (v === null ? null : 100 * v)) },
    {
      key: "always",
      label: "Every delegate always votes",
      color: SEQUENTIAL[700],
      dashed: true,
      values: always.map((v) => (v === null ? null : 100 * v)),
    },
  ];
  const added: DialSeries[] = [
    {
      key: "always",
      label: "Floor 1: every delegate always votes",
      color: SEQUENTIAL[700],
      values: always.map((v, i) => (v === null || own[i] === null ? null : 100 * (v - (own[i] as number)))),
    },
    {
      key: "office",
      label: `Floor ${city.design.office_rate}: the office-holder rate`,
      color: SEQUENTIAL[300],
      values: office.map((v, i) => (v === null || own[i] === null ? null : 100 * (v - (own[i] as number)))),
    },
  ];

  return (
    <StoryFigure
      title="Delegates who don't show up"
      subtitle={`Each delegate votes at the larger of their own rate and a floor; office holders stay at their fixed rate. Means over the ${measures.protocol.cities} primary cities.`}
      source="eval/benchmarks/delegation_frontier_v1 (frontier.csv; measures.csv for attendance)"
      note="Floors from 0.2 to 0.9 add at most 0.3 points at any level and are not drawn; they are in frontier.csv."
      table={{
        caption: "Attendance and the frontier per turnout level",
        columns: [
          { key: "level", label: "Turnout", numeric: true },
          { key: "attendance", label: "Holders vote", numeric: true },
          { key: "own", label: "Lead, own rate", numeric: true },
          { key: "always", label: "Lead, always vote", numeric: true },
        ],
        rows: levels.map((l, i) => ({
          level: l,
          attendance: pct(measures.levels[levelKey(l)].liquid.resolver_attendance ?? 0),
          own: own[i] === null ? "" : pointsLabel(100 * (own[i] as number)),
          always: always[i] === null ? "" : pointsLabel(100 * (always[i] as number)),
        })),
      }}
    >
      <div className="grid gap-8 md:grid-cols-2">
        <div>
          <div className="mb-1 font-sans text-sm font-medium text-story-ink">How often the people deciding for others vote</div>
          <DialLegend series={attendance} />
          <DialChart
            series={attendance}
            yDomain={[80, 100]}
            yTicks={[80, 85, 90, 95, 100]}
            yFormat={percent}
            yLabel="Attendance"
            height={210}
            lines={[{ y: 100 * city.design.office_rate, label: "office holders", dashed: true }]}
            ariaLabel="How often liquid's resolvers vote across the turnout dial"
          />
        </div>
        <div>
          <div className="mb-1 font-sans text-sm font-medium text-story-ink">Liquid minus the representative</div>
          <DialLegend series={lead} />
          <DialChart
            series={lead}
            band={{
              lower: own.map((v) => 100 * (v ?? 0)),
              upper: always.map((v) => 100 * (v ?? 0)),
              color: SEQUENTIAL[400],
            }}
            yDomain={[-12, 20]}
            yTicks={[-10, -5, 0, 5, 10, 15, 20]}
            yFormat={pointsLabel}
            yLabel="Points"
            height={210}
            lines={[{ y: 0 }]}
            ariaLabel="Liquid minus the representative with delegates at their own rate and always voting"
          />
          <p className="mt-1 font-sans text-xs text-story-muted">The shaded gap is the most better attendance could add.</p>
        </div>
      </div>
      <div className="mt-8">
        <div className="mb-1 font-sans text-sm font-medium text-story-ink">What better attendance adds</div>
        <DialLegend series={added} />
        <DialChart
          series={added}
          yDomain={[0, 3.5]}
          yTicks={[0, 1, 2, 3]}
          yFormat={pointsLabel}
          yLabel="Points added"
          height={180}
          ariaLabel="Points added by attendance floors across the turnout dial"
        />
      </div>
      <TurnoutDial className="mt-4 max-w-xl" />
    </StoryFigure>
  );
}
