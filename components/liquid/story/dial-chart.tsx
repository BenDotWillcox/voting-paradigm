"use client";

import * as React from "react";

import { AxisX, AxisY, ChartTooltip, useElementWidth } from "@/components/story/chart";
import { INK } from "@/lib/story/palette";

import { useTurnout } from "./turnout";

export interface DialSeries {
  key: string;
  label: string;
  color: string;
  /** One value per turnout level, in the dial's order; null for no value. */
  values: Array<number | null>;
  dashed?: boolean;
  /** Draw the points only, without a line between them. */
  dotsOnly?: boolean;
  /** A color per point, where some points mean something else (a failing level). */
  dotColor?: (index: number) => string;
  /** Draw a point only where this holds (the line still runs through all). */
  dotsWhere?: (index: number) => boolean;
}

interface DialChartProps {
  series: DialSeries[];
  /** A shaded band around one curve, one bound per level. */
  band?: { lower: number[]; upper: number[]; color: string };
  yDomain: [number, number];
  yTicks: number[];
  yFormat: (value: number) => string;
  yLabel: string;
  height?: number;
  /** Horizontal reference lines; labels sit at the left unless `labelAt` says right. */
  lines?: Array<{ y: number; label?: string; dashed?: boolean; labelAt?: "left" | "right" }>;
  /** A shaded stretch of the dial, as turnout values. */
  shade?: { from: number; to: number; label?: string };
  /** Points to mark and label, in data coordinates. */
  marks?: Array<{ x: number; y: number; label: string }>;
  /** Labels above the points of one series (only where `where` holds, if given). */
  pointLabels?: {
    series: string;
    format: (value: number, index: number) => string;
    where?: (value: number, index: number) => boolean;
  };
  /** Vertical interval bars at some levels (an index into the dial's levels). */
  whiskers?: Array<{ index: number; lower: number; upper: number; color: string }>;
  ariaLabel: string;
}

/**
 * A measure across the turnout dial: one line per series at the recorded
 * levels, with the dial's own level marked. Hovering reads every series at
 * the nearest level. Plain and static; the page's design comes later.
 */
