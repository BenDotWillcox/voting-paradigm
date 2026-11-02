"use client";

import * as React from "react";

import { blockDistrictColor } from "@/lib/block-map-projection";
import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";
import type { PowerDiagram, PowerFrame } from "@/lib/districting-explainer";
import { MAP_COLORS } from "@/lib/districts-palette";
import { WALKTHROUGH_COLORS, usePath } from "./layers";

const STATE = "26";

/** Cell edges are straight in the solver's plane, not on the conic map, so long edges are densified first. */
function ringPath(ring: [number, number][], projection: BlockMapProjection) {
  let d = "";
  ring.forEach((point, index) => {
    const next = ring[(index + 1) % ring.length];
    const pieces = Math.max(1, Math.ceil(Math.max(Math.abs(next[0] - point[0]), Math.abs(next[1] - point[1])) / 0.05));
    for (let piece = 0; piece < pieces; piece++) {
      const t = piece / pieces;
      const [x, y] = projection.projectPoint([point[0] + (next[0] - point[0]) * t, point[1] + (next[1] - point[1]) * t]);
      d += `${d ? "L" : "M"}${x.toFixed(3)} ${y.toFixed(3)}`;
    }
  });
  return `${d}Z`;
}

const dotPath = (points: [number, number][], projection: BlockMapProjection) =>
  points.map((point) => { const [x, y] = projection.projectPoint(point); return `M${x.toFixed(3)} ${y.toFixed(3)}l0 0`; }).join("");

/** Michigan's land outline as a clip path, so cells show only over the state. */
export const StateClip = React.memo(function StateClip({ id, overview, projection }: { id: string; overview: BlockMapCollection; projection: BlockMapProjection }) {
  const path = usePath(projection);
  return <defs><clipPath id={id}>{overview.features.map((feature, index) => <path key={index} d={path(feature) ?? ""} clipRule="evenodd" />)}</clipPath></defs>;
});

/** The exact power cells of one frame, in the explorer's district colors. */
export function PowerCells({ frame, projection, clipId, opacity = 0.62, highlight }: {
  frame: PowerFrame; projection: BlockMapProjection; clipId: string; opacity?: number; highlight?: number;
}) {
  const rings = React.useMemo(() => frame.cells.map((ring) => ring.length > 2 ? ringPath(ring, projection) : ""), [frame, projection]);
  return <g clipPath={`url(#${clipId})`}>
    {rings.map((d, district) => d && <path key={district} d={d} fill={blockDistrictColor(district, STATE)}
      fillOpacity={highlight === undefined || highlight === district ? opacity : opacity * 0.35}
      stroke={MAP_COLORS.line} strokeWidth={1.3} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />)}
  </g>;
}

/** Each weight drawn as a reach: a circle of radius √(wᵢ − min w) around its center. */
export function ReachCircles({ frame, projection, plane, highlight }: {
  frame: PowerFrame; projection: BlockMapProjection; plane: PowerDiagram["plane"]; highlight?: number;
}) {
  return <g fill="none">
    {frame.centers.map((center, district) => {
      const reach = frame.reachKm[district];
      if (reach <= 0) return null;
      const [x, y] = projection.projectPoint(center);
      const [ex, ey] = projection.projectPoint([center[0] + (reach * 1000) / plane.metersPerDegreeLon, center[1]]);
      const lit = district === highlight;
      return <circle key={district} cx={x} cy={y} r={Math.hypot(ex - x, ey - y)} stroke={lit ? MAP_COLORS.selection : MAP_COLORS.line}
        strokeOpacity={lit ? 0.95 : 0.5} strokeWidth={lit ? 2 : 1} strokeDasharray={lit ? undefined : "3 4"} vectorEffect="non-scaling-stroke" />;
    })}
  </g>;
}

/** Centers as dots, optionally with the path each one has traveled so far. */
export function PowerCenters({ frames, current, projection, trails = false }: { frames: PowerFrame[]; current: number; projection: BlockMapProjection; trails?: boolean }) {
  const frame = frames[current];
  const trailPaths = React.useMemo(() => trails ? frame.centers.map((_, district) => frames.slice(0, current + 1).map((item, index) => {
    const [x, y] = projection.projectPoint(item.centers[district]);
    return `${index ? "L" : "M"}${x.toFixed(3)} ${y.toFixed(3)}`;
  }).join("")) : [], [frames, current, projection, trails, frame]);
  const dots = dotPath(frame.centers, projection);
  return <g fill="none" strokeLinecap="round" strokeLinejoin="round">
    {trailPaths.map((d, district) => <path key={district} d={d} stroke={WALKTHROUGH_COLORS.edge} strokeOpacity={0.8} strokeWidth={1.4} vectorEffect="non-scaling-stroke" />)}
    <path d={dots} stroke={MAP_COLORS.casing} strokeWidth={10} vectorEffect="non-scaling-stroke" />
    <path d={dots} stroke={MAP_COLORS.line} strokeWidth={6} vectorEffect="non-scaling-stroke" />
  </g>;
}

