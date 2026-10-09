import * as React from "react";

import { AxisX, AxisY } from "@/components/story/chart";
import type { EssayApportionment } from "@/lib/apportionment/essay-data";
import { INK } from "@/lib/story/palette";

/** People per House seat at one census. */
export interface PerSeatPoint {
  year: number;
  perSeat: number;
}

const FIRST = 1790;
const LAST = 2020;
const MAX = 800_000;
/** The census whose apportionment brought the House to 435, where it has stayed. */
export const FREEZE_YEAR = 1910;

/**
 * People per seat at every census. Through 1910 that is the national
 * resident population over the seats (the only measure for the whole run);
 * from 1920, while the House is frozen, it is the Census Bureau's own average
 * apportionment population per representative, which ends at 761,169.
 */
export function perSeatSeries(history: readonly EssayApportionment[]): PerSeatPoint[] {
  return history
    .filter((a) => a.year >= FIRST)
    .map((a) => {
      const perSeat = a.year > FREEZE_YEAR ? a.apportionmentPerSeat : a.residentPerSeat;
      if (perSeat === null) throw new Error(`No people-per-seat figure for ${a.year}`);
      return { year: a.year, perSeat: Math.round(perSeat) };
    });
}

export const PER_SEAT_NOTE =
  "People per seat: U.S. resident population ÷ House seats through 1910; from 1920, the Census Bureau’s average apportionment population per representative.";

export interface PerSeatLayout {
  x: (year: number) => number;
  y: (perSeat: number) => number;
  left: number;
  right: number;
  top: number;
  bottom: number;
  compact: boolean;
  /** Where the shrunken chamber lands: the freeze band's legend icon. */
  icon: { left: number; top: number; width: number };
}

/** The chart's plot area within its box (box pixels), right of any caption. */
export function perSeatLayout(area: { left: number; width: number; height: number }): PerSeatLayout {
  const compact = area.width < 560;
  const margin = compact
    ? { top: 40, right: 14, bottom: 30, left: 38 }
    : { top: 52, right: 92, bottom: 36, left: 66 };
  const left = area.left + margin.left;
  const right = area.left + area.width - margin.right;
  const top = margin.top;
  const bottom = Math.max(top + 40, area.height - margin.bottom);
  const x = (year: number) => left + ((year - FIRST) / (LAST - FIRST)) * (right - left);
  const y = (perSeat: number) => bottom - (perSeat / MAX) * (bottom - top);
  const width = compact ? 60 : 100;
  return { x, y, left, right, top, bottom, compact, icon: { left: x(FREEZE_YEAR) + 10, top: top + 8, width } };
}

const PRE = INK.secondary;
const FROZEN = "var(--gap-more-3)";
const X_TICKS = [1790, 1850, 1910, 1970, 2020];
const Y_TICKS = [0, 200_000, 400_000, 600_000, 800_000];

/**
 * People per House seat, census by census: a line that climbs gently while
 * the House grows, then steeply across the band where it is fixed at 435.
 * The line is drawn through `drawTo` (a fractional year), so the figure can
 * scrub it with the scroll.
 */
