"use client";

import * as React from "react";
import { geoPath, type GeoProjection } from "d3-geo";
import type { Feature, Geometry } from "geojson";

import type { TractProperties } from "@/types/districting";

export type TractFeature = Feature<Geometry, TractProperties>;

interface TractCanvasFigureProps {
  /** Tract polygons; empty renders just the underlay and overlay. */
  tracts: TractFeature[];
  projection: GeoProjection;
  /** viewBox the projection was fitted to; overlays must use the same one. */
  viewBox: { width: number; height: number };
  /** Fill per tract, or null for no fill. Keep the identity stable. */
  fill: (tract: TractProperties) => string | null;
  /** Stroke color: a CSS color or a custom property such as `--border`. */
  stroke?: string | null;
  /** Stroke width in viewBox units. */
  strokeWidth?: number;
  opacity?: number;
  /** Called with the tract under the pointer (or null) and its viewBox point. */
  onHover?: (tract: TractProperties | null, point: [number, number] | null) => void;
  /** SVG drawn below the canvas, in viewBox units. */
  underlay?: React.ReactNode;
  /** SVG drawn above the canvas, in viewBox units. */
  children?: React.ReactNode;
  ariaLabel: string;
}

interface PreparedTract {
  properties: TractProperties;
  path: Path2D;
  bounds: [[number, number], [number, number]];
}

const GRID = 24;

/**
 * Tract-level map drawn on <canvas> instead of thousands of SVG nodes.
 *
 * Each tract is projected once into a cached Path2D, so restyling (fill
 * mode, theme, resize) is a cheap repaint. Hover uses a coarse bounding-box
 * grid plus `isPointInPath`, so no per-tract DOM or event listeners exist.
 * SVG under/overlays share the viewBox, keeping district outlines, centers,
 * and annotations crisp and accessible.
 */
export function TractCanvasFigure({
  tracts,
  projection,
  viewBox,
  fill,
  stroke = null,
  strokeWidth = 0.35,
  opacity = 1,
  onHover,
  underlay,
  children,
  ariaLabel,
}: TractCanvasFigureProps) {
  const wrapperRef = React.useRef<HTMLDivElement | null>(null);
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const [cssWidth, setCssWidth] = React.useState(0);
  const [themeTick, setThemeTick] = React.useState(0);

  const prepared = React.useMemo(() => prepareTracts(tracts, projection), [tracts, projection]);
  const grid = React.useMemo(() => buildGrid(prepared, viewBox), [prepared, viewBox]);

  React.useEffect(() => {
    const node = wrapperRef.current;
    if (!node) return;
    // Measure now so the first paint doesn't wait for an observer frame.
    setCssWidth(Math.round(node.getBoundingClientRect().width));
    const observer = new ResizeObserver((entries) => {
      setCssWidth(Math.round(entries[0]?.contentRect.width ?? 0));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  // Theme switches (class strategy) change the custom properties we resolve.
  React.useEffect(() => {
    const observer = new MutationObserver(() => setThemeTick((tick) => tick + 1));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || cssWidth === 0) return;
    const dpr = window.devicePixelRatio || 1;
    const scale = (cssWidth * dpr) / viewBox.width;
    canvas.width = Math.round(viewBox.width * scale);
    canvas.height = Math.round(viewBox.height * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (prepared.length === 0) return;

    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    ctx.globalAlpha = opacity;
    ctx.lineJoin = "round";
    const strokeColor = stroke ? resolveColor(canvas, stroke) : null;
    const fillCache = new Map<string, string>();
    for (const tract of prepared) {
      const tractFill = fill(tract.properties);
      if (tractFill) {
        let resolved = fillCache.get(tractFill);
        if (resolved === undefined) {
          resolved = resolveColor(canvas, tractFill);
          fillCache.set(tractFill, resolved);
        }
        ctx.fillStyle = resolved;
        ctx.fill(tract.path);
      }
    }
    if (strokeColor) {
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = strokeWidth;
      for (const tract of prepared) ctx.stroke(tract.path);
    }
  }, [prepared, fill, stroke, strokeWidth, opacity, cssWidth, viewBox, themeTick]);

  const hitContext = React.useMemo(() => {
    if (typeof document === "undefined") return null;
    return document.createElement("canvas").getContext("2d");
  }, []);

  const lastHover = React.useRef<TractProperties | null>(null);
  const handlePointerMove = React.useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!onHover || !hitContext || !wrapperRef.current) return;
      const rect = wrapperRef.current.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width) * viewBox.width;
      const y = ((event.clientY - rect.top) / rect.height) * viewBox.height;
      const hit = hitTest(grid, viewBox, hitContext, x, y);
      lastHover.current = hit;
      onHover(hit, hit ? [x, y] : null);
    },
    [grid, hitContext, onHover, viewBox]
  );
  const handlePointerLeave = React.useCallback(() => {
    if (lastHover.current === null) return;
    lastHover.current = null;
    onHover?.(null, null);
  }, [onHover]);

  const svgProps = {
    viewBox: `0 0 ${viewBox.width} ${viewBox.height}`,
    className: "absolute inset-0 h-full w-full",
    "aria-hidden": true as const,
  };

  return (
    <div
      ref={wrapperRef}
      className="relative w-full"
      style={{ aspectRatio: `${viewBox.width} / ${viewBox.height}` }}
      onPointerMove={onHover ? handlePointerMove : undefined}
      onPointerLeave={onHover ? handlePointerLeave : undefined}
    >
      {underlay ? <svg {...svgProps}>{underlay}</svg> : null}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 h-full w-full"
        role="img"
        aria-label={ariaLabel}
      />
      {children ? <svg {...svgProps}>{children}</svg> : null}
    </div>
  );
}

