"use client";

import * as React from "react";
import type { Geometry } from "geojson";

import { blockDistrictColor } from "@/lib/block-map-projection";
import type { ExtremeState } from "@/lib/districting-explainer";
import { MAP_COLORS } from "@/lib/districts-palette";

const WIDTH = 1000, HEIGHT = 620;
/** Neutral tints for enacted districts, so their shapes read without implying a match to computed colors. */
const MUTED = ["#e3e7d6", "#d3dbc2", "#eef0e6", "#cfd8dc", "#e6e2cf", "#dde6e8"];
/** Who drew each serving map, as reported in the chapter's sources. */
export const SERVING_MAP: Record<string, string> = {
  "37": "2023 Republican map", "17": "2021 Democratic map", "48": "2021 Republican map", "24": "2022 court-ordered redraw",
};

type Fit = (point: number[]) => [number, number];

/** Equirectangular scaled by the cosine of the middle latitude, fitted into a box. */
function fitTo([w, s, e, n]: readonly number[], [x0, y0, bw, bh]: readonly number[]): Fit {
  const k = Math.cos(((s + n) / 2) * (Math.PI / 180));
  const sx = (e - w) * k, sy = n - s;
  const scale = Math.min(bw / sx, bh / sy);
  const ox = x0 + (bw - sx * scale) / 2, oy = y0 + (bh - sy * scale) / 2;
  return ([lon, lat]) => [ox + (lon - w) * k * scale, oy + (n - lat) * scale];
}

