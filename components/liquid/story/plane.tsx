"use client";

import * as React from "react";

import { AxisX, AxisY, ChartTooltip, useElementWidth } from "@/components/story/chart";
import { DataTable, StoryFigure } from "@/components/story/story-figure";
import { dec } from "@/lib/liquid/format";
import { ARRANGEMENT_LABEL, ARRANGEMENTS, type Arrangement } from "@/lib/liquid/story-types";
import { INK, seriesColor } from "@/lib/story/palette";

import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

type Shape = "circle" | "ring" | "diamond" | "triangle" | "square";

/** Liquid in the first series color, comparisons in the second, references in ink. */
const MARK: Record<Arrangement, { color: string; shape: Shape }> = {
  liquid: { color: seriesColor(0), shape: "circle" },
  proxy: { color: seriesColor(1), shape: "triangle" },
  representative: { color: seriesColor(1), shape: "diamond" },
  direct: { color: INK.secondary, shape: "ring" },
  full_turnout: { color: INK.primary, shape: "square" },
};

/** Drawn last on top: liquid over the comparisons it sits beside. */
const DRAW_ORDER: readonly Arrangement[] = ["full_turnout", "direct", "representative", "proxy", "liquid"];

/** Axis ticks without trailing zeros: 0, 0.25, 0.5, 1. */
function tick(value: number): string {
  return String(Number(value.toFixed(2)));
}

/** The zoom panel's window: every level's low-overhead arrangements fall inside it. */
const ZOOM = { x: [0, 0.25], y: [0.45, 0.85] } as const;

function Mark({ shape, color, size = 9 }: { shape: Shape; color: string; size?: number }) {
  const h = size / 2;
  const ring = { stroke: INK.surface, strokeWidth: 2 };
  switch (shape) {
    case "circle":
      return <circle r={h} fill={color} {...ring} />;
    case "ring":
      return <circle r={h - 1} fill={INK.surface} stroke={color} strokeWidth={2} />;
    case "diamond":
      return <path d={`M0,${-h - 1}L${h + 1},0L0,${h + 1}L${-h - 1},0Z`} fill={color} {...ring} />;
    case "triangle":
      return <path d={`M0,${-h - 1}L${h + 1},${h}L${-h - 1},${h}Z`} fill={color} {...ring} />;
    case "square":
      return <rect x={-h} y={-h} width={size} height={size} fill={color} {...ring} />;
  }
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 font-sans text-xs text-story-ink-2">
      {ARRANGEMENTS.slice()
        .reverse()
        .map((name) => (
          <span key={name} className="inline-flex items-center gap-1.5">
            <svg width={14} height={14} aria-hidden="true" className="overflow-visible">
              <g transform="translate(7,7)">
                <Mark {...MARK[name]} />
              </g>
            </svg>
            {ARRANGEMENT_LABEL[name]}
          </span>
        ))}
    </div>
  );
}

interface PanelProps {
  domainX: readonly [number, number];
  domainY: readonly [number, number];
  ticksX: number[];
  ticksY: number[];
  width: number;
  height: number;
  zoomWindow?: boolean;
  title: string;
}

