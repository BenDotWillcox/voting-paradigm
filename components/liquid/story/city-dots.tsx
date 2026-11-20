"use client";

import * as React from "react";

import { ChartTooltip, useElementWidth } from "@/components/story/chart";
import { district as districtName } from "@/lib/liquid/format";
import type { BallotCode, StoryCity } from "@/lib/liquid/story-types";
import { DIVERGING, INK } from "@/lib/story/palette";
import { cn } from "@/lib/utils";

/** Colors of a ballot's outcome, shared by every figure that shows ballots. */
export const OUTCOME_COLOR = {
  match: DIVERGING.positive,
  contrary: DIVERGING.negative,
  none: INK.empty,
} as const;

/** How one dot is drawn: a color, filled (the resident's own) or a ring (someone else's). */
export interface DotLook {
  color: string;
  ring: boolean;
}

export function ballotLook(code: BallotCode): DotLook {
  switch (code) {
    case "M":
      return { color: OUTCOME_COLOR.match, ring: false };
    case "N":
      return { color: OUTCOME_COLOR.none, ring: false };
    case "m":
      return { color: OUTCOME_COLOR.match, ring: true };
    case "c":
      return { color: OUTCOME_COLOR.contrary, ring: true };
    case "n":
      return { color: OUTCOME_COLOR.none, ring: true };
  }
}

const COLUMNS = 10;
/** Gap between district blocks, in dot spacings. */
const BLOCK_GAP = 1.6;
const LABEL_HEIGHT = 20;

interface Layout {
  width: number;
  height: number;
  spacing: number;
  points: Array<{ x: number; y: number }>;
  labels: Array<{ x: number; y: number; district: number }>;
}

/**
 * Five district blocks of ten by ten: in one row on wide screens, three over
 * two on narrow ones. Inside a block, residents run in the city's drawing
 * order (by own turnout rate, highest first).
 */
function layout(city: StoryCity, width: number): Layout {
  const districts = city.design.districts;
  const perRow = width >= 560 ? districts : Math.ceil(districts / 2);
  const rows = Math.ceil(districts / perRow);
  const rowsPerBlock = Math.ceil(city.design.residents_per_district / COLUMNS);
  // Capped, so the city stays compact enough to pin above the text on a
  // phone; a narrower city is centered
  const spacing = Math.min(perRow === districts ? 12 : 9, width / (perRow * COLUMNS + (perRow - 1) * BLOCK_GAP));
  const blockWidth = COLUMNS * spacing;
  const blockHeight = rowsPerBlock * spacing;
  const rowGap = spacing * 1.5;

  const origin: Array<{ x: number; y: number }> = [];
  for (let d = 0; d < districts; d++) {
    const row = Math.floor(d / perRow);
    const inRow = Math.min(perRow, districts - row * perRow);
    const rowWidth = inRow * blockWidth + (inRow - 1) * BLOCK_GAP * spacing;
    const left = (width - rowWidth) / 2;
    const column = d - row * perRow;
    origin.push({
      x: left + column * (blockWidth + BLOCK_GAP * spacing),
      y: row * (LABEL_HEIGHT + blockHeight + rowGap) + LABEL_HEIGHT,
    });
  }

  const points: Array<{ x: number; y: number }> = new Array(city.district.length);
  const seen = new Array(districts).fill(0);
  for (const resident of city.order) {
    const d = city.district[resident];
    const slot = seen[d]++;
    points[resident] = {
      x: origin[d].x + (slot % COLUMNS) * spacing + spacing / 2,
      y: origin[d].y + Math.floor(slot / COLUMNS) * spacing + spacing / 2,
    };
  }
  return {
    width,
    height: Math.ceil(rows * (LABEL_HEIGHT + blockHeight) + (rows - 1) * rowGap),
    spacing,
    points,
    labels: origin.map((o, d) => ({ x: o.x, y: o.y - 7, district: d })),
  };
}

interface CityDotsProps {
  city: StoryCity;
  /** How each resident is drawn, by resident index. Memoize it. */
  looks: readonly DotLook[];
  /** Residents to keep at full strength; the rest fade. */
  focus?: ReadonlySet<number> | null;
  /** Ring each district's elected representative. */
  markRepresentatives?: boolean;
  /** What hovering a resident shows. */
  tooltip?: (resident: number) => React.ReactNode;
  ariaLabel: string;
  className?: string;
}

/**
 * The walkthrough's motif: the illustrative city, one dot per resident.
 * Static for now; how it moves comes with the page's design.
 */
