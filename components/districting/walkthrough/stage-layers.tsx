"use client";

import * as React from "react";

import { blockDistrictColor } from "@/lib/block-map-projection";
import { BLOCK_MAP_HEIGHT, BLOCK_MAP_WIDTH } from "@/lib/block-map-projection";
import type { BlockMapProjection } from "@/lib/block-map-projection";
import type { StageBlock } from "@/lib/districting-explainer";
import { MAP_COLORS } from "@/lib/districts-palette";
import { Outline, usePath } from "./layers";

/** The explorer's own Michigan district colors, by district id. */
export const DISTRICT_COLORS = Array.from({ length: 13 }, (_, district) => blockDistrictColor(district, "26"));

/**
 * The middle of a window's clip box, so the camera never shows where its blocks
 * were cut off. A negative shift slides the view west, putting the focus right
 * of center and clear of the docked card; it stays within the spare margin.
 */
export function innerBounds([w, s, e, n]: readonly [number, number, number, number], share = 0.75, shift = 0): [number, number, number, number] {
  const dx = ((e - w) * (1 - share)) / 2, dy = ((n - s) * (1 - share)) / 2;
  const slide = Math.max(-dx, Math.min(dx, shift * (e - w)));
  return [w + dx + slide, s + dy, e - dx + slide, n - dy];
}

/** Alternates a move's before and after while active: a beat of before, a longer hold on after. */
export function useBeforeAfter(active: boolean, reduced: boolean) {
  const [after, setAfter] = React.useState(true);
  React.useEffect(() => {
    if (!active || reduced) { setAfter(true); return; }
    setAfter(false);
    let showing = false, timer = 0;
    const flip = () => { showing = !showing; setAfter(showing); timer = window.setTimeout(flip, showing ? 2600 : 1300); };
    timer = window.setTimeout(flip, 1300);
    return () => window.clearTimeout(timer);
  }, [active, reduced]);
  return after;
}

/** The corner label for a before/after loop. */
export function PhaseBadge({ after }: { after: boolean }) {
  return <span className="dd-badge" data-phase={after ? "after" : "before"}>{after ? "After" : "Before"}</span>;
}

/** World units per screen pixel when the stage frames these bounds, for marks of a fixed screen size. */
export function unitsPerPixel([w, s, e, n]: readonly [number, number, number, number], projection: BlockMapProjection) {
  const corners = ([[w, s], [w, n], [e, s], [e, n]] as [number, number][]).map((point) => projection.projectPoint(point));
  const xs = corners.map(([x]) => x), ys = corners.map(([, y]) => y);
  return Math.max(Math.max(...xs) - Math.min(...xs), ((Math.max(...ys) - Math.min(...ys)) * BLOCK_MAP_WIDTH) / BLOCK_MAP_HEIGHT) / BLOCK_MAP_WIDTH;
}

/** A dashed line across a gap between blocks that do not touch, crossed out, with its length. */
export function NoTouch({ from, to, label, projection, unit }: {
  from: [number, number]; to: [number, number]; label: string; projection: BlockMapProjection; unit: number;
}) {
  const [x1, y1] = projection.projectPoint(from), [x2, y2] = projection.projectPoint(to);
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, r = 7 * unit, d = r * 0.7;
  // The label sits past the far end, clear of the piece the line starts from.
  const length = Math.hypot(x2 - x1, y2 - y1) || 1, ux = (x2 - x1) / length, uy = (y2 - y1) / length;
  const lx = x2 + ux * 10 * unit, ly = y2 + uy * 10 * unit + 4 * unit;
  return <g>
    <path d={`M${x1} ${y1}L${x2} ${y2}`} stroke={MAP_COLORS.selectionCasing} strokeWidth={5} vectorEffect="non-scaling-stroke" />
    <path d={`M${x1} ${y1}L${x2} ${y2}`} stroke={MAP_COLORS.selection} strokeWidth={2} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />
    <circle cx={mx} cy={my} r={r} fill="#ffffff" stroke={MAP_COLORS.selection} strokeWidth={2} vectorEffect="non-scaling-stroke" />
    <path d={`M${mx - d} ${my + d}L${mx + d} ${my - d}`} stroke={MAP_COLORS.selection} strokeWidth={2} vectorEffect="non-scaling-stroke" />
    <text x={lx} y={ly} textAnchor={ux < 0 ? "end" : "start"} fontSize={12 * unit} fontWeight={600} fontFamily="var(--dd-mono)" fill={MAP_COLORS.selection}
      stroke={MAP_COLORS.selectionCasing} strokeWidth={3 * unit} paintOrder="stroke">{label}</text>
  </g>;
}

