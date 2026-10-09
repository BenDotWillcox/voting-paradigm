"use client";

import * as React from "react";

import { SWEEP_START, SWEEP_STOP } from "@/lib/apportionment-sweep";
import { INK } from "@/lib/story/palette";

import { useStateFocus } from "./state-focus";
import { averageAt, spreadAt, sweepData } from "./state-swarm";

/**
 * Act IV's charts: how far state averages stray from the national average at
 * every House size, the two gaps side by side at each proposed size, and how
 * other democracies compare. The sweep is computed in the
 * browser and matches the build's house-sizes.json at every size.
 */

/** The House sizes the act stops at, with the rule behind each. */
export const NAMED_SIZES = [
  { size: 435, label: "Today’s House" },
  { size: 573, label: "The Wyoming Rule" },
  { size: 692, label: "The cube-root rule" },
  { size: 1000, label: "A round thousand" },
  { size: 11_036, label: "The 30,000-person benchmark" },
] as const;

/** Salary plus the average Members' Representational Allowance (CRS, 2026). */
export const COST_PER_MEMBER = 174_000 + 1_928_107;

const percent = (share: number) => {
  if (share === 0) return "avg";
  const value = Math.abs(share) * 100;
  return `${share > 0 ? "+" : "−"}${value < 10 && Math.abs(value - Math.round(value)) > 0.05 ? value.toFixed(1) : Math.round(value)}%`;
};

/**
 * Every House size from 435 to 11,036 on a log scale: the band from the
 * lowest state average to the highest (each as a share of the national
 * average), and inside it ± the median state's gap, the band that holds
 * half the states. Drawn left to right through `reveal`; once drawn, a
 * cursor names the states setting each extreme at any size.
 */