function prepareTracts(tracts: TractFeature[], projection: GeoProjection): PreparedTract[] {
  if (typeof Path2D === "undefined") return [];
  const path = geoPath(projection);
  const prepared: PreparedTract[] = [];
  for (const tract of tracts) {
    const d = path(tract);
    if (!d) continue;
    prepared.push({
      properties: tract.properties,
      path: new Path2D(d),
      bounds: path.bounds(tract),
    });
  }
  return prepared;
}

function buildGrid(
  prepared: PreparedTract[],
  viewBox: { width: number; height: number }
): PreparedTract[][] {
  const cells: PreparedTract[][] = Array.from({ length: GRID * GRID }, () => []);
  for (const tract of prepared) {
    const [[x0, y0], [x1, y1]] = tract.bounds;
    const [c0, r0] = cellOf(viewBox, x0, y0);
    const [c1, r1] = cellOf(viewBox, x1, y1);
    for (let r = r0; r <= r1; r++) {
      for (let c = c0; c <= c1; c++) cells[r * GRID + c].push(tract);
    }
  }
  return cells;
}

function hitTest(
  grid: PreparedTract[][],
  viewBox: { width: number; height: number },
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number
): TractProperties | null {
  if (x < 0 || y < 0 || x > viewBox.width || y > viewBox.height) return null;
  const [c, r] = cellOf(viewBox, x, y);
  const candidates = grid[r * GRID + c];
  for (let i = candidates.length - 1; i >= 0; i--) {
    const tract = candidates[i];
    const [[x0, y0], [x1, y1]] = tract.bounds;
    if (x < x0 || x > x1 || y < y0 || y > y1) continue;
    if (ctx.isPointInPath(tract.path, x, y)) return tract.properties;
  }
  return null;
}

function cellOf(
  viewBox: { width: number; height: number },
  x: number,
  y: number
): [number, number] {
  const clamp = (v: number) => Math.max(0, Math.min(GRID - 1, v));
  return [
    clamp(Math.floor((x / viewBox.width) * GRID)),
    clamp(Math.floor((y / viewBox.height) * GRID)),
  ];
}

/** Canvas can't read CSS custom properties; resolve `--name` / `var(--name)`. */
function resolveColor(element: Element, color: string): string {
  const match = /^(?:var\()?(--[\w-]+)\)?$/.exec(color.trim());
  if (!match) return color;
  return getComputedStyle(element).getPropertyValue(match[1]).trim() || "transparent";
}