function pathOf(geometry: Geometry, fit: Fit) {
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.type === "MultiPolygon" ? geometry.coordinates : [];
  return polygons.map((rings) => rings.map((ring) => ring.map((point, index) => {
    const [x, y] = fit(point);
    return `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join("") + "Z").join("")).join("");
}

function Districts({ state, side, fit, highlight }: { state: ExtremeState; side: "computed" | "enacted"; fit: Fit; highlight?: number }) {
  const features = state[side].features;
  const shapes = React.useMemo(() => features.map((feature) => pathOf(feature.geometry, fit)), [features, fit]);
  return <g strokeLinejoin="round">
    {shapes.map((d, index) => <path key={index} d={d} fillRule="evenodd"
      fill={side === "computed" ? blockDistrictColor(features[index].district, state.stateFips) : MUTED[index % MUTED.length]}
      fillOpacity={side === "computed" ? 0.78 : 1} stroke={side === "computed" ? MAP_COLORS.line : MAP_COLORS.selection}
      strokeOpacity={side === "computed" ? 0.55 : 0.9} strokeWidth={side === "computed" ? 0.6 : 0.9} />)}
    {highlight !== undefined && <>
      <path d={shapes[highlight]} fill="none" stroke={MAP_COLORS.selectionCasing} strokeWidth={4.5} />
      <path d={shapes[highlight]} fill="none" stroke={MAP_COLORS.selection} strokeWidth={2.2} />
    </>}
  </g>;
}

function Caption({ x, y, title, detail }: { x: number; y: number; title: string; detail: string }) {
  return <text x={x} y={y} fill={MAP_COLORS.label}>
    <tspan fontSize={17} fontWeight={600}>{title}</tspan>
    <tspan x={x} dy={18} fontSize={12} fontFamily="var(--dd-mono)" fillOpacity={0.75}>{detail}</tspan>
  </text>;
}

/** A figure that is not on Michigan's map: same frame and card as the explainer stage. */
export function PanelStage({ label, card, aside, children }: { label: string; card?: React.ReactNode; aside?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="dd-map-area dd-chapter-stage">
      <div className="dd-map-frame dd-fade-in" role="img" aria-label={label}>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="absolute inset-0 h-full w-full" aria-hidden="true">{children}</svg>
      </div>
      {card && <div className="dd-stage-card" aria-live="polite">{card}</div>}
      {aside && <div className="dd-stage-card" data-at="bottom-right" aria-live="polite">{aside}</div>}
    </div>
  );
}

const INK = "#2f3327";
const ordinal = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] ?? "th"}`;
/** Approximate width of a 12px mono label, for keeping labels apart. */
const textWidth = (text: string) => text.length * 7.2 + 6;
type Rect = [number, number, number, number];
type Note = { key: string; x: number; y: number; text: string; strong?: boolean };
type Placed = Note & { lx: number; ly: number; anchor: "start" | "end"; ax: number; ay: number };

/**
 * Where one map sits in its half, and where its labels go. A tall state is
 * pushed to the divider so its labels get a gutter on the outer side; a wide
 * state keeps its place and labels go in the bands above and below it.
 */
function halfLayout(state: ExtremeState, half: "left" | "right") {
  const box: Rect = half === "left" ? [24, 64, WIDTH / 2 - 48, HEIGHT - 88] : [WIDTH / 2 + 24, 64, WIDTH / 2 - 48, HEIGHT - 88];
  const [w, s, e, n] = state.bbox;
  const k = Math.cos(((s + n) / 2) * (Math.PI / 180));
  const scale = Math.min(box[2] / ((e - w) * k), box[3] / (n - s));
  const sw = (e - w) * k * scale, sh = (n - s) * scale;
  const tall = box[3] - sh < 90;
  const mapBox: Rect = tall ? (half === "left" ? [box[0] + box[2] - sw, box[1], sw, box[3]] : [box[0], box[1], sw, box[3]]) : box;
  const fit = fitTo(state.bbox, mapBox);
  const [x0, y0] = fit([w, n]), [x1, y1] = fit([e, s]);
  return { fit, box, shape: [x0, y0, x1, y1] as Rect, mode: tall ? half : "band" as "left" | "right" | "band" };
}

/** Labels off the map: stacked in a gutter, or spread along the bands above and below. */
function placeNotes(notes: Note[], layout: ReturnType<typeof halfLayout>): Placed[] {
  const { box, shape, mode } = layout;
  const [bx, by, bw, bh] = box, [sx0, sy0, sx1] = shape;
  if (mode !== "band") {
    const right = mode === "right";
    const lx = right ? sx1 + 16 : sx0 - 16;
    let last = -Infinity;
    return [...notes].sort((a, b) => a.y - b.y).map((note) => {
      const ly = Math.min(by + bh - 4, Math.max(note.y + 4, last + 18, by + 12));
      last = ly;
      return { ...note, lx, ly, anchor: right ? "start" : "end", ax: right ? lx - 4 : lx + 4, ay: ly - 4 };
    });
  }
  // Every label goes in the band above: the info boxes sit in both bottom corners.
  // A label that would collide moves up a row instead of sliding far from its point.
  const rows: number[] = [];
  return [...notes].sort((a, b) => a.x - b.x).map((note) => {
    const width = textWidth(note.text);
    const want = Math.min(bx + bw - width, Math.max(bx, note.x - width / 2));
    let row = rows.findIndex((cursor) => cursor <= want);
    if (row === -1) { rows.push(bx); row = rows.length - 1; }
    rows[row] = want + width + 12;
    const ly = Math.max(by + 12 + row * 17, sy0 - 12 - row * 17);
    return { ...note, lx: want, ly, anchor: "start" as const, ax: want + width / 2, ay: ly + 4 };
  });
}

/** City dots and the focus circle stay on the map; their labels sit outside it on leader lines. */
function Callouts({ state, side, layout }: { state: ExtremeState; side: "computed" | "enacted"; layout: ReturnType<typeof halfLayout> }) {
  const { fit } = layout;
  const { focus, leastCompact, cities } = state.callouts;
  const ring = Array.from({ length: 49 }, (_, index) => {
    const t = (index / 48) * 2 * Math.PI;
    const [x, y] = fit([focus.point[0] + (focus.radiusKm * Math.cos(t)) / (111.195 * Math.cos((focus.point[1] * Math.PI) / 180)), focus.point[1] + (focus.radiusKm * Math.sin(t)) / 111.195]);
    return `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join("") + "Z";
  const count = side === "enacted" ? focus.enacted : focus.computed;
  const notes: Note[] = cities.map((city) => {
    const [x, y] = fit(city.point);
    const isFocus = city.name === focus.city;
    return { key: city.name, x, y, strong: isFocus, text: isFocus ? `${city.name}: ${count} district${count === 1 ? "" : "s"}` : city.name };
  });
  if (side === "enacted") {
    const [x, y] = fit(leastCompact.labelPoint);
    notes.push({ key: "least", x, y, strong: true, text: `${ordinal(leastCompact.district)} district · ${leastCompact.pp.toFixed(2)}` });
  }
  const placed = placeNotes(notes, layout);
  return <g fontFamily="var(--dd-mono)">
    <path d={ring} fill="none" stroke={INK} strokeWidth={1.5} strokeDasharray="4 3" />
    {placed.map((note) => <path key={`leader-${note.key}`} d={`M${note.x.toFixed(1)} ${note.y.toFixed(1)}L${note.ax.toFixed(1)} ${note.ay.toFixed(1)}`}
      stroke={INK} strokeOpacity={0.7} strokeWidth={0.9} />)}
    {cities.map((city) => {
      const [x, y] = fit(city.point);
      return <circle key={city.name} cx={x} cy={y} r={city.name === focus.city ? 4.5 : 3.5} fill="#ffffff" stroke={INK} strokeWidth={1.6} />;
    })}
    {placed.map((note) => <text key={note.key} x={note.lx} y={note.ly} textAnchor={note.anchor} fontSize={12} fontWeight={note.strong ? 700 : 600}
      fill={note.key === "least" ? MAP_COLORS.selection : INK}>{note.text}</text>)}
  </g>;
}

/** One state's computed plan beside its serving map, at the same scale, least compact districts outlined. */
export function StatePair({ state }: { state: ExtremeState }) {
  const left = React.useMemo(() => halfLayout(state, "left"), [state]);
  const right = React.useMemo(() => halfLayout(state, "right"), [state]);
  const least = (values: number[]) => values.indexOf(Math.min(...values));
  return <>
    <Caption x={24} y={28} title="Computed" detail="House 435 · this method" />
    <Caption x={WIDTH / 2 + 24} y={28} title="Serving map" detail={`119th Congress · ${SERVING_MAP[state.stateFips]}`} />
    <path d={`M${WIDTH / 2} 16V${HEIGHT - 16}`} stroke={MAP_COLORS.line} strokeOpacity={0.25} />
    <Districts state={state} side="computed" fit={left.fit} highlight={least(state.computed.pp)} />
    <Districts state={state} side="enacted" fit={right.fit} highlight={state.callouts.leastCompact.index} />
    <Callouts state={state} side="computed" layout={left} />
    <Callouts state={state} side="enacted" layout={right} />
  </>;
}