export function EnvelopeChart({
  area,
  height,
  reveal,
}: {
  area: { left: number; width: number };
  height: number;
  reveal: number;
}) {
  const { states } = useStateFocus();
  const compact = area.width < 560;
  const plot = {
    left: area.left + (compact ? 34 : 50),
    right: area.left + area.width - (compact ? 10 : 24),
    // Phones: the title sits below the figure's unit label.
    top: compact ? 66 : 56,
    bottom: height - (compact ? 46 : 54),
  };
  const [lo, hi] = [-0.35, 0.45];
  const logStart = Math.log(SWEEP_START);
  const logStop = Math.log(SWEEP_STOP);
  const x = React.useCallback(
    (size: number) => plot.left + ((Math.log(size) - logStart) / (logStop - logStart)) * (plot.right - plot.left),
    [plot.left, plot.right, logStart, logStop]
  );
  const y = (share: number) => plot.bottom - ((share - lo) / (hi - lo)) * (plot.bottom - plot.top);
  const [hover, setHover] = React.useState<number | null>(null);

  // One column per pixel: the band keeps each column's widest extremes, so
  // no spike is lost however many sizes share a pixel.
  const columns = React.useMemo(() => {
    const { sweep } = sweepData();
    const out: Array<{ x: number; high: number; low: number; typical: number }> = [];
    let current: (typeof out)[number] | null = null;
    let count = 0;
    for (const row of sweep) {
      const px = Math.round(x(row.size));
      if (!current || px !== current.x) {
        if (current) current.typical /= count;
        current = { x: px, high: row.high, low: row.low, typical: 0 };
        count = 0;
        out.push(current);
      }
      current.high = Math.max(current.high, row.high);
      current.low = Math.min(current.low, row.low);
      current.typical += row.typical;
      count++;
    }
    if (current) current.typical /= count;
    return out;
  }, [x]);

  const band = (upper: (c: (typeof columns)[number]) => number, lower: (c: (typeof columns)[number]) => number) =>
    columns.map((c, i) => `${i === 0 ? "M" : "L"}${c.x},${y(upper(c)).toFixed(1)}`).join("") +
    [...columns].reverse().map((c) => `L${c.x},${y(lower(c)).toFixed(1)}`).join("") +
    "Z";
  const line = (pick: (c: (typeof columns)[number]) => number) =>
    columns.map((c, i) => `${i === 0 ? "M" : "L"}${c.x},${y(pick(c)).toFixed(1)}`).join("");
  const clipId = React.useId();
  const { sweep } = sweepData();
  const spike = sweep[810 - SWEEP_START];
  const ticks = compact ? [-0.3, 0, 0.3] : [-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3, 0.4];
  // Labels sit clear of the lines: by the band's edges past 1,000 seats,
  // where the sawtooth has settled, and the typical band's label below it.
  const settled = columns.filter((c) => c.x >= x(1100) && c.x <= x(1700));
  const settledHigh = Math.max(...settled.map((c) => c.high));
  const settledLow = Math.min(...settled.map((c) => c.low));
  const drawn = reveal > 0.95;
  const nameOf = (fips: string) => states.find((s) => s.fips === fips)?.name ?? fips;
  const inspected = hover !== null ? sweep[hover - SWEEP_START] : null;

  const inspect = (event: React.PointerEvent<SVGRectElement>) => {
    const box = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!box) return;
    const px = event.clientX - box.left;
    const t = Math.max(0, Math.min(1, (px - plot.left) / (plot.right - plot.left)));
    setHover(Math.round(Math.exp(logStart + t * (logStop - logStart))));
  };

  return (
    <>
      <svg
        role="img"
        aria-label="How far state averages stray from the national average at every House size from 435 to 11,036 seats: the gap between the highest and lowest stays wide until about 1,000 seats, while the typical state's gap shrinks overall, unevenly."
        width="100%"
        height={height}
        className="pointer-events-none absolute inset-0 overflow-visible font-sans"
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={plot.left - 2} y={0} width={(plot.right - plot.left + 4) * reveal} height={height} />
          </clipPath>
        </defs>
        <text x={area.left} y={plot.top - 24} fontSize={12} fill={INK.muted}>
          {compact
            ? "State averages vs. the national average"
            : "Average people per seat by state, compared with the national average (2020 census)"}
        </text>
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={plot.left}
              x2={plot.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke={tick === 0 ? INK.secondary : INK.grid}
              strokeDasharray={tick === 0 ? "3 4" : undefined}
            />
            <text x={plot.left - 6} y={y(tick)} dy="0.32em" textAnchor="end" fontSize={11} fill={INK.muted} className="tabular-nums">
              {percent(tick)}
            </text>
          </g>
        ))}
        {NAMED_SIZES.map(({ size }) => (
          <g key={size}>
            <line x1={x(size)} x2={x(size)} y1={plot.top} y2={plot.bottom + 4} stroke={INK.axis} />
            <text
              x={x(size)}
              y={plot.bottom + 18}
              textAnchor={size === SWEEP_STOP ? "end" : size === SWEEP_START ? "start" : "middle"}
              fontSize={11}
              fill={INK.muted}
              className="tabular-nums"
            >
              {compact && (size === 573 || size === 692) ? "" : size.toLocaleString("en-US")}
            </text>
          </g>
        ))}
        <text x={(plot.left + plot.right) / 2} y={plot.bottom + 36} textAnchor="middle" fontSize={11} fill={INK.muted}>
          House size, in seats (logarithmic scale)
        </text>
        <g clipPath={`url(#${clipId})`}>
          <path d={band((c) => c.high, (c) => c.low)} fill="color-mix(in srgb, var(--story-seat) 22%, transparent)" />
          <path
            d={band((c) => c.typical, (c) => -c.typical)}
            fill="color-mix(in srgb, var(--story-seat-focus) 35%, transparent)"
          />
          <path d={line((c) => c.high)} fill="none" stroke="var(--gap-more-3)" strokeWidth={1.5} />
          <path d={line((c) => c.low)} fill="none" stroke="var(--gap-fewer-3)" strokeWidth={1.5} />
        </g>
        <g style={{ opacity: drawn ? 1 : 0, transition: "opacity 400ms ease" }} fontSize={compact ? 11 : 12}>
          <text x={x(1100)} y={y(settledHigh) - 8} fill="var(--gap-more-3)" fontWeight={600}>
            Highest state average
          </text>
          <text x={x(1100)} y={y(settledLow) + 18} fill="var(--gap-fewer-3)" fontWeight={600}>
            Lowest state average
          </text>
          <text x={x(SWEEP_START) + 6} y={y(-0.075)} fill="var(--story-seat-focus)" fontWeight={600}>
            {compact ? "Typical state" : "Blue band: ± the median state’s gap"}
          </text>
          {!compact ? (
            <text x={x(SWEEP_START) + 6} y={y(-0.075) + 15} fill="var(--story-seat-focus)">
              Half the states lie inside it
            </text>
          ) : null}
          {!compact ? (
            <g>
              <circle cx={x(810)} cy={y(spike.high)} r={4} fill="var(--gap-more-3)" stroke={INK.surface} strokeWidth={2} />
              <text x={x(810) + 8} y={y(spike.high) - 6} fill={INK.primary} fontWeight={600}>
                810 seats: highest {percent(spike.high)}
              </text>
            </g>
          ) : null}
        </g>
        {inspected ? (
          <g>
            <line x1={x(inspected.size)} x2={x(inspected.size)} y1={plot.top} y2={plot.bottom} stroke={INK.primary} strokeWidth={1} />
            <circle cx={x(inspected.size)} cy={y(inspected.high)} r={4} fill="var(--gap-more-3)" stroke={INK.surface} strokeWidth={2} />
            <circle cx={x(inspected.size)} cy={y(inspected.low)} r={4} fill="var(--gap-fewer-3)" stroke={INK.surface} strokeWidth={2} />
          </g>
        ) : null}
        {/* The inspectable area, once the chart is drawn. */}
        {drawn ? (
          <rect
            x={plot.left}
            y={plot.top}
            width={plot.right - plot.left}
            height={plot.bottom - plot.top}
            fill="transparent"
            style={{ pointerEvents: "all", cursor: "crosshair" }}
            onPointerMove={inspect}
            onPointerDown={inspect}
            onPointerLeave={() => setHover(null)}
          />
        ) : null}
      </svg>
      {inspected ? (
        <div
          role="status"
          className="pointer-events-none absolute z-10 w-max max-w-64 rounded-md bg-story-surface px-3 py-2 font-sans text-xs text-story-ink shadow-md ring-1 ring-story-rule"
          style={{
            left: x(inspected.size),
            top: plot.top,
            transform: `translateX(${x(inspected.size) > (plot.left + plot.right) / 2 ? "calc(-100% - 10px)" : "10px"})`,
          }}
        >
          <p className="font-semibold tabular-nums">{inspected.size.toLocaleString("en-US")} seats</p>
          <p className="tabular-nums" style={{ color: "var(--gap-more-3)" }}>
            Highest: {nameOf(inspected.largest.fips)} {percent(inspected.high)} · {inspected.largest.seats} seat
            {inspected.largest.seats === 1 ? "" : "s"}
          </p>
          <p className="tabular-nums" style={{ color: "var(--gap-fewer-3)" }}>
            Lowest: {nameOf(inspected.smallest.fips)} {percent(inspected.low)} · {inspected.smallest.seats} seat
            {inspected.smallest.seats === 1 ? "" : "s"}
          </p>
          <p className="text-story-ink-2 tabular-nums">Median state’s gap: ±{(inspected.typical * 100).toFixed(1)}%</p>
        </div>
      ) : null}
    </>
  );
}