/** Seeds as black dots over white, numbered in the order they were drawn. */
export function SeedMarks({ seeds, count, projection, numbered = true, latest }: {
  seeds: PowerDiagram["seeds"]; count: number; projection: BlockMapProjection; numbered?: boolean;
  /** The order of a seed just drawn, ringed so it stands out from the earlier ones. */
  latest?: number;
}) {
  const shown = seeds.slice(0, count);
  const dots = dotPath(shown.map((seed) => seed.point), projection);
  const ring = latest ? dotPath([seeds[latest - 1].point], projection) : "";
  return <g strokeLinecap="round">
    {ring && <>
      <path d={ring} fill="none" stroke={MAP_COLORS.selectionCasing} strokeWidth={30} vectorEffect="non-scaling-stroke" />
      <path d={ring} fill="none" stroke={MAP_COLORS.selection} strokeWidth={26} vectorEffect="non-scaling-stroke" />
      <path d={ring} fill="none" stroke={MAP_COLORS.selectionCasing} strokeWidth={21} vectorEffect="non-scaling-stroke" />
    </>}
    <path d={dots} fill="none" stroke={MAP_COLORS.selectionCasing} strokeWidth={13} vectorEffect="non-scaling-stroke" />
    <path d={dots} fill="none" stroke={MAP_COLORS.selection} strokeWidth={8} vectorEffect="non-scaling-stroke" />
    {numbered && shown.map((seed) => {
      const [x, y] = projection.projectPoint(seed.point);
      return <text key={seed.order} x={x + 7} y={y - 6} fontSize={15} fontWeight={700} fontFamily="var(--dd-mono)" fill={MAP_COLORS.selection}
        stroke={MAP_COLORS.selectionCasing} strokeWidth={3.5} strokeLinejoin="round" paintOrder="stroke">{seed.order}</text>;
    })}
  </g>;
}

/** Thirteen bars: each district's population minus the target, scaled to the largest gap shown. */
export function PopulationBars({ populations, target }: { populations: number[]; target: number }) {
  const deviations = populations.map((population) => population - target);
  const scale = Math.max(...deviations.map(Math.abs), 1e-9);
  return <div className="grid gap-1">
    <div className="dd-bars" role="img" aria-label={`District populations minus the target; the largest gap is ${scale.toLocaleString(undefined, { maximumFractionDigits: 2 })} people`}>
      {deviations.map((deviation, district) => <span key={district} className="dd-bar">
        <span style={{ height: `${(Math.abs(deviation) / scale) * 50}%`, background: blockDistrictColor(district, STATE),
          ...(deviation >= 0 ? { bottom: "50%" } : { top: "50%" }) }} />
      </span>)}
    </div>
    <p className="dd-meta flex justify-between font-mono"><span>scale ±{scale.toLocaleString(undefined, { maximumFractionDigits: scale < 10 ? 2 : 0 })}</span><span>0 = target</span></p>
  </div>;
}

/** One value per round or move, on a log scale unless told otherwise, with the current one marked. */
export function RoundTrace({ values: raw, current, label, log = true }: { values: number[]; current: number; label: string; log?: boolean }) {
  const width = 240, height = 44;
  const values = log ? raw.map((value) => Math.log10(Math.max(value, 1e-3))) : raw;
  const top = log ? Math.ceil(Math.max(...values)) : Math.max(...values), bottom = log ? Math.floor(Math.min(...values)) : 0;
  const x = (index: number) => (index / (values.length - 1)) * width;
  const y = (value: number) => 2 + (1 - (value - bottom) / Math.max(top - bottom, 1)) * (height - 4);
  const d = values.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(2)} ${y(value).toFixed(2)}`).join("");
  return <div className="grid gap-1">
    <svg viewBox={`0 0 ${width} ${height}`} className="h-11 w-full" preserveAspectRatio="none" aria-hidden="true">
      <path d={d} fill="none" stroke={WALKTHROUGH_COLORS.edge} strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
      <line x1={x(current)} x2={x(current)} y1={0} y2={height} stroke={MAP_COLORS.selection} strokeWidth={1} vectorEffect="non-scaling-stroke" />
    </svg>
    <p className="dd-meta flex justify-between font-mono"><span>1</span><span>{label}</span><span>{values.length}</span></p>
  </div>;
}
