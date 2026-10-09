"use client";

import * as React from "react";

import { SWEEP_START, SWEEP_STOP, awardOrder, seatsAtSize, sizeSweep, type SizeSpread } from "@/lib/apportionment-sweep";
import { INK } from "@/lib/story/palette";
import { US_2020_APPORTIONMENT_POPULATIONS as POPULATIONS } from "@/lib/us-state-populations";

import { useStateFocus } from "./state-focus";
import { gapClassFor } from "./state-map";

const TOTAL = Object.values(POPULATIONS).reduce((sum, n) => sum + n, 0);

let sweepCache: { order: string[]; sweep: SizeSpread[] } | null = null;
/**
 * Every House size from 435 to 11,036 (computed once, on first use): the
 * award order and the inequality at each size. Matches house-sizes.json
 * exactly (scripts/check-apportionment-parity.mjs).
 */
export function sweepData(): { order: string[]; sweep: SizeSpread[] } {
  if (!sweepCache) {
    const order = awardOrder(POPULATIONS, SWEEP_STOP);
    sweepCache = { order, sweep: sizeSweep(POPULATIONS, order, SWEEP_START, SWEEP_STOP) };
  }
  return sweepCache;
}

export function spreadAt(size: number): SizeSpread {
  return sweepData().sweep[size - SWEEP_START];
}

export function seatsFor(size: number): Record<string, number> {
  return seatsAtSize(POPULATIONS, sweepData().order, size);
}

/** People per seat on average across the country at a House size. */
export function averageAt(size: number): number {
  return TOTAL / size;
}

/** "+30%", and one decimal under 10% ("+2.1%", "−0.2%") so near-ties still read. */
const signedPercent = (share: number) => {
  const percent = Math.abs(share) * 100;
  const digits = percent < 10 ? 1 : 0;
  if (Number(percent.toFixed(digits)) === 0) return "0%";
  return `${share > 0 ? "+" : "−"}${percent.toFixed(digits)}%`;
};

/**
 * People per seat in every state, one dot per state on one axis, colored as
 * on the picker, with the extremes and the reader's state labeled. In
 * people (`relative` off: 2020's House, Act III) or as a share above or
 * below the national average at any House `size` (Act IV), where the dots
 * glide as the size changes.
 */