function Panel({ domainX, domainY, ticksX, ticksY, width, height, zoomWindow, title }: PanelProps) {
  const { measures } = useStoryData();
  const { key } = useTurnout();
  const [hover, setHover] = React.useState<{ name: Arrangement; x: number; y: number } | null>(null);
  const margin = { top: 24, right: 14, bottom: 42, left: 46 };
  const plotWidth = Math.max(60, width - margin.left - margin.right);
  const plotHeight = height - margin.top - margin.bottom;
  const x = (v: number) => ((v - domainX[0]) / (domainX[1] - domainX[0])) * plotWidth;
  const y = (v: number) => plotHeight - ((v - domainY[0]) / (domainY[1] - domainY[0])) * plotHeight;
  const values = measures.levels[key];
  const clip = `plane-${React.useId().replace(/:/g, "")}`;

  return (
    <div className="relative">
      <div className="mb-1 font-sans text-xs font-medium text-story-ink-2">{title}</div>
      <svg width={width} height={height} className="block font-sans" role="img" aria-label={title}>
        <defs>
          <clipPath id={clip}>
            <rect x={-8} y={-8} width={plotWidth + 16} height={plotHeight + 16} />
          </clipPath>
        </defs>
        <g transform={`translate(${margin.left},${margin.top})`}>
          <AxisY y={y} ticks={ticksY} format={tick} width={plotWidth} />
          <AxisX x={x} ticks={ticksX} format={tick} y={plotHeight} grid label="Overhead" width={plotWidth} />
          <text x={-margin.left} y={-14} fontSize={11} fill={INK.muted}>
            Fidelity
          </text>
          {zoomWindow ? (
            <rect
              x={x(ZOOM.x[0])}
              y={y(ZOOM.y[1])}
              width={x(ZOOM.x[1]) - x(ZOOM.x[0])}
              height={y(ZOOM.y[0]) - y(ZOOM.y[1])}
              fill="none"
              stroke={INK.muted}
              strokeDasharray="3 3"
            />
          ) : null}
          <g clipPath={`url(#${clip})`}>
            {DRAW_ORDER.map((name) => {
              const v = values[name];
              const px = x(v.overhead);
              const py = y(v.fidelity);
              return (
                <g
                  key={name}
                  transform={`translate(${px},${py})`}
                  onPointerEnter={() => setHover({ name, x: px + margin.left, y: py + margin.top })}
                  onPointerLeave={() => setHover(null)}
                >
                  <circle r={12} fill="transparent" />
                  <Mark {...MARK[name]} size={10} />
                </g>
              );
            })}
          </g>
        </g>
      </svg>
      {hover ? (
        <ChartTooltip x={hover.x} y={hover.y} width={width}>
          <div className="font-sans">
            <div className="font-semibold">{ARRANGEMENT_LABEL[hover.name]}</div>
            <div>
              Overhead {dec(values[hover.name].overhead)} · fidelity {dec(values[hover.name].fidelity)}
            </div>
          </div>
        </ChartTooltip>
      ) : null}
    </div>
  );
}

/**
 * §4, the framing figure: the five arrangements on the overhead-fidelity
 * plane at the dial's turnout, as averaged over the 200 primary cities.
 * Only the calibrated arrangements are drawn; liquid's own curve is §12's
 * exploratory figure.
 */
export function PlaneFigure() {
  const { measures } = useStoryData();
  const { key, level, swiss } = useTurnout();
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const twoUp = width >= 640;
  const panelWidth = twoUp ? Math.floor((width - 24) / 2) : width;
  const values = measures.levels[key];

  return (
    <StoryFigure
      title={`Five arrangements on one plane, at ${level === swiss ? "Swiss turnout" : "turnout"} ${level}`}
      subtitle="Up is more faithful; left asks less of each voter. The right panel enlarges the dashed corner."
      source="eval/benchmarks/delegation_frontier_v1/measures.csv, mean over the 200 primary cities"
      note="Where two marks overlap (liquid and the proxy at some turnouts), the table below separates them."
    >
      <Legend />
      <div ref={ref} className="mt-3">
        {width > 0 ? (
          <div className={twoUp ? "grid grid-cols-2 gap-6" : "space-y-4"}>
            <Panel
              title="The whole plane"
              domainX={[0, 1]}
              domainY={[0, 1]}
              ticksX={[0, 0.25, 0.5, 0.75, 1]}
              ticksY={[0, 0.25, 0.5, 0.75, 1]}
              width={panelWidth}
              height={280}
              zoomWindow
            />
            <Panel
              title="Near zero overhead"
              domainX={ZOOM.x}
              domainY={ZOOM.y}
              ticksX={[0, 0.05, 0.1, 0.15, 0.2, 0.25]}
              ticksY={[0.5, 0.6, 0.7, 0.8]}
              width={panelWidth}
              height={280}
            />
          </div>
        ) : (
          <div style={{ height: 300 }} />
        )}
      </div>
      <TurnoutDial className="mt-4 max-w-xl" />
      <DataTable
        caption={`Overhead and fidelity at turnout ${level}`}
        columns={[
          { key: "arrangement", label: "Arrangement" },
          { key: "overhead", label: "Overhead", numeric: true },
          { key: "fidelity", label: "Fidelity", numeric: true },
        ]}
        rows={DRAW_ORDER.map((name) => ({
          arrangement: ARRANGEMENT_LABEL[name] + (name === "full_turnout" ? " (reference)" : ""),
          overhead: dec(values[name].overhead),
          fidelity: dec(values[name].fidelity),
        }))}
      />
    </StoryFigure>
  );
}
