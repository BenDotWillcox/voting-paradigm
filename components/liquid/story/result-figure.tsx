"use client";

import { StoryFigure } from "@/components/story/story-figure";
import { pct, pointsLabel } from "@/lib/liquid/format";
import { levelKey } from "@/lib/liquid/story-types";
import { DIVERGING, INK, seriesColor } from "@/lib/story/palette";

import { DialChart, DialLegend, type DialSeries } from "./dial-chart";
import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

/**
 * §5, the result: the benchmark's Figure 1. Liquid minus the representative
 * across the dial with its 95% band, the same over only the cities under the
 * cap, and below it the share of cities that keep liquid under the cap.
 */
export function ResultFigure() {
  const { results, measures } = useStoryData();
  const { levels, level } = useTurnout();
  const rows = levels.map((l) => results.levels[levelKey(l)]);
  const { threshold, rules } = results;
  const gate = rules.feasible_share;
  // A level fails the gate where liquid leads but too few cities keep it under the cap
  const fails = (index: number) => rows[index].h1.estimate > 0 && rows[index].cap_share < gate;

  // Where only a few cities are under the cap, the cap-only curve stands apart
  const few = (index: number) => rows[index].h1_cap !== null && rows[index].cap_share < gate;
  // Drawn first, so the all-city curve lies on top where the two coincide
  const curves: DialSeries[] = [
    {
      key: "cap",
      label: "Only cities under the 10% cap",
      color: seriesColor(1),
      dashed: true,
      values: rows.map((r) => (r.h1_cap ? 100 * r.h1_cap.estimate : null)),
      dotsWhere: few,
    },
    { key: "all", label: `All ${measures.protocol.cities} cities`, color: seriesColor(0), values: rows.map((r) => 100 * r.h1.estimate) },
  ];
  const whiskers = rows.flatMap((r, index) =>
    few(index) && r.band_cap ? [{ index, lower: 100 * r.band_cap.lower, upper: 100 * r.band_cap.upper, color: seriesColor(1) }] : []
  );
  const shares: DialSeries[] = [
    {
      key: "share",
      label: "Cities under the cap",
      color: INK.secondary,
      dotsOnly: true,
      values: rows.map((r) => 100 * r.cap_share),
      dotColor: (index) => (fails(index) ? DIVERGING.negative : INK.secondary),
    },
  ];
  const at = results.levels[levelKey(level)];

  return (
    <StoryFigure
      title="Liquid delegation minus the district representative, across the turnout dial"
      subtitle={`Fidelity difference in points, averaged over the ${measures.protocol.cities} primary cities. At turnout ${level}: ${pointsLabel(100 * at.h1.estimate)} points, with ${pct(at.cap_share, at.cap_share === 1 || at.cap_share === 0 ? 0 : 1)} of cities under the cap.`}
      source="eval/benchmarks/delegation_frontier_v1 (levels.csv, thresholds.csv)"
      note={`The band is the simultaneous 95% band. The dashed curve uses only cities whose overhead stays at or under 10%; from 0.3 to 0.8 it lies under the solid one, and where few cities qualify its bar is their 95% band. The test needs at least ${pct(gate, 0)} of cities under the cap wherever liquid leads.`}
      table={{
        caption: "Liquid minus the representative, and the share of cities under the cap, per turnout level",
        columns: [
          { key: "level", label: "Turnout", numeric: true },
          { key: "difference", label: "Difference (points)", numeric: true },
          { key: "band", label: "95% band", numeric: true },
          { key: "share", label: "Cities under cap", numeric: true },
          { key: "reading", label: "Reading" },
        ],
        rows: levels.map((l, i) => ({
          level: l,
          difference: pointsLabel(100 * rows[i].h1.estimate),
          band: `${pointsLabel(100 * rows[i].band.lower)} to ${pointsLabel(100 * rows[i].band.upper)}`,
          share: pct(rows[i].cap_share, 1),
          reading: rows[i].size === rows[i].direction ? rows[i].direction : `${rows[i].direction}, ${rows[i].size}`,
        })),
      }}
    >
      <DialLegend series={[...curves].reverse()} />
      <div className="mt-2">
        <DialChart
          series={curves}
          band={{ lower: rows.map((r) => 100 * r.band.lower), upper: rows.map((r) => 100 * r.band.upper), color: seriesColor(0) }}
          yDomain={[-13, 21]}
          yTicks={[-10, -5, 0, 5, 10, 15, 20]}
          yFormat={pointsLabel}
          yLabel="Points"
          height={300}
          lines={[{ y: 0 }, { y: 100 * rules.delta, label: `δ = ${100 * rules.delta} points`, dashed: true, labelAt: "right" }]}
          shade={{ from: threshold.confidence[0], to: threshold.confidence[1], label: "95% range for\nthe crossing" }}
          marks={[{ x: threshold.crossing, y: 0, label: `overtakes near ${threshold.crossing.toFixed(2)}` }]}
          whiskers={whiskers}
          ariaLabel="Liquid minus the representative across the turnout dial"
        />
      </div>
      <div className="mt-4">
        <div className="mb-1 font-sans text-xs font-medium text-story-ink-2">
          Share of cities keeping liquid&apos;s overhead at or under 10%
        </div>
        <DialChart
          series={shares}
          yDomain={[0, 115]}
          yTicks={[0, 50, 100]}
          yFormat={(v) => `${Number.isInteger(v) ? v : v.toFixed(1)}%`}
          yLabel="Cities"
          height={170}
          lines={[{ y: 100 * gate, label: `${pct(gate, 0)} gate`, dashed: true }]}
          shade={{ from: threshold.confidence[0], to: threshold.confidence[1] }}
          pointLabels={{
            series: "share",
            format: (v) => `${Number.isInteger(v) ? v : v.toFixed(1)}%`,
            // Full shares need no label: the gate line shows them
            where: (v) => v < 100,
          }}
          ariaLabel="Share of cities under the overhead cap across the turnout dial"
        />
      </div>
      <TurnoutDial className="mt-4 max-w-xl" />
    </StoryFigure>
  );
}