export function StateSwarm({
  area,
  height,
  size,
  relative,
  nationalAverage,
  dim,
  spotlight,
}: {
  area: { left: number; width: number };
  height: number;
  size: number;
  relative: boolean;
  /** The 2020 national average per seat (the absolute plot's reference line). */
  nationalAverage: number;
  /** Recede behind a clip. */
  dim: boolean;
  /** Ring one state, e.g. Montana while its 1992 case is told. */
  spotlight?: string;
}) {
  const { states, focus } = useStateFocus();
  const compact = area.width < 560;
  const left = area.left + (compact ? 20 : 28);
  const right = area.left + area.width - (compact ? 20 : 28);
  const [lo, hi] = relative ? [-0.4, 0.4] : [500_000, 1_000_000];
  const average = relative ? averageAt(size) : nationalAverage;
  const [entered, setEntered] = React.useState(false);
  React.useEffect(() => {
    const frame = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  // Each state's people per seat at this size: the Census Bureau's own
  // figure for today's House, otherwise population over seats.
  const values = React.useMemo(() => {
    const seats = size === 435 ? Object.fromEntries(states.map((s) => [s.fips, s.seats])) : seatsFor(size);
    return states.map((state) => {
      const perSeat = size === 435 ? state.averagePerSeat : state.population / seats[state.fips];
      return { state, seats: seats[state.fips], perSeat, value: relative ? perSeat / average - 1 : perSeat };
    });
  }, [states, size, relative, average]);

  // A one-axis swarm: each dot takes the free row nearest the middle. Where
  // the states crowd together (big Houses), the dots shrink a little; where
  // they nearly agree (11,036 seats) no swarm fits, so they pile up in a
  // clump at the average, overlapping.
  const swarm = React.useMemo(() => {
    const x = (v: number) => left + ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * (right - left);
    const sorted = [...values].sort((a, b) => a.value - b.value);
    let radius = compact ? 6 : 9;
    const room = height * (compact ? 0.42 : 0.46);
    for (let attempt = 0; attempt < 3; attempt++) {
      const out: Array<{ entry: (typeof values)[number]; x: number; dy: number }> = [];
      for (const entry of sorted) {
        const px = x(entry.value);
        for (let k = 0; ; k++) {
          const dy = (k % 2 === 0 ? 1 : -1) * Math.ceil(k / 2) * radius * 2.1;
          if (out.every((p) => Math.hypot(p.x - px, p.dy - dy) >= radius * 2.05)) {
            out.push({ entry, x: px, dy });
            break;
          }
        }
      }
      const extent = Math.max(...out.map((p) => p.dy)) - Math.min(...out.map((p) => p.dy)) + radius * 2;
      if (extent <= room) return { points: out, radius, packed: false };
      radius *= 0.85;
    }
    const packed = sorted.map((entry, i) => ({ entry, x: x(entry.value), dy: (((i * 7) % 5) - 2) * radius * 0.9 }));
    return { points: packed, radius, packed: true };
  }, [values, left, right, lo, hi, compact, height]);

  const { points, radius, packed } = swarm;
  const above = Math.min(...points.map((p) => p.dy)) - radius;
  const below = Math.max(...points.map((p) => p.dy)) + radius;
  const header = compact ? 34 : 42;
  const labelRoom = compact ? 34 : 42;
  const block = header - above + below + labelRoom + 24 + (focus ? 40 : 0);
  const top = Math.max(4, (height - block) / 2);
  const center = top + header - above;
  const axisY = center + below + labelRoom;
  const placed = points.map((p) => ({ ...p.entry, x: p.x, y: center + p.dy }));
  const extremes = [placed[0], placed[placed.length - 1]];
  const labeled = new Set([...extremes.map((p) => p.state.fips), ...(focus ? [focus.fips] : [])]);
  const outward = extremes[1].x - extremes[0].x < (compact ? 160 : 260);
  const zeroX = left + ((relative ? 0 : nationalAverage) - lo) / (hi - lo) * (right - left);
  const ticks = relative ? [-0.4, -0.2, 0, 0.2, 0.4] : [500_000, 600_000, 700_000, 800_000, 900_000, 1_000_000];
  const tickX = (v: number) => left + ((v - lo) / (hi - lo)) * (right - left);
  const halo = { stroke: INK.surface, strokeWidth: 4, strokeLinejoin: "round" as const, paintOrder: "stroke" as const };
  const move = "transform 800ms cubic-bezier(0.2,0.7,0.2,1)";

  return (
    <svg
      role="img"
      aria-label={
        relative
          ? `People per House seat in each state with ${size.toLocaleString("en-US")} seats, relative to the national average: from ${extremes[0].state.name} (${signedPercent(extremes[0].value)}) to ${extremes[1].state.name} (${signedPercent(extremes[1].value)}).`
          : `People per House seat in each state after the 2020 census, from ${extremes[0].state.name} (${Math.round(extremes[0].perSeat).toLocaleString("en-US")}) to ${extremes[1].state.name} (${Math.round(extremes[1].perSeat).toLocaleString("en-US")}).`
      }
      width="100%"
      height={height}
      className="pointer-events-none absolute inset-0 overflow-visible font-sans transition-opacity duration-500"
      style={{ opacity: dim ? 0.14 : 1 }}
    >
      <text x={left} y={top + 12} fontSize={12} fill={INK.muted}>
        {relative
          ? compact
            ? `State averages vs. national, ${size.toLocaleString("en-US")} seats`
            : `Average people per seat by state, vs. the national average · ${size.toLocaleString("en-US")} seats, 2020 census`
          : compact
            ? "Average people per seat by state, 2020"
            : "Average people per House seat by state, 2020 census"}
      </text>
      <text x={zeroX} y={top + header - 10} textAnchor="middle" fontSize={compact ? 11 : 12} fill={INK.secondary} {...halo}>
        {relative ? "Average" : "U.S. average"} {Math.round(average).toLocaleString("en-US")}
      </text>
      <line x1={zeroX} x2={zeroX} y1={top + header - 4} y2={axisY} stroke={INK.secondary} strokeDasharray="3 4" />
      <line x1={left} x2={right} y1={axisY} y2={axisY} stroke={INK.axis} />
      {ticks.map((tick) => (
        <g key={`${relative}-${tick}`}>
          <line x1={tickX(tick)} x2={tickX(tick)} y1={axisY} y2={axisY + 4} stroke={INK.axis} />
          <text x={tickX(tick)} y={axisY + 18} textAnchor="middle" fontSize={11} fill={INK.muted} className="tabular-nums">
            {relative
              ? tick === 0
                ? "avg"
                : `${tick > 0 ? "+" : "−"}${Math.round(Math.abs(tick) * 100)}%`
              : compact
                ? `${tick / 1000}k`
                : tick.toLocaleString("en-US")}
          </text>
        </g>
      ))}
      {placed.map(({ state, perSeat, value, x: px, y: py }, i) => {
        // Colored as on the picker; at other sizes, by the same share above
        // or below the average as the picker's classes are at 2020's.
        const { token } = gapClassFor(relative ? (1 + value) * nationalAverage : perSeat, nationalAverage);
        const ringed = state.fips === spotlight || state.fips === focus?.fips;
        return (
          <circle
            key={state.fips}
            cx={0}
            cy={0}
            r={radius}
            fill={`var(--gap-${token})`}
            fillOpacity={packed ? 0.7 : 1}
            stroke={ringed ? INK.primary : INK.surface}
            strokeWidth={ringed ? 2.5 : 1.5}
            style={{
              transform: entered ? `translate(${px.toFixed(1)}px, ${py.toFixed(1)}px)` : `translate(${zeroX.toFixed(1)}px, ${center.toFixed(1)}px)`,
              opacity: entered ? 1 : 0,
              transition: `${move} ${entered ? 0 : i * 8}ms, opacity 400ms ease ${i * 8}ms, fill 500ms ease`,
            }}
          />
        );
      })}
      {placed
        .filter((p) => labeled.has(p.state.fips))
        .map(({ state, seats, perSeat, value, x: px, y: py }) => {
          const extreme = extremes.some((p) => p.state.fips === state.fips);
          // The extremes are labeled just under their dots, reading toward
          // the middle; the reader's state under the axis, on a leader.
          // When the extremes sit close together, their labels point outward
          // instead, so they never cross.
          const isLeft = state.fips === extremes[0].state.fips;
          const anchor = !extreme ? "middle" : outward ? (isLeft ? "end" : "start") : px < zeroX ? "start" : "end";
          const lx = !extreme
            ? px
            : outward
              ? px + (isLeft ? -radius - 6 : radius + 6)
              : px + (px < zeroX ? -radius : radius);
          const ly = !extreme ? axisY + (compact ? 36 : 40) : outward ? py - 2 : py + radius + (compact ? 13 : 16);
          const strong = state.fips === spotlight;
          // Positioned by transform, so labels glide with their dots; a label
          // for a new extreme fades in once its dot has arrived.
          return (
            <g
              key={state.fips}
              className="motion-safe:animate-[story-fade-in_400ms_ease-out_500ms_both]"
              style={{ transform: `translate(${lx.toFixed(1)}px, ${ly.toFixed(1)}px)`, transition: move }}
            >
              {!extreme ? (
                <line x1={0} x2={0} y1={py + radius - ly} y2={compact ? -11 : -13} stroke={INK.secondary} strokeWidth={1} />
              ) : null}
              <text x={0} y={0} textAnchor={anchor} fontSize={compact ? 11 : 13} fontWeight={strong ? 700 : 600} fill={INK.primary} {...halo}>
                <tspan x={0}>{compact ? state.abbr : state.name}</tspan>
                <tspan x={0} dy={compact ? 13 : 16} fontWeight={400} fill={INK.secondary} className="tabular-nums">
                  {relative ? signedPercent(value) : Math.round(perSeat).toLocaleString("en-US")} · {seats} seat
                  {seats === 1 ? "" : "s"}
                </tspan>
              </text>
            </g>
          );
        })}
    </svg>
  );
}
