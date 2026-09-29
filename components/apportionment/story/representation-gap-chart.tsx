"use client";

import * as React from "react";
import { scaleLinear } from "d3-scale";

import {
  Annotation,
  AxisX,
  ChartTooltip,
  useElementWidth,
  useReducedMotion,
} from "@/components/story/chart";
import { useScrollyStep } from "@/components/story/scrolly";
import { StoryFigure } from "@/components/story/story-figure";
import { INK, seriesColor } from "@/lib/story/palette";
import type {
  HouseSizeSnapshot,
  StateRepresentation,
} from "@/lib/story/representation-gap";

interface RepresentationGapChartProps {
  /** One snapshot per scrolly step. */
  snapshots: HouseSizeSnapshot[];
  /** Short name per snapshot, e.g. "Wyoming Rule". */
  labels: string[];
}

const MARGIN_X = 16;
/** Top band holding the average label and the two extreme-state labels. */
const LABEL_BAND = 58;
const AXIS_SPACE = 34;

/**
 * Each state's district size relative to the national average, as a
 * beeswarm on one axis. Scrolling steps through House sizes; dots glide to
 * their new positions and the spread visibly collapses toward zero.
 */
export function RepresentationGapChart({ snapshots, labels }: RepresentationGapChartProps) {
  const { step } = useScrollyStep();
  const index = Math.min(step, snapshots.length - 1);
  const snapshot = snapshots[index];
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const reducedMotion = useReducedMotion();
  const [hovered, setHovered] = React.useState<StateRepresentation | null>(null);

  // Fixed domain across steps so movement means change, not rescaling.
  const extent = React.useMemo(() => {
    const max = Math.max(...snapshots.flatMap((s) => s.states.map((st) => Math.abs(st.deviation))));
    return Math.ceil(max * 10) / 10;
  }, [snapshots]);

  const plotWidth = Math.max(0, width - 2 * MARGIN_X);
  const radius = width < 480 ? 4 : 5;
  const x = React.useMemo(
    () => scaleLinear().domain([-extent, extent]).range([0, plotWidth]),
    [extent, plotWidth]
  );
  // Swarm every step up front so the chart height stays fixed while
  // scrolling. When states pile up near the average (large Houses), the
  // swarm is compressed into a capped band and dots overlap: the pile-up
  // is the point.
  const maxSpread = width < 480 ? 64 : 88;
  const layouts = React.useMemo(
    () =>
      snapshots.map((s) => {
        const layout = dodge(s.states, (state) => x(state.deviation), radius * 2 + 1.5);
        const spread = Math.max(0, ...[...layout.values()].map((p) => Math.abs(p.y)));
        const squeeze = spread > maxSpread ? maxSpread / spread : 1;
        for (const position of layout.values()) position.y *= squeeze;
        return layout;
      }),
    [snapshots, x, radius, maxSpread]
  );
  const swarmHalf = React.useMemo(
    () =>
      Math.max(
        radius,
        ...layouts.flatMap((layout) => [...layout.values()].map((p) => Math.abs(p.y)))
      ) +
      radius +
      4,
    [layouts, radius]
  );
  const positions = layouts[index];
  const centerY = LABEL_BAND + swarmHalf;
  const axisY = centerY + swarmHalf;
  const height = axisY + AXIS_SPACE;
  const ticks = x.ticks(width < 480 ? 4 : 6);
  const extremes = [snapshot.largest, snapshot.smallest];

  const hoveredPosition = hovered ? positions.get(hovered.fips) : undefined;

  return (
    <StoryFigure
      bare
      title={
        <>
          {snapshot.cap.toLocaleString("en-US")}-seat House
          <span className="font-normal text-story-ink-2"> · {labels[index]}</span>
        </>
      }
      subtitle="People per representative in each state, relative to the national average"
      source="2020 Census apportionment counts; Method of Equal Proportions"
      table={{
        caption: `District size by state at ${snapshot.cap} seats`,
        columns: [
          { key: "state", label: "State" },
          { key: "seats", label: "Seats", numeric: true },
          { key: "perSeat", label: "People per seat", numeric: true },
          { key: "deviation", label: "vs. average", numeric: true },
        ],
        rows: [...snapshot.states]
          .sort((a, b) => b.perSeat - a.perSeat)
          .map((state) => ({
            state: state.name,
            seats: state.seats,
            perSeat: Math.round(state.perSeat),
            deviation: formatPercent(state.deviation),
          })),
      }}
    >
      <div ref={ref} className="relative" onPointerLeave={() => setHovered(null)}>
        {width > 0 ? (
          <svg
            width={width}
            height={height}
            role="img"
            aria-label={`At ${snapshot.cap} seats, district sizes range from ${formatPeople(snapshot.smallest.perSeat)} in ${snapshot.smallest.name} to ${formatPeople(snapshot.largest.perSeat)} in ${snapshot.largest.name}.`}
          >
            <g transform={`translate(${MARGIN_X},0)`}>
              <AxisX
                x={x}
                ticks={ticks}
                format={formatPercent}
                y={axisY}
                grid
              />
              <line
                x1={x(0)}
                x2={x(0)}
                y1={20}
                y2={axisY}
                stroke={INK.secondary}
                strokeWidth={1}
              />
              <text
                x={x(0)}
                y={12}
                textAnchor="middle"
                fontSize={12}
                fill={INK.secondary}
              >
                National average · {formatPeople(snapshot.average)}
              </text>
              <g>
                {snapshot.states.map((state) => {
                  const position = positions.get(state.fips) ?? { x: 0, y: 0 };
                  const isHovered = hovered?.fips === state.fips;
                  return (
                    <circle
                      key={state.fips}
                      r={isHovered ? radius + 1.5 : radius}
                      fill={seriesColor(0)}
                      stroke={isHovered ? INK.primary : INK.surface}
                      strokeWidth={2}
                      style={{
                        transform: `translate(${position.x}px, ${centerY + position.y}px)`,
                        transition: reducedMotion
                          ? undefined
                          : "transform 750ms cubic-bezier(0.2, 0.7, 0.2, 1)",
                      }}
                      onPointerEnter={() => setHovered(state)}
                    >
                      <title>{`${state.name}: ${formatPeople(state.perSeat)} per seat`}</title>
                    </circle>
                  );
                })}
              </g>
              {!hovered
                ? extremes.map((state) => {
                    const position = positions.get(state.fips);
                    if (!position) return null;
                    // Labels extend outward from their dot (away from the
                    // other extreme) so they never meet in the middle; they
                    // flip inward only when the chart edge is too close.
                    const right = state.deviation > 0;
                    const labelWidth = estimateLabelWidth(state.name);
                    const outwardFits = right
                      ? position.x + labelWidth <= plotWidth
                      : position.x - labelWidth >= 0;
                    const align = right === outwardFits ? "start" : "end";
                    const dotTop = centerY + position.y - radius - 1;
                    return (
                      <Annotation
                        key={`${index}-${state.fips}`}
                        x={position.x}
                        y={dotTop}
                        dx={0}
                        dy={LABEL_BAND - 6 - dotTop}
                        align={align}
                        detail={formatPeople(state.perSeat)}
                      >
                        {state.name}
                      </Annotation>
                    );
                  })
                : null}
            </g>
          </svg>
        ) : (
          <div style={{ height: LABEL_BAND + 200 }} />
        )}
        {hovered && hoveredPosition ? (
          <ChartTooltip
            x={MARGIN_X + hoveredPosition.x}
            y={centerY + hoveredPosition.y}
            width={width}
          >
            <div className="font-semibold">{hovered.name}</div>
            <div className="mt-0.5 tabular-nums text-story-ink-2">
              {hovered.seats.toLocaleString("en-US")} seats ·{" "}
              {formatPeople(hovered.perSeat)} per seat
            </div>
            <div className="tabular-nums text-story-ink-2">
              {formatPercent(hovered.deviation)} vs. national average
            </div>
          </ChartTooltip>
        ) : null}
      </div>
    </StoryFigure>
  );
}

