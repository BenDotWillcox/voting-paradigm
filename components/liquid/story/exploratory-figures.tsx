"use client";

import * as React from "react";

import { AxisX, AxisY, ChartTooltip, useElementWidth } from "@/components/story/chart";
import { DataTable, StoryFigure } from "@/components/story/story-figure";
import { dec, pct } from "@/lib/liquid/format";
import { levelKey, type Arrangement } from "@/lib/liquid/story-types";
import { INK, seriesColor } from "@/lib/story/palette";

import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

const LIQUID = seriesColor(0);
const REPRESENTATIVE = seriesColor(1);

/**
 * §12a, exploratory: liquid's handover curve at the dial's turnout. At depth
 * d every voter hands over their d best topics; depth 0 is direct voting and
 * depth 8 hands over everything a voter can. The frozen benchmark holds only
 * the calibrated point, drawn beside the curve.
 */
export function HandoverFigure() {
  const { exploratory, measures } = useStoryData();
  const { key, level } = useTurnout();
  const curve = exploratory.handover.levels[key];
  const at = measures.levels[key];
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = React.useState<number | null>(null);
  const margin = { top: 26, right: 16, bottom: 40, left: 46 };
  const height = 320;
  const plotWidth = Math.max(60, width - margin.left - margin.right);
  const plotHeight = height - margin.top - margin.bottom;
  const x = (value: number) => ((value + 0.02) / 1.07) * plotWidth;
  const y = (value: number) => plotHeight - (value / 1.05) * plotHeight;
  const path = curve.map((p, i) => `${i ? "L" : "M"}${x(p.overhead)},${y(p.fidelity)}`).join("");
  const best = curve.reduce((a, b) => (b.fidelity > a.fidelity ? b : a));
  const deepest = curve[curve.length - 1];
  const cap = measures.protocol.cap;

  return (
    <StoryFigure
      title={`Liquid's whole curve at turnout ${level}: from voting yourself to handing over everything`}
      subtitle={`Each point is a depth: every voter hands over that many of their best topics. Highest fidelity here at depth ${best.depth} (${dec(best.fidelity)}).`}
      source={`${exploratory.handover.source}, run from commit ${exploratory.handover.commit.slice(0, 7)} on ${exploratory.handover.cities} cities; calibrated point and representative from the frozen benchmark`}
      note="Exploratory, computed after the freeze with the frozen code. The calibrated point uses a city-wide quality cut-off and the curve a count of topics per voter, so the point need not lie on the curve."
      table={{
        caption: `Liquid's handover curve at turnout ${level}`,
        columns: [
          { key: "depth", label: "Depth", numeric: true },
          { key: "overhead", label: "Overhead", numeric: true },
          { key: "fidelity", label: "Fidelity", numeric: true },
          { key: "contrary", label: "Against them", numeric: true },
          { key: "none", label: "No ballot", numeric: true },
        ],
        rows: curve.map((p) => ({
          depth: p.depth,
          overhead: dec(p.overhead),
          fidelity: dec(p.fidelity),
          contrary: pct(p.contrary_share),
          none: pct(p.none_share),
        })),
      }}
    >
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 font-sans text-xs text-story-ink-2">
        <span className="inline-flex items-center gap-1.5">
          <svg width={20} height={10} aria-hidden="true">
            <line x1={0} x2={20} y1={5} y2={5} stroke={LIQUID} strokeWidth={2} />
            <circle cx={10} cy={5} r={3} fill={LIQUID} />
          </svg>
          Liquid, depths 0 to {deepest.depth}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width={12} height={12} aria-hidden="true">
            <circle cx={6} cy={6} r={4.5} fill="none" stroke={INK.primary} strokeWidth={1.5} />
          </svg>
          Liquid as calibrated (frozen)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width={12} height={12} aria-hidden="true">
            <path d="M6,1L11,6L6,11L1,6Z" fill={REPRESENTATIVE} />
          </svg>
          District representative
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width={12} height={12} aria-hidden="true">
            <rect x={2} y={2} width={8} height={8} fill={INK.secondary} />
          </svg>
          Full turnout
        </span>
      </div>
      <div ref={ref} className="relative mt-2">
        {width > 0 ? (
          <svg
            width={width}
            height={height}
            role="img"
            aria-label={`Liquid's handover curve at turnout ${level}`}
            className="block font-sans"
            onPointerMove={(event) => {
              const box = event.currentTarget.getBoundingClientRect();
              const px = event.clientX - box.left - margin.left;
              const py = event.clientY - box.top - margin.top;
              let nearest = 0;
              curve.forEach((p, i) => {
                const d = Math.hypot(x(p.overhead) - px, y(p.fidelity) - py);
                if (d < Math.hypot(x(curve[nearest].overhead) - px, y(curve[nearest].fidelity) - py)) nearest = i;
              });
              setHover(nearest);
            }}
            onPointerLeave={() => setHover(null)}
          >
            <g transform={`translate(${margin.left},${margin.top})`}>
              <AxisY y={y} ticks={[0, 0.25, 0.5, 0.75, 1]} format={(v) => String(v)} width={plotWidth} />
              <AxisX x={x} ticks={[0, 0.25, 0.5, 0.75, 1]} format={(v) => String(v)} y={plotHeight} grid label="Overhead" width={plotWidth} />
              <text x={-margin.left} y={-margin.top + 11} fontSize={11} fill={INK.muted}>
                Fidelity
              </text>
              <line x1={x(cap)} x2={x(cap)} y1={0} y2={plotHeight} stroke={INK.secondary} strokeDasharray="4 3" />
              <text x={x(cap) + 4} y={plotHeight - 6} fontSize={10} fill={INK.secondary}>
                {pct(cap, 0)} overhead
              </text>
              <path d={path} fill="none" stroke={LIQUID} strokeWidth={2} />
              {curve.map((p) => (
                <circle key={p.depth} cx={x(p.overhead)} cy={y(p.fidelity)} r={3.5} fill={LIQUID} stroke={INK.surface} strokeWidth={1.5} />
              ))}
              {[curve[0], deepest].map((p) => (
                <text
                  key={`label-${p.depth}`}
                  x={x(p.overhead)}
                  y={y(p.fidelity) + (p.depth === 0 ? 16 : -10)}
                  textAnchor="middle"
                  fontSize={10}
                  fill={INK.secondary}
                >
                  depth {p.depth}
                </text>
              ))}
              <circle cx={x(at.liquid.overhead)} cy={y(at.liquid.fidelity)} r={6} fill="none" stroke={INK.primary} strokeWidth={1.5} />
              <path
                transform={`translate(${x(at.representative.overhead)},${y(at.representative.fidelity)})`}
                d="M0,-6L6,0L0,6L-6,0Z"
                fill={REPRESENTATIVE}
                stroke={INK.surface}
                strokeWidth={1.5}
              />
              <rect x={x(1) - 5} y={y(1) - 5} width={10} height={10} fill={INK.secondary} />
            </g>
          </svg>
        ) : (
          <div style={{ height }} />
        )}
        {hover !== null && width > 0 ? (
          <ChartTooltip x={margin.left + x(curve[hover].overhead)} y={margin.top + y(curve[hover].fidelity)} width={width}>
            <div className="font-sans">
              <div className="font-semibold">Depth {curve[hover].depth}</div>
              <div>
                Overhead {dec(curve[hover].overhead)} · fidelity {dec(curve[hover].fidelity)}
              </div>
              <div>
                {pct(curve[hover].contrary_share)} against · {pct(curve[hover].none_share)} no ballot
              </div>
            </div>
          </ChartTooltip>
        ) : null}
      </div>
      <TurnoutDial className="mt-4 max-w-xl" />
    </StoryFigure>
  );
}