export function PerSeatChart({
  layout,
  points,
  drawTo,
  reveal,
  pinned,
  width,
  height,
}: {
  layout: PerSeatLayout;
  points: readonly PerSeatPoint[];
  drawTo: number;
  /** 0..1: the axes and the freeze band fade in as the chamber lands. */
  reveal: number;
  /** Censuses whose values stay labeled once drawn (the newest always is). */
  pinned: readonly number[];
  width: number;
  height: number;
}) {
  const { x, y, compact } = layout;
  const drawn = points.filter((p) => p.year <= drawTo);
  const next = points.find((p) => p.year > drawTo);
  const last = drawn[drawn.length - 1];
  // The moving head, between the last census drawn and the next.
  const head =
    last && next
      ? {
          year: drawTo,
          perSeat: last.perSeat + ((next.perSeat - last.perSeat) * (drawTo - last.year)) / (next.year - last.year),
        }
      : null;
  const line = head ? [...drawn, head] : drawn;
  const path = (part: readonly PerSeatPoint[]) =>
    part.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.year).toFixed(1)},${y(p.perSeat).toFixed(1)}`).join("");
  const pre = line.filter((p) => p.year <= FREEZE_YEAR);
  const frozen = line.filter((p) => p.year >= FREEZE_YEAR);
  const format = (v: number) => (compact && v >= 1000 ? `${v / 1000}k` : v.toLocaleString("en-US"));
  const labeled = drawn.filter((p) => p === last || pinned.includes(p.year));
  const freezeX = x(FREEZE_YEAR);
  const halo = { stroke: INK.surface, strokeWidth: 4, strokeLinejoin: "round" as const, paintOrder: "stroke" as const };
  const first = points[0];
  const final = points[points.length - 1];

  return (
    <svg
      width={width}
      height={height}
      role="img"
      aria-label={`People per House seat at each census, 1790 to 2020: ${first.perSeat.toLocaleString("en-US")} in ${first.year}, rising to ${final.perSeat.toLocaleString("en-US")} in ${final.year}. The House has had 435 seats since the ${FREEZE_YEAR} census.`}
      className="pointer-events-none absolute inset-0 overflow-visible font-sans"
    >
      <g style={{ opacity: reveal }}>
        {/* The years the House has been fixed at 435. */}
        <rect
          x={freezeX}
          y={layout.top - 8}
          width={layout.right - freezeX + (compact ? 6 : 12)}
          height={layout.bottom - layout.top + 8}
          fill="color-mix(in srgb, var(--gap-more-3) 8%, transparent)"
        />
        <line x1={freezeX} x2={freezeX} y1={layout.top - 8} y2={layout.bottom} stroke={FROZEN} strokeOpacity={0.35} />
        {/* Beside the icon, or under it on phones, where the line's steep end
            would otherwise run through it. */}
        <text
          x={compact ? layout.icon.left + layout.icon.width / 2 : layout.icon.left + layout.icon.width + 8}
          y={compact ? layout.icon.top + layout.icon.width * 0.5 + 14 : layout.icon.top + layout.icon.width * 0.36}
          textAnchor={compact ? "middle" : "start"}
          fontSize={compact ? 11 : 13}
          fontWeight={600}
          fill={FROZEN}
        >
          Fixed at 435{compact ? "" : " seats"}
        </text>
        <text x={layout.left - (compact ? 38 : 66)} y={layout.top - 22} fontSize={12} fill={INK.muted}>
          People per seat
        </text>
        <g transform={`translate(${layout.left},0)`}>
          <AxisY y={y} ticks={compact ? [0, 400_000, 800_000] : Y_TICKS} format={format} width={layout.right - layout.left} />
        </g>
        <line x1={layout.left} x2={layout.right} y1={layout.bottom} y2={layout.bottom} stroke={INK.axis} />
        <AxisX x={x} ticks={X_TICKS} y={layout.bottom} />
      </g>

      {pre.length > 1 ? (
        <path d={path(pre)} fill="none" stroke={PRE} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
      ) : null}
      {frozen.length > 1 ? (
        <path d={path(frozen)} fill="none" stroke={FROZEN} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
      ) : null}
      {drawn.map((p) => (
        <circle
          key={p.year}
          cx={x(p.year)}
          cy={y(p.perSeat)}
          r={compact ? 3.5 : 4.5}
          fill={p.year > FREEZE_YEAR ? FROZEN : PRE}
          stroke={INK.surface}
          strokeWidth={2}
        />
      ))}
      {labeled.map((p) => {
        const newest = p === last;
        // The newest value sits right of its point (above it on phones, and
        // near the end where the margin runs out); pinned ones sit below.
        const right = !compact && newest;
        const px = x(p.year);
        const py = y(p.perSeat);
        return (
          <text
            key={p.year}
            x={right ? px + 10 : newest ? px - 6 : px + 8}
            y={right ? py + 5 : newest ? py - 10 : py + 20}
            textAnchor={right || !newest ? "start" : "end"}
            fontSize={compact ? 11 : 13}
            fontWeight={newest ? 700 : 600}
            fill={newest ? INK.primary : INK.secondary}
            className="tabular-nums"
            {...halo}
          >
            {p.perSeat.toLocaleString("en-US")}
          </text>
        );
      })}
    </svg>
  );
}