export function DialChart({
  series,
  band,
  yDomain,
  yTicks,
  yFormat,
  yLabel,
  height = 240,
  lines = [],
  shade,
  marks = [],
  pointLabels,
  whiskers = [],
  ariaLabel,
}: DialChartProps) {
  const { levels, level } = useTurnout();
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = React.useState<number | null>(null);
  // Room above the plot for the axis title (and point labels)
  const margin = { top: pointLabels ? 34 : 26, right: 12, bottom: 34, left: 46 };
  const plotWidth = Math.max(60, width - margin.left - margin.right);
  const plotHeight = height - margin.top - margin.bottom;
  const x = (value: number) => ((value - 0.05) / 0.9) * plotWidth;
  const y = (value: number) =>
    plotHeight - ((Math.max(yDomain[0], Math.min(yDomain[1], value)) - yDomain[0]) / (yDomain[1] - yDomain[0])) * plotHeight;

  const path = (values: Array<number | null>) => {
    let d = "";
    let open = false;
    values.forEach((value, index) => {
      if (value === null) {
        open = false;
        return;
      }
      d += `${open ? "L" : "M"}${x(levels[index])},${y(value)}`;
      open = true;
    });
    return d;
  };
  const bandPath = band
    ? `M${levels.map((l, i) => `${x(l)},${y(band.upper[i])}`).join("L")}L${levels
        .map((l, i) => `${x(l)},${y(band.lower[i])}`)
        .reverse()
        .join("L")}Z`
    : "";

  const onMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - box.left - margin.left;
    let best = 0;
    levels.forEach((l, i) => {
      if (Math.abs(x(l) - px) < Math.abs(x(levels[best]) - px)) best = i;
    });
    setHover(best);
  };

  return (
    <div ref={ref} className="relative">
      {width > 0 ? (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={ariaLabel}
          className="block font-sans"
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        >
          <g transform={`translate(${margin.left},${margin.top})`}>
            {shade ? (
              <g>
                <rect
                  x={x(shade.from)}
                  y={0}
                  width={x(shade.to) - x(shade.from)}
                  height={plotHeight}
                  fill={INK.grid}
                  opacity={0.6}
                />
                {shade.label ? (
                  // A line break in the label splits it, so it fits a narrow band
                  <text textAnchor="middle" fontSize={10} fill={INK.muted}>
                    {shade.label.split("\n").map((part, i) => (
                      // At the top of the band, clear of curves that start low
                      <tspan key={part} x={(x(shade.from) + x(shade.to)) / 2} y={12 + i * 12}>
                        {part}
                      </tspan>
                    ))}
                  </text>
                ) : null}
              </g>
            ) : null}
            <AxisY y={y} ticks={yTicks} format={yFormat} width={plotWidth} />
            <AxisX x={x} ticks={levels.filter((l) => l !== 0.45)} format={(v) => String(v)} y={plotHeight} />
            <text x={-margin.left} y={-margin.top + 11} fontSize={11} fill={INK.muted}>
              {yLabel}
            </text>
            {lines.map((line) => (
              <g key={`${line.y}-${line.label ?? ""}`}>
                <line
                  x1={0}
                  x2={plotWidth}
                  y1={y(line.y)}
                  y2={y(line.y)}
                  stroke={line.dashed ? INK.secondary : INK.axis}
                  strokeWidth={line.dashed ? 1 : 1.25}
                  strokeDasharray={line.dashed ? "4 3" : undefined}
                />
                {line.label ? (
                  <text
                    x={line.labelAt === "right" ? plotWidth : 4}
                    y={y(line.y) - 4}
                    textAnchor={line.labelAt === "right" ? "end" : "start"}
                    fontSize={10}
                    fill={INK.secondary}
                  >
                    {line.label}
                  </text>
                ) : null}
              </g>
            ))}
            {/* The dial's own level */}
            <line x1={x(level)} x2={x(level)} y1={0} y2={plotHeight} stroke={INK.secondary} strokeWidth={1} />
            {band ? <path d={bandPath} fill={band.color} opacity={0.18} /> : null}
            {series.map((s) =>
              s.dotsOnly ? null : (
                <path
                  key={s.key}
                  d={path(s.values)}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={2}
                  strokeDasharray={s.dashed ? "5 4" : undefined}
                />
              )
            )}
            {whiskers.map((w) => (
              <line
                key={`whisker-${w.index}-${w.color}`}
                x1={x(levels[w.index])}
                x2={x(levels[w.index])}
                y1={y(w.lower)}
                y2={y(w.upper)}
                stroke={w.color}
                strokeWidth={2}
              />
            ))}
            {series.map((s) =>
              s.values.map((value, index) =>
                value === null || (s.dotsWhere && !s.dotsWhere(index)) ? null : (
                  <circle
                    key={`${s.key}-${index}`}
                    cx={x(levels[index])}
                    cy={y(value)}
                    r={levels[index] === level ? 5 : 3.5}
                    fill={s.dotColor ? s.dotColor(index) : s.color}
                    stroke={INK.surface}
                    strokeWidth={1.5}
                  />
                )
              )
            )}
            {pointLabels
              ? (series.find((s) => s.key === pointLabels.series)?.values ?? []).map((value, index) =>
                  value === null || (pointLabels.where && !pointLabels.where(value, index)) ? null : (
                    <text
                      key={`label-${index}`}
                      x={x(levels[index])}
                      y={y(value) - 9}
                      textAnchor="middle"
                      fontSize={10}
                      fill={INK.secondary}
                    >
                      {pointLabels.format(value, index)}
                    </text>
                  )
                )
              : null}
            {marks.map((mark) => (
              <g key={mark.label}>
                <circle cx={x(mark.x)} cy={y(mark.y)} r={4.5} fill={INK.surface} stroke={INK.primary} strokeWidth={1.75} />
                <text x={x(mark.x) + 8} y={y(mark.y) + 14} fontSize={11} fill={INK.primary}>
                  {mark.label}
                </text>
              </g>
            ))}
            {hover !== null ? (
              <line x1={x(levels[hover])} x2={x(levels[hover])} y1={0} y2={plotHeight} stroke={INK.muted} strokeDasharray="2 3" />
            ) : null}
          </g>
        </svg>
      ) : (
        <div style={{ height }} />
      )}
      {hover !== null && width > 0 ? (
        <ChartTooltip x={margin.left + x(levels[hover])} y={margin.top + plotHeight / 3} width={width}>
          <div className="font-sans">
            <div className="font-semibold">Turnout {levels[hover]}</div>
            {series.map((s) => (
              <div key={s.key}>
                {s.label}: {s.values[hover] === null ? "none" : yFormat(s.values[hover] as number)}
              </div>
            ))}
          </div>
        </ChartTooltip>
      ) : null}
    </div>
  );
}

/** The key to a DialChart's series. */
export function DialLegend({ series }: { series: Array<Pick<DialSeries, "key" | "label" | "color" | "dashed" | "dotsOnly">> }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 font-sans text-xs text-story-ink-2">
      {series.map((s) => (
        <span key={s.key} className="inline-flex items-center gap-1.5">
          <svg width={20} height={10} aria-hidden="true">
            {s.dotsOnly ? null : (
              <line x1={0} x2={20} y1={5} y2={5} stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? "4 3" : undefined} />
            )}
            <circle cx={10} cy={5} r={3} fill={s.color} />
          </svg>
          {s.label}
        </span>
      ))}
    </div>
  );
}