export function CityDots({
  city,
  looks,
  focus,
  markRepresentatives = false,
  tooltip,
  ariaLabel,
  className,
}: CityDotsProps) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = React.useState<{ resident: number; x: number; y: number } | null>(null);
  const geometry = React.useMemo(() => (width > 0 ? layout(city, width) : null), [city, width]);
  const representatives = React.useMemo(() => new Set(city.representatives), [city.representatives]);

  const onMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!geometry || !tooltip) return;
    const box = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - box.left;
    const py = event.clientY - box.top;
    let best = -1;
    let bestDistance = geometry.spacing * 0.75;
    geometry.points.forEach((point, resident) => {
      const distance = Math.hypot(point.x - px, point.y - py);
      if (distance < bestDistance) {
        best = resident;
        bestDistance = distance;
      }
    });
    setHover(best >= 0 ? { resident: best, x: geometry.points[best].x, y: geometry.points[best].y } : null);
  };

  const outer = geometry ? geometry.spacing * 0.4 : 0;
  const ringWidth = Math.max(1.25, outer * 0.42);

  return (
    <div ref={ref} className={cn("relative w-full", className)}>
      {geometry ? (
        <svg
          width={geometry.width}
          height={geometry.height}
          role="img"
          aria-label={ariaLabel}
          onPointerMove={tooltip ? onMove : undefined}
          onPointerLeave={tooltip ? () => setHover(null) : undefined}
          className="block overflow-visible"
        >
          {geometry.labels.map((label) => (
            <text
              key={label.district}
              x={label.x}
              y={label.y}
              fontSize={11}
              fill={INK.muted}
              className="font-sans"
              aria-hidden="true"
            >
              {districtName(label.district)}
            </text>
          ))}
          {geometry.points.map((point, resident) => {
            const look = looks[resident];
            if (!look) return null;
            const faded = focus ? !focus.has(resident) : false;
            return (
              <g key={resident}>
                {markRepresentatives && representatives.has(resident) ? (
                  <circle
                    cx={point.x}
                    cy={point.y}
                    r={outer + Math.max(1.5, outer * 0.35)}
                    fill="none"
                    stroke={INK.primary}
                    strokeWidth={1}
                    opacity={faded ? 0.2 : 1}
                  />
                ) : null}
                <circle
                  cx={point.x}
                  cy={point.y}
                  r={outer - ringWidth / 2}
                  strokeWidth={ringWidth}
                  style={{
                    fill: look.ring ? "transparent" : look.color,
                    stroke: look.color,
                    opacity: faded ? 0.16 : 1,
                  }}
                />
              </g>
            );
          })}
          {hover ? (
            <circle
              cx={hover.x}
              cy={hover.y}
              r={outer + 2.5}
              fill="none"
              stroke={INK.primary}
              strokeWidth={1.5}
              pointerEvents="none"
            />
          ) : null}
        </svg>
      ) : (
        <div style={{ height: 120 }} />
      )}
      {hover && tooltip && geometry ? (
        <ChartTooltip x={hover.x} y={hover.y} width={geometry.width}>
          {tooltip(hover.resident)}
        </ChartTooltip>
      ) : null}
    </div>
  );
}

/** The key to the ballot dots: form says whose ballot, color says how it compares. */
export function BallotLegend({ className, compact = false }: { className?: string; compact?: boolean }) {
  const item = (look: DotLook, text: string) => (
    <span className="inline-flex items-center gap-1.5">
      <svg width={12} height={12} aria-hidden="true">
        <circle
          cx={6}
          cy={6}
          r={look.ring ? 4.2 : 5}
          strokeWidth={look.ring ? 2 : 0}
          style={{ fill: look.ring ? "transparent" : look.color, stroke: look.color }}
        />
      </svg>
      {text}
    </span>
  );
  return (
    <div className={cn("flex flex-wrap gap-x-4 gap-y-1.5 font-sans text-xs text-story-ink-2", className)}>
      {/* Form keys in ink, so they don't read as an outcome */}
      {item({ color: INK.secondary, ring: false }, compact ? "Own ballot" : "Their own ballot")}
      {item({ color: INK.secondary, ring: true }, compact ? "Someone else's" : "Someone else's ballot")}
      <span className="inline-flex items-center gap-1.5">
        <Swatch color={OUTCOME_COLOR.match} /> Matches them
      </span>
      <span className="inline-flex items-center gap-1.5">
        <Swatch color={OUTCOME_COLOR.contrary} /> Against them
      </span>
      <span className="inline-flex items-center gap-1.5">
        <Swatch color={OUTCOME_COLOR.none} /> No ballot
      </span>
    </div>
  );
}

function Swatch({ color }: { color: string }) {
  return <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: color }} />;
}

/** Count a level's codes into the three shares behind fidelity. */
export function tally(codes: string): { match: number; contrary: number; none: number; own: number } {
  let match = 0;
  let contrary = 0;
  let none = 0;
  let own = 0;
  for (const code of codes) {
    if (code === "M" || code === "m") match++;
    else if (code === "c") contrary++;
    else none++;
    if (code === "M" || code === "N") own++;
  }
  return { match, contrary, none, own };
}
