"use client";

import { useState } from "react";
import { ago } from "./people";

export type TrendPoint = {
  /** Days before today; larger is further back. */
  daysAgo: number;
  value: number;
  /** What this point is, for the tooltip and the table: a ballot's name. */
  label: string;
};

type Props = {
  /** Names the series; a single series needs no legend. */
  title: string;
  /** Oldest first. */
  points: TrendPoint[];
  format: (value: number) => string;
};

const WIDTH = 720;
const HEIGHT = 240;
const PAD = { top: 16, right: 20, bottom: 30, left: 48 };

/** Round a maximum up to a tidy axis top with three even steps below it. */
function axisTop(max: number): number {
  if (max <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(max));
  const step = [1, 2, 2.5, 5, 10].find((candidate) => candidate * magnitude >= max) ?? 10;
  return step * magnitude;
}

/**
 * One stat over time, one point per closed ballot. Time runs left to right
 * on a true scale, so ballots that closed close together sit close together.
 * Hovering or focusing the plot reads out the nearest point; the same
 * numbers are in the table underneath.
 */
export function TrendChart({ title, points, format }: Props) {
  const [active, setActive] = useState<number | null>(null);

  if (points.length < 2) {
    return (
      <p className="text-sm text-muted-foreground">
        Not enough closed ballots to draw {title.toLowerCase()} over time.
      </p>
    );
  }

  const oldest = points[0].daysAgo;
  const newest = points[points.length - 1].daysAgo;
  const top = axisTop(Math.max(...points.map((point) => point.value)));
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const x = (daysAgo: number) =>
    PAD.left + ((oldest - daysAgo) / Math.max(oldest - newest, 1)) * plotWidth;
  const y = (value: number) => PAD.top + plotHeight - (value / top) * plotHeight;
  const line = points.map((point) => `${x(point.daysAgo)},${y(point.value)}`).join(" ");
  const ticks = [0, top / 2, top];
  const shown = active === null ? null : points[active];

  const nearest = (clientX: number, bounds: DOMRect) => {
    const at = ((clientX - bounds.left) / bounds.width) * WIDTH;
    let best = 0;
    points.forEach((point, index) => {
      if (Math.abs(x(point.daysAgo) - at) < Math.abs(x(points[best].daysAgo) - at)) best = index;
    });
    setActive(best);
  };

  return (
    <figure className="space-y-3">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-sm font-semibold">{title}, by ballot</span>
        <span className="font-mono text-xs text-muted-foreground" aria-live="polite">
          {shown
            ? `${shown.label} · ${ago(shown.daysAgo)} · ${format(shown.value)}`
            : "Point at the chart for a ballot's value"}
        </span>
      </figcaption>
      <div className="relative">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-auto w-full touch-none select-none"
          role="img"
          aria-label={`${title} for each of ${points.length} closed ballots, from ${ago(oldest)} to ${ago(newest)}`}
          onPointerMove={(event) => nearest(event.clientX, event.currentTarget.getBoundingClientRect())}
          onPointerLeave={() => setActive(null)}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={PAD.left}
                x2={WIDTH - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke="currentColor"
                className="text-border"
                strokeWidth="1"
              />
              <text
                x={PAD.left - 8}
                y={y(tick) + 4}
                textAnchor="end"
                className="fill-muted-foreground font-mono text-[11px]"
              >
                {format(tick)}
              </text>
            </g>
          ))}
          <text x={PAD.left} y={HEIGHT - 8} className="fill-muted-foreground font-mono text-[11px]">
            {ago(oldest)}
          </text>
          <text
            x={WIDTH - PAD.right}
            y={HEIGHT - 8}
            textAnchor="end"
            className="fill-muted-foreground font-mono text-[11px]"
          >
            {ago(newest)}
          </text>

          {shown && (
            <line
              x1={x(shown.daysAgo)}
              x2={x(shown.daysAgo)}
              y1={PAD.top}
              y2={PAD.top + plotHeight}
              stroke="var(--foreground)"
              strokeOpacity="0.35"
              strokeWidth="1"
            />
          )}
          <polyline
            points={line}
            fill="none"
            stroke="var(--lq-violet)"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {points.map((point, index) => (
            <circle
              key={`${point.label}-${point.daysAgo}`}
              cx={x(point.daysAgo)}
              cy={y(point.value)}
              r={index === active ? 6 : 4.5}
              fill="var(--lq-violet)"
              stroke="var(--background)"
              strokeWidth="2"
            />
          ))}
        </svg>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
          View as a table
        </summary>
        <table className="mt-2 w-full text-left text-sm">
          <thead>
            <tr className="liquid-label">
              <th className="py-1 pr-4 font-normal">Ballot</th>
              <th className="py-1 pr-4 font-normal">Closed</th>
              <th className="py-1 text-right font-normal">{title}</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={`${point.label}-${point.daysAgo}`} className="border-t">
                <td className="py-1 pr-4">{point.label}</td>
                <td className="py-1 pr-4 text-muted-foreground">{ago(point.daysAgo)}</td>
                <td className="py-1 text-right font-mono tabular-nums">{format(point.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
