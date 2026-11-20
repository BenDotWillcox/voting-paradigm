"use client";

import { StoryFigure } from "@/components/story/story-figure";
import { pointsLabel } from "@/lib/liquid/format";
import { levelKey } from "@/lib/liquid/story-types";
import { INK, SEQUENTIAL, seriesColor } from "@/lib/story/palette";

import { DialChart, DialLegend, type DialSeries } from "./dial-chart";
import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

/**
 * A family's settings other than its baseline, in their order along the
 * ordinal ramp. Only its middle steps, so no setting is mistaken for the
 * baseline's ink line at either end (dark ink in light mode, light in dark).
 */
const RAMP: Record<number, string[]> = {
  1: [SEQUENTIAL[400]],
  2: [SEQUENTIAL[200], SEQUENTIAL[500]],
  3: [SEQUENTIAL[200], SEQUENTIAL[300], SEQUENTIAL[500]],
  4: [SEQUENTIAL[200], SEQUENTIAL[300], SEQUENTIAL[400], SEQUENTIAL[500]],
};

/**
 * §9, the sweeps: the benchmark's robustness figure, one panel per family.
 * Each line is liquid minus the representative across the dial for one value
 * of the family's setting; the dark line is the baseline it is compared with.
 * A hollow point is a level where fewer than 95% of cities stay under the cap.
 */
export function SweepsFigure() {
  const { results } = useStoryData();
  const { levels, level } = useTurnout();
  const { panels, points, reference } = results.sweeps;
  const gate = results.rules.feasible_share;
  const cities = points[reference].cities;

  const seriesFor = (panel: (typeof panels)[number]): DialSeries[] => {
    const ramped = panel.series.filter((s) => !s.baseline && s.accent === null);
    const out: DialSeries[] = [];
    // The belief family is compared with its own baseline; the fitted reference stays as a dashed guide
    if (!panel.series.some((s) => s.point === reference)) {
      out.push({
        key: reference,
        label: "fitted reference",
        color: INK.muted,
        dashed: true,
        values: levels.map((l) => 100 * points[reference].levels[levelKey(l)].h1),
        dotsWhere: () => false,
      });
    }
    for (const s of panel.series) {
      const point = points[s.point];
      const color = s.baseline
        ? INK.primary
        : s.accent !== null
          ? seriesColor(s.accent)
          : RAMP[ramped.length][ramped.findIndex((r) => r.point === s.point)];
      out.push({
        key: s.point,
        label: s.baseline ? `${s.label}, baseline` : s.label,
        color,
        values: levels.map((l) => 100 * point.levels[levelKey(l)].h1),
        hollowWhere: (index) => point.levels[levelKey(levels[index])].cap_share < gate,
      });
    }
    return out;
  };

  const sweepKeys = Object.keys(points).filter((key) => key !== reference && points[key].family !== "primary");

  return (
    <StoryFigure
      title="What the lead depends on: the robustness sweeps"
      subtitle={`Liquid minus the representative across the dial, ${cities} cities per setting. In each panel the dark line is the baseline; the others vary one setting, light to dark in order. A hollow point: fewer than ${Math.round(100 * gate)}% of cities under the 10% cap at that level.`}
      source="eval/benchmarks/delegation_frontier_v1 (levels.csv, thresholds.csv)"
      note="City-level 95% intervals are about ±0.7 points, so lines closer than about a point are not distinguished."
      table={{
        caption: "Each sweep setting's lead at the dial's turnout and its threshold reading",
        columns: [
          { key: "setting", label: "Setting" },
          { key: "lead", label: `Lead at ${level} (points)`, numeric: true },
          { key: "crossing", label: "Crosses near", numeric: true },
          { key: "range", label: "Crossing range" },
          { key: "verdict", label: "Reading" },
        ],
        rows: sweepKeys.map((key) => {
          const p = points[key];
          const [lo, hi] = p.confidence;
          return {
            setting: `${p.family.replace(/_/g, " ")}: ${p.label}`,
            lead: pointsLabel(100 * p.levels[levelKey(level)].h1),
            crossing: p.crossing === null ? "" : p.crossing.toFixed(2),
            range: lo === null && hi === null ? "unbounded" : `${lo ?? "−∞"} to ${hi ?? "∞"}`,
            verdict: p.verdict,
          };
        }),
      }}
    >
      <div className="grid gap-x-8 gap-y-10 md:grid-cols-2">
        {panels.map((panel) => {
          const series = seriesFor(panel);
          return (
            <div key={panel.title}>
              <div className="mb-1 font-sans text-sm font-medium text-story-ink">{panel.title}</div>
              <DialLegend series={series} />
              <div className="mt-1">
                <DialChart
                  series={series}
                  yDomain={[-25, 22]}
                  yTicks={[-20, -10, 0, 10, 20]}
                  yFormat={pointsLabel}
                  yLabel="Points"
                  height={200}
                  lines={[{ y: 0 }]}
                  ariaLabel={`${panel.title}: liquid minus the representative across the dial`}
                />
              </div>
            </div>
          );
        })}
      </div>
      <TurnoutDial className="mt-6 max-w-xl" />
    </StoryFigure>
  );
}