/** Pew Research Center's 2018 OECD comparison, people per lower-house seat. */
const PEERS = [
  { name: "United States", value: 747_000, about: true },
  { name: "Japan", value: 272_108, about: false },
  { name: "Mexico", value: 247_965, about: false },
  { name: "Iceland", value: 5_500, about: true },
] as const;

/** People per lower-house seat: the United States against its peers (2018). */
export function PeersChart({ area, height }: { area: { left: number; width: number }; height: number }) {
  const compact = area.width < 560;
  const [entered, setEntered] = React.useState(false);
  React.useEffect(() => {
    const frame = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(frame);
  }, []);
  const labelWidth = compact ? 96 : 140;
  const valueWidth = compact ? 104 : 96;
  const barMax = area.width - labelWidth - valueWidth - 16;
  const rowHeight = compact ? 34 : 46;
  const top = Math.max(40, (height - rowHeight * PEERS.length) / 2);

  return (
    <div
      className="pointer-events-none absolute font-sans"
      style={{ left: area.left, top: 0, width: area.width, height }}
      role="img"
      aria-label="People per lower-house seat in 2018: United States about 747,000, Japan 272,108, Mexico 247,965, Iceland about 5,500 (Pew Research Center)."
    >
      <p className="absolute left-0 text-xs text-story-muted" style={{ top: top - 32 }}>
        People per lower-house seat, 2018 · highest and lowest of the 35 OECD countries
      </p>
      {PEERS.map((peer, i) => (
        <div key={peer.name} className="absolute inset-x-0 flex items-center" style={{ top: top + i * rowHeight, height: rowHeight }}>
          <span className="shrink-0 pr-3 text-right text-sm" style={{ width: labelWidth, color: i === 0 ? INK.primary : INK.secondary, fontWeight: i === 0 ? 700 : 500 }}>
            {peer.name}
          </span>
          <span
            className="h-[55%] shrink-0 rounded-sm transition-[width] duration-700 ease-out"
            style={{
              width: entered ? Math.max(3, (peer.value / PEERS[0].value) * barMax) : 0,
              background: i === 0 ? "var(--gap-more-3)" : "var(--story-seat)",
              transitionDelay: `${i * 90}ms`,
            }}
          />
          <span className="shrink-0 pl-2 text-sm tabular-nums" style={{ color: i === 0 ? INK.primary : INK.secondary, fontWeight: i === 0 ? 700 : 400 }}>
            {peer.about ? "about " : ""}
            {peer.value.toLocaleString("en-US")}
          </span>
        </div>
      ))}
    </div>
  );
}