/** Point bins for the stage canvas: district id + 1, so every block draws in its district's color. */
export function districtBins(labels: Uint8Array) {
  const bins = new Uint8Array(labels.length);
  for (let i = 0; i < labels.length; i++) bins[i] = labels[i] + 1;
  return bins;
}

export function Metrics({ rows }: { rows: [string, React.ReactNode][] }) {
  return <dl className="dd-card-metrics">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

/** A district as the explorer names it, with its color. */
export function District({ id }: { id: number }) {
  return <span className="inline-flex items-center gap-1.5"><span className="dd-district-chip" style={{ background: DISTRICT_COLORS[id] }} aria-hidden="true" />District {id + 1}</span>;
}

/** Window blocks filled by district at one stage: 0 power diagram, 1 after repair, 2 final. */
export const DistrictBlocks = React.memo(function DistrictBlocks({ blocks, projection, stage, overrides }: {
  blocks: StageBlock[]; projection: BlockMapProjection; stage: 0 | 1 | 2;
  /** Districts to show instead of the stage's, by block index, for a single move. */
  overrides?: ReadonlyMap<number, number>;
}) {
  const path = usePath(projection);
  const shapes = React.useMemo(() => blocks.map((block) => path({ type: "Feature", properties: {}, geometry: block.geometry }) ?? ""), [blocks, path]);
  return <g>
    {blocks.map((block, index) => {
      const district = overrides?.get(block.i) ?? block.labels[stage];
      return <path key={block.geoid} d={shapes[index]} fillRule="evenodd" fill={DISTRICT_COLORS[district]} fillOpacity={block.landM2 === 0 ? 0.4 : 0.72}
        stroke={MAP_COLORS.line} strokeOpacity={0.45} strokeWidth={0.6} vectorEffect="non-scaling-stroke" style={{ transition: "fill 450ms ease" }} />;
    })}
  </g>;
});

/** Black-over-white outlines around the blocks a step is about. */
export function FocusOutlines({ blocks, focus, projection }: { blocks: StageBlock[]; focus: readonly number[]; projection: BlockMapProjection }) {
  const set = React.useMemo(() => new Set(focus), [focus]);
  return <g>{blocks.filter((block) => set.has(block.i)).map((block) => <Outline key={block.geoid} geometry={block.geometry} projection={projection} />)}</g>;
}

/** Constant-size rings marking where moves happened. */
export function MoveMarks({ points, projection }: { points: [number, number][]; projection: BlockMapProjection }) {
  const d = points.map((point) => { const [x, y] = projection.projectPoint(point); return `M${x.toFixed(3)} ${y.toFixed(3)}l0 0`; }).join("");
  return <g fill="none" strokeLinecap="round">
    <path d={d} stroke={MAP_COLORS.selectionCasing} strokeWidth={15} vectorEffect="non-scaling-stroke" />
    <path d={d} stroke={MAP_COLORS.selection} strokeWidth={12} vectorEffect="non-scaling-stroke" />
    <path d={d} stroke={MAP_COLORS.selectionCasing} strokeWidth={6} vectorEffect="non-scaling-stroke" />
  </g>;
}