/**
 * Deterministic beeswarm: place dots in x order, each at the smallest
 * vertical offset (alternating above and below) that clears every dot
 * already placed within one diameter.
 */
function dodge<T extends { fips: string }>(
  items: T[],
  xOf: (item: T) => number,
  spacing: number
): Map<string, { x: number; y: number }> {
  const sorted = [...items].sort((a, b) => xOf(a) - xOf(b) || a.fips.localeCompare(b.fips));
  const placed: Array<{ x: number; y: number }> = [];
  const result = new Map<string, { x: number; y: number }>();
  for (const item of sorted) {
    const px = xOf(item);
    const neighbors = placed.filter((p) => Math.abs(p.x - px) < spacing);
    let y = 0;
    for (let k = 0; k < 200; k++) {
      const candidate = k === 0 ? 0 : Math.ceil(k / 2) * (k % 2 ? -1 : 1) * (spacing / 2);
      if (neighbors.every((p) => Math.hypot(p.x - px, p.y - candidate) >= spacing)) {
        y = candidate;
        break;
      }
    }
    const position = { x: px, y };
    placed.push(position);
    result.set(item.fips, position);
  }
  return result;
}

/** Approximate width of a 13px semibold sans label, for placement only. */
function estimateLabelWidth(text: string): number {
  return text.length * 7.4 + 4;
}

function formatPercent(value: number): string {
  const rounded = Math.round(value * 100);
  if (rounded === 0) return "0%";
  return `${rounded > 0 ? "+" : "−"}${Math.abs(rounded)}%`;
}

function formatPeople(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 10_000) return `${Math.round(value / 1_000)}K`;
  return Math.round(value).toLocaleString("en-US");
}
