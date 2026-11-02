"use client";

import * as React from "react";
import { geoPath } from "d3-geo";
import type { Feature, Geometry } from "geojson";

import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";
import type { ExplainerBlock } from "@/lib/districting-explainer";
import { MAP_COLORS } from "@/lib/districts-palette";

/** Walkthrough fills: neutral land and water, so map data colors stay the explorer's. */
export const WALKTHROUGH_COLORS = {
  land: "#f1f3ea",
  silhouette: "#e7eadb",
  water: "#d4eff3",
  highlight: "rgba(177, 235, 252, 0.6)",
  highlightWater: "rgba(0, 131, 143, 0.32)",
  /** Highlighted land beside water, where the blue highlight would read as water. */
  highlightLand: "rgba(173, 185, 72, 0.45)",
  /** Other states, shown only for context. */
  neighbor: "#e9eae4",
  edge: "#626a0f",
} as const;

export function usePath(projection: BlockMapProjection) {
  return React.useMemo(() => geoPath(projection).digits(6), [projection]);
}

function asFeature(geometry: Geometry): Feature<Geometry> {
  return { type: "Feature", properties: {}, geometry };
}

/** Michigan from the explorer's own land-focused outline, drawn without districts. */
export const Silhouette = React.memo(function Silhouette({ overview, coast, projection }: {
  overview: BlockMapCollection; coast: BlockMapCollection | null; projection: BlockMapProjection;
}) {
  const path = usePath(projection);
  return <g>
    {overview.features.map((feature, index) => <path key={index} d={path(feature) ?? ""} fill={WALKTHROUGH_COLORS.silhouette} fillRule="evenodd" />)}
    {coast?.features.map((feature, index) => <path key={index} d={path(feature) ?? ""} fill="none" stroke={MAP_COLORS.line} strokeOpacity={0.3} strokeWidth={0.6} vectorEffect="non-scaling-stroke" />)}
  </g>;
});

export const BlockShapes = React.memo(function BlockShapes({ blocks, projection, highlight, strong = false, landHighlight = WALKTHROUGH_COLORS.highlight, landFill = WALKTHROUGH_COLORS.land }: {
  blocks: Pick<ExplainerBlock, "geoid" | "landM2" | "geometry">[]; projection: BlockMapProjection; highlight?: ReadonlySet<string>; landHighlight?: string;
  /** Fill for land blocks that are not highlighted, such as a state's own tint. */
  landFill?: string;
  /** Outline highlighted blocks in solid ink instead of the faint block line. */
  strong?: boolean;
}) {
  const path = usePath(projection);
  return <g>
    {blocks.map((block) => {
      const water = block.landM2 === 0;
      const lit = highlight?.has(block.geoid);
      return <path key={block.geoid} d={path(asFeature(block.geometry)) ?? ""} fillRule="evenodd"
        fill={lit ? water ? WALKTHROUGH_COLORS.highlightWater : landHighlight : water ? WALKTHROUGH_COLORS.water : landFill}
        stroke={MAP_COLORS.line} strokeOpacity={lit && strong ? 1 : 0.55} strokeWidth={lit && strong ? 1.4 : 0.6} vectorEffect="non-scaling-stroke" />;
    })}
  </g>;
});

/** Black over white, the explorer's selection outline. */
export function Outline({ geometry, projection }: { geometry: Geometry; projection: BlockMapProjection }) {
  const path = usePath(projection);
  const d = path(asFeature(geometry)) ?? "";
  return <g fill="none" strokeLinejoin="round">
    <path d={d} stroke={MAP_COLORS.selectionCasing} strokeWidth={4.6} vectorEffect="non-scaling-stroke" />
    <path d={d} stroke={MAP_COLORS.selection} strokeWidth={2.2} vectorEffect="non-scaling-stroke" />
  </g>;
}

/** The block graph drawn as its dual: a line between the internal points of neighbors. */
export const GraphEdges = React.memo(function GraphEdges({ blocks, edges, projection, width = 0.8, opacity = 0.7, dash }: {
  blocks: ExplainerBlock[]; edges: readonly (readonly [number, number])[]; projection: BlockMapProjection;
  width?: number; opacity?: number; dash?: string;
}) {
  const d = React.useMemo(() => {
    const at = new Map(blocks.map((block) => [block.i, projection.projectPoint(block.point)]));
    let value = "";
    for (const [a, b] of edges) {
      const p = at.get(a), q = at.get(b);
      if (p && q) value += `M${p[0].toFixed(5)} ${p[1].toFixed(5)}L${q[0].toFixed(5)} ${q[1].toFixed(5)}`;
    }
    return value;
  }, [blocks, edges, projection]);
  return <path d={d} fill="none" stroke={WALKTHROUGH_COLORS.edge} strokeOpacity={opacity} strokeWidth={width} strokeDasharray={dash} strokeLinecap="round" vectorEffect="non-scaling-stroke" />;
});

/** Constant-size node dots: zero-length round-capped strokes ignore the zoom. */
export const GraphNodes = React.memo(function GraphNodes({ blocks, projection, size = 3 }: {
  blocks: ExplainerBlock[]; projection: BlockMapProjection; size?: number;
}) {
  const d = React.useMemo(() => blocks.map((block) => {
    const [x, y] = projection.projectPoint(block.point);
    return `M${x.toFixed(5)} ${y.toFixed(5)}l0 0`;
  }).join(""), [blocks, projection]);
  return <path d={d} fill="none" stroke={WALKTHROUGH_COLORS.edge} strokeWidth={size} strokeLinecap="round" vectorEffect="non-scaling-stroke" />;
});

export function boundsOf(geometry: Geometry, padding = 0): [number, number, number, number] {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const visit = (value: unknown): void => {
    if (Array.isArray(value) && typeof value[0] === "number") {
      w = Math.min(w, value[0]); e = Math.max(e, value[0]); s = Math.min(s, value[1]); n = Math.max(n, value[1]);
    } else if (Array.isArray(value)) value.forEach(visit);
  };
  visit("coordinates" in geometry ? geometry.coordinates : []);
  const dx = (e - w) * padding, dy = (n - s) * padding;
  return [w - dx, s - dy, e + dx, n + dy];
}

export function formatArea(m2: number) {
  return m2 >= 1_000_000 ? `${(m2 / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 1 })} km²`
    : `${(m2 / 10_000).toLocaleString(undefined, { maximumFractionDigits: 1 })} ha`;
}

/** Counties named in the walkthrough (2020 county FIPS within Michigan, 26). */
export const MICHIGAN_COUNTIES: Record<string, string> = {
  "029": "Charlevoix", "031": "Cheboygan", "063": "Huron", "095": "Luce", "097": "Mackinac", "163": "Wayne",
};
