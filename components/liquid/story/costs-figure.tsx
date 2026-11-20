"use client";

import * as React from "react";

import { AxisX, AxisY, ChartTooltip, useElementWidth } from "@/components/story/chart";
import { StoryFigure } from "@/components/story/story-figure";
import { pct } from "@/lib/liquid/format";
import { levelKey, type ArrangementMeasures } from "@/lib/liquid/story-types";
import { INK, seriesColor } from "@/lib/story/palette";

import { OUTCOME_COLOR } from "./city-dots";
import { DialChart, DialLegend, type DialSeries } from "./dial-chart";
import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

const percent = (value: number) => `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
const LIQUID = seriesColor(0);
const REPRESENTATIVE = seriesColor(1);

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

/** §10, the costs the headline does not show: concentration, poor representation and the cold start. */
export function CostsFigure() {
  const { measures } = useStoryData();
  const { levels, key, level } = useTurnout();
  const m = measures.levels;
  const at = m[key];

  const concentration: DialSeries[] = [
    { key: "mean", label: "Liquid: largest delegate, average question", color: LIQUID, values: across(levels, m, "liquid", "mean_largest_share") },
    {
      key: "worst",
      label: "Liquid: largest delegate, a city's worst question",
      color: LIQUID,
      dashed: true,
      values: across(levels, m, "liquid", "max_largest_share"),
    },
    {
      key: "rep",
      label: "A district representative",
      color: REPRESENTATIVE,
      values: across(levels, m, "representative", "mean_largest_share"),
    },
  ];
  const poor: DialSeries[] = [
    { key: "liquid", label: "Liquid delegation", color: LIQUID, values: across(levels, m, "liquid", "share_below_half") },
    { key: "rep", label: "District representative", color: REPRESENTATIVE, values: across(levels, m, "representative", "share_below_half") },
  ];
  const lifecycle: DialSeries[] = [
    { key: "lifecycle", label: "Liquid, counting the history period", color: LIQUID, values: across(levels, m, "liquid", "lifecycle_overhead") },
    { key: "steady", label: "Liquid, steady state", color: LIQUID, dashed: true, values: across(levels, m, "liquid", "overhead") },
  ];

  const composition = (["liquid", "representative"] as const).map((name) => {
    const none = at[name].below_half_none_share ?? 0;
    const contrary = at[name].below_half_contrary_share ?? 0;
    return { name, none, contrary, match: Math.max(0, 1 - none - contrary) };
  });

  return (
    <StoryFigure
      title="Costs the headline does not show"
      subtitle={`Means over the ${measures.protocol.cities} primary cities across the dial.`}
      source="eval/benchmarks/delegation_frontier_v1/measures.csv"
      table={{
        caption: "Concentration, poor representation and the cold start per turnout level",
        columns: [
          { key: "level", label: "Turnout", numeric: true },
          { key: "largest", label: "Largest delegate (avg / worst)", numeric: true },
          { key: "poor", label: "Under half (liquid / rep.)", numeric: true },
          { key: "lifecycle", label: "Lifecycle overhead", numeric: true },
        ],
        rows: levels.map((l) => {
          const v = m[levelKey(l)];
          return {
            level: l,
            largest: `${pct(v.liquid.mean_largest_share ?? 0)} / ${pct(v.liquid.max_largest_share ?? 0)}`,
            poor: `${pct(v.liquid.share_below_half ?? 0)} / ${pct(v.representative.share_below_half ?? 0)}`,
            lifecycle: pct(v.liquid.lifecycle_overhead ?? 0),
          };
        }),
      }}
    >
      <div className="grid gap-8 md:grid-cols-2">
        <Panel
          title="Concentration: one person's share of a question"
          series={concentration}
          yDomain={[0, 70]}
          yTicks={[0, 20, 40, 60]}
          yFormat={percent}
          yLabel="Share of votes"
          height={210}
          ariaLabel="The largest single delegate's share of a question across the dial"
        />
        <Panel
          title="Voters represented on fewer than half their questions"
          series={poor}
          yDomain={[0, 35]}
          yTicks={[0, 10, 20, 30]}
          yFormat={percent}
          yLabel="Voters"
          height={210}
          ariaLabel="Share of voters represented on fewer than half their questions across the dial"
        />
        <div>
          <div className="mb-1 font-sans text-sm font-medium text-story-ink">
            How those voters fail, at turnout {level}
          </div>
          <div className="space-y-3 font-sans text-xs">
            {composition.map((c) => (
              <div key={c.name}>
                <div className="mb-1 text-story-ink-2">
                  {c.name === "liquid" ? "Liquid delegation" : "District representative"}: {pct(c.none, 0)} no ballot,{" "}
                  {pct(c.contrary, 0)} against them
                </div>
                <div className="flex h-3.5 gap-[2px] overflow-hidden rounded-[3px]" aria-hidden="true">
                  <span style={{ width: `${100 * c.match}%`, background: OUTCOME_COLOR.match }} />
                  <span style={{ width: `${100 * c.contrary}%`, background: OUTCOME_COLOR.contrary }} />
                  <span style={{ width: `${100 * c.none}%`, background: OUTCOME_COLOR.none }} />
                </div>
              </div>
            ))}
            <p className="text-story-muted">Of those voters&apos; questions: matched, against them, no ballot.</p>
          </div>
        </div>
        <Panel
          title="The cold start: overhead while the record is built"
          series={lifecycle}
          yDomain={[0, 100]}
          yTicks={[0, 25, 50, 75, 100]}
          yFormat={percent}
          yLabel="Overhead"
          height={210}
          ariaLabel="Liquid's overhead with and without the history period across the dial"
        />
      </div>
      <TurnoutDial className="mt-6 max-w-xl" />
    </StoryFigure>
  );
}

/** §10's router: what the real decision model does when it files a question under a voter's categories. */
export function RouterFigure() {
  const { results } = useStoryData();
  const { by_threshold: rows, operating, model, fixture } = results.router;
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = React.useState<number | null>(null);
  const margin = { top: 26, right: 12, bottom: 40, left: 46 };
  const height = 240;
  const plotWidth = Math.max(60, width - margin.left - margin.right);
  const plotHeight = height - margin.top - margin.bottom;
  // The axis reaches the largest error measured, rounded up to a tenth
  const top = Math.ceil(10 * Math.max(...rows.flatMap((r) => [r.false_delegation_rate, r.false_keep_rate]))) / 10;
  const ticks = Array.from({ length: Math.round(top / 0.1) + 1 }, (_, i) => Number((i * 0.1).toFixed(1)));
  const x = (value: number) => value * plotWidth;
  const y = (value: number) => plotHeight - (value / top) * plotHeight;
  const line = (field: "false_delegation_rate" | "false_keep_rate") =>
    rows.map((r, i) => `${i ? "L" : "M"}${x(r.threshold)},${y(r[field])}`).join("");
  const series = [
    { key: "false_delegation_rate" as const, label: "False delegation: sent to a category it is not about", color: seriesColor(2) },
    { key: "false_keep_rate" as const, label: "False keep: kept although a category fitted", color: seriesColor(3) },
  ];

  return (
    <StoryFigure
      title="The study routes every question exactly; a real router does not"
      subtitle={`The decision model (${model}) on ${fixture.voter_cases} voter cases: ${fixture.questions} questions against ${fixture.categories} written categories. A false delegation costs fidelity; a false keep costs overhead.`}
      source={results.router.source}
      note={`At the operating threshold, ${operating.threshold}: ${operating.false_delegations} false delegations (${pct(operating.false_delegation_rate)} of those sent) and ${operating.false_keeps} false keeps (${pct(operating.false_keep_rate)} of the ${operating.delegable} cases with a fitting category). The benchmark under routing error is a declared follow-up, not a result.`}
      table={{
        caption: "Router errors by threshold",
        columns: [
          { key: "threshold", label: "Threshold", numeric: true },
          { key: "fd", label: "False delegation", numeric: true },
          { key: "fk", label: "False keep", numeric: true },
          { key: "coverage", label: "Coverage", numeric: true },
        ],
        rows: rows.map((r) => ({
          threshold: r.threshold,
          fd: pct(r.false_delegation_rate),
          fk: pct(r.false_keep_rate),
          coverage: pct(r.coverage),
        })),
      }}
    >
      <DialLegend series={series.map((s) => ({ ...s }))} />
      <div ref={ref} className="relative mt-1">
        {width > 0 ? (
          <svg
            width={width}
            height={height}
            role="img"
            aria-label="Router false delegation and false keep rates by threshold"
            className="block font-sans"
            onPointerMove={(event) => {
              const px = event.clientX - event.currentTarget.getBoundingClientRect().left - margin.left;
              let best = 0;
              rows.forEach((r, i) => {
                if (Math.abs(x(r.threshold) - px) < Math.abs(x(rows[best].threshold) - px)) best = i;
              });
              setHover(best);
            }}
            onPointerLeave={() => setHover(null)}
          >
            <g transform={`translate(${margin.left},${margin.top})`}>
              <AxisY y={y} ticks={ticks} format={(v) => `${Math.round(v * 100)}%`} width={plotWidth} />
              <AxisX
                x={x}
                ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
                format={(v) => String(v)}
                y={plotHeight}
                label="Threshold: how sure the model must be"
                width={plotWidth}
              />
              <text x={-margin.left} y={-margin.top + 11} fontSize={11} fill={INK.muted}>
                Error rate
              </text>
              <line x1={x(operating.threshold)} x2={x(operating.threshold)} y1={0} y2={plotHeight} stroke={INK.secondary} />
              <text x={x(operating.threshold) + 4} y={10} fontSize={10} fill={INK.secondary}>
                operating threshold {operating.threshold}
              </text>
              {series.map((s) => (
                <g key={s.key}>
                  <path d={line(s.key)} fill="none" stroke={s.color} strokeWidth={2} />
                  {rows.map((r) => (
                    <circle key={r.threshold} cx={x(r.threshold)} cy={y(r[s.key])} r={3} fill={s.color} stroke={INK.surface} strokeWidth={1.5} />
                  ))}
                </g>
              ))}
            </g>
          </svg>
        ) : (
          <div style={{ height }} />
        )}
        {hover !== null && width > 0 ? (
          <ChartTooltip x={margin.left + x(rows[hover].threshold)} y={margin.top + plotHeight / 3} width={width}>
            <div className="font-sans">
              <div className="font-semibold">Threshold {rows[hover].threshold}</div>
              <div>False delegation: {pct(rows[hover].false_delegation_rate)}</div>
              <div>False keep: {pct(rows[hover].false_keep_rate)}</div>
              <div>Coverage: {pct(rows[hover].coverage)}</div>
            </div>
          </ChartTooltip>
        ) : null}
      </div>
    </StoryFigure>
  );
}