/** The comparison strip's height: a header and one row per size shown. */
export function sizeStripHeight(compact: boolean): number {
  return compact ? 72 : 136;
}

/**
 * Both gaps at every proposed size, kept on screen while the swarm moves:
 * the average people per seat (and its change from 435), the typical
 * state's gap, and the highest ÷ lowest state average. Phones show today's
 * House and the current size.
 */
export function SizeStrip({
  area,
  current,
  compact,
}: {
  area: { left: number; width: number };
  current: number;
  compact: boolean;
}) {
  const rows = compact ? NAMED_SIZES.filter(({ size }) => size === 435 || size === current) : NAMED_SIZES;
  const base = averageAt(435);
  return (
    <table
      className="absolute bottom-0 font-sans text-[11px] leading-tight tabular-nums sm:text-xs"
      style={{ left: area.left, width: area.width }}
      aria-label="The two gaps at each proposed House size, 2020 census"
    >
      <thead>
        <tr className="text-story-muted">
          <th className="pb-1 text-left font-normal">Seats</th>
          <th className="pb-1 text-right font-normal">Average per seat</th>
          <th className="pb-1 text-right font-normal">vs. 435</th>
          <th className="pb-1 text-right font-normal">{compact ? "Typical" : "Typical state’s gap"}</th>
          <th className="pb-1 text-right font-normal">{compact ? "High ÷ low" : "Highest ÷ lowest"}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ size, label }) => {
          const row = spreadAt(size);
          const average = averageAt(size);
          const here = size === current;
          return (
            <tr
              key={size}
              className={here ? "bg-story-surface font-semibold text-story-ink" : "text-story-ink-2"}
              aria-current={here ? "true" : undefined}
            >
              <td className="py-0.5 pl-1 text-left">
                {size.toLocaleString("en-US")}
                {compact ? null : <span className="font-normal text-story-muted"> · {label}</span>}
              </td>
              <td className="py-0.5 text-right">{Math.round(average).toLocaleString("en-US")}</td>
              <td className="py-0.5 text-right">
                {size === 435 ? "—" : `−${Math.round((1 - average / base) * 100 + 1e-9)}%`}
              </td>
              <td className="py-0.5 text-right">±{(row.typical * 100).toFixed(1)}%</td>
              <td className="py-0.5 pr-1 text-right">{row.ratio.toFixed(2)}×</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