const SCORED: readonly Arrangement[] = ["direct", "representative", "proxy", "liquid"];
const SHORT: Record<string, string> = { direct: "Direct", representative: "Representative", proxy: "Proxy", liquid: "Liquid" };

/**
 * §12b, exploratory: each arrangement scored as match − w × contrary. w = 0
 * is the frozen fidelity; w = 1 counts a ballot against a voter as −1, as it
 * acts on a binary majority. A static table, from the published shares.
 */
export function WrongBallotFigure() {
  const { exploratory, measures } = useStoryData();
  const levels = measures.protocol.turnout_grid;
  const table = exploratory.wrong_ballot.levels;
  return (
    <StoryFigure
      title="How bad is a ballot against you? Two ways to score"
      subtitle="Each arrangement scored as matches minus w times ballots against the voter. At w = 0 a ballot against you counts like no ballot (the frozen fidelity); at w = 1 it counts as −1, as it does on a yes-or-no majority."
      source={exploratory.wrong_ballot.source}
      note="Exploratory: a re-scoring of the frozen benchmark's published shares, without intervals. The frozen verdict is read at w = 0."
    >
      <DataTable
        caption="Scores at w = 0 and w = 1 per turnout level"
        columns={[
          { key: "level", label: "Turnout", numeric: true },
          ...SCORED.flatMap((name) =>
            name === "direct"
              ? [{ key: "direct", label: "Direct (both)", numeric: true }]
              : [
                  { key: `${name}0`, label: `${SHORT[name]}, w = 0`, numeric: true },
                  { key: `${name}1`, label: `${SHORT[name]}, w = 1`, numeric: true },
                ]
          ),
        ]}
        rows={levels.map((l) => {
          const at = table[levelKey(l)];
          return {
            level: l,
            direct: dec(at.direct.w0),
            ...Object.fromEntries(
              SCORED.filter((name) => name !== "direct").flatMap((name) => [
                [`${name}0`, dec(at[name].w0)],
                [`${name}1`, dec(at[name].w1)],
              ])
            ),
          };
        })}
      />
    </StoryFigure>
  );
}
