"use client";

import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";
import { BLOCK_MAP_HEIGHT as HEIGHT, BLOCK_MAP_WIDTH as WIDTH } from "@/lib/block-map-projection";
import type { BlockMapProjection } from "@/lib/block-map-projection";
import { interpolateView, type ExplainerPoints } from "@/lib/districting-explainer";

/** Block points projected once per projection and shared by every chapter that draws them. */
const projected = new WeakMap<ExplainerPoints, WeakMap<BlockMapProjection, Float32Array>>();
function projectPoints(points: ExplainerPoints, projection: BlockMapProjection) {
  const byProjection = projected.get(points) ?? new WeakMap<BlockMapProjection, Float32Array>();
  projected.set(points, byProjection);
  let xy = byProjection.get(projection);
  if (!xy) {
    xy = new Float32Array(points.count * 2);
    for (let i = 0; i < points.count; i++) {
      const [x, y] = projection.projectPoint([points.lon[i], points.lat[i]]);
      xy[i * 2] = x; xy[i * 2 + 1] = y;
    }
    byProjection.set(projection, xy);
  }
  return xy;
}

/** West, south, east, north in degrees; null frames the whole state. */
export type StageBounds = readonly [number, number, number, number] | null;
type Camera = [number, number, number]; // world-space center x, center y, visible width

const STATE_CAMERA: Camera = [WIDTH / 2, HEIGHT / 2, WIDTH];

function cameraFor(bounds: StageBounds, projection: BlockMapProjection, padding: number): Camera {
  if (!bounds) return STATE_CAMERA;
  const [w, s, e, n] = bounds;
  const corners = [[w, s], [w, n], [e, s], [e, n]].map((point) => projection.projectPoint(point));
  const xs = corners.map((point) => point[0]), ys = corners.map((point) => point[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const width = Math.max(x1 - x0, ((y1 - y0) * WIDTH) / HEIGHT, 1e-4) * (1 + 2 * padding);
  return [(x0 + x1) / 2, (y0 + y1) / 2, width];
}

function transformFor([cx, cy, width]: Camera) {
  const k = WIDTH / width;
  return { k, x: WIDTH / 2 - cx * k, y: HEIGHT / 2 - cy * k };
}

/**
 * One chapter figure on the explorer's map plate. Children are SVG layers in
 * the state's world coordinates (the explorer's own Michigan projection); the
 * camera flies between step bounds with a smooth zoom, or jumps when the
 * viewer prefers reduced motion. Block points draw on a canvas above the
 * layers, and only on steps that show them.
 */
export function ExplainerStage({ projection, bounds, startBounds, padding = 0.12, points, showPoints = false, pointBins, binColors, card, cardAt, cardLive = true, cardWide = false, badge, label, fadeIn = false, overlay, children }: {
  projection: BlockMapProjection;
  bounds: StageBounds;
  /** A wider view to open on, held briefly before the camera flies to `bounds`. */
  startBounds?: StageBounds;
  padding?: number;
  points?: ExplainerPoints;
  showPoints?: boolean;
  /** Per-point bin (0 = not drawn), colored by binColors[bin - 1], instead of land/water. */
  pointBins?: Uint8Array;
  binColors?: readonly string[];
  card?: React.ReactNode;
  /** Where the card docks on wide screens; bottom left unless the figure needs that corner. */
  cardAt?: "top-left";
  /** Announce card changes; off while a time-lapse plays. */
  cardLive?: boolean;
  /** Let the card grow sideways so its values stay on one line instead of wrapping. */
  cardWide?: boolean;
  /** A small label pinned to the figure's top right, such as Before or After. */
  badge?: React.ReactNode;
  label: string;
  /** Fade the plate in on mount, for figures that change state instead of flying. */
  fadeIn?: boolean;
  /** SVG layers drawn above the block points, like markers that must stay visible. */
  overlay?: React.ReactNode;
  children: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  const groupRef = React.useRef<SVGGElement>(null);
  const overlayRef = React.useRef<SVGGElement>(null);
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const camera = React.useRef<Camera>(STATE_CAMERA);
  const opened = React.useRef(false);
  const holdUntil = React.useRef(0);
  const showPointsRef = React.useRef(showPoints);
  showPointsRef.current = showPoints;

  const world = React.useMemo(() => points ? projectPoints(points, projection) : null, [points, projection]);

  const draw = React.useCallback(() => {
    const view = transformFor(camera.current);
    const transform = `translate(${view.x} ${view.y}) scale(${view.k})`;
    groupRef.current?.setAttribute("transform", transform);
    overlayRef.current?.setAttribute("transform", transform);
    const canvas = canvasRef.current;
    if (!canvas || !points || !world) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.round(canvas.clientWidth * ratio), height = Math.round(canvas.clientHeight * ratio);
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, width, height);
    if (!showPointsRef.current) return;
    const scale = width / WIDTH;
    context.setTransform(scale, 0, 0, scale, 0, 0);
    const growth = Math.min(view.k, 6) ** 0.5;
    if (pointBins && binColors) {
      // Low bins first, so the strongest values draw on top.
      binColors.forEach((color, bin) => {
        context.fillStyle = color;
        for (let i = 0; i < points.count; i++) {
          if (pointBins[i] !== bin + 1) continue;
          const x = world[i * 2] * view.k + view.x, y = world[i * 2 + 1] * view.k + view.y;
          const size = (0.6 + Math.sqrt(points.population[i]) * 0.045) * growth;
          context.fillRect(x - size / 2, y - size / 2, size, size);
        }
      });
      return;
    }
    for (let pass = 0; pass < 2; pass++) {
      context.fillStyle = pass === 0 ? "rgba(0, 131, 143, 0.45)" : "rgba(70, 74, 59, 0.45)";
      for (let i = 0; i < points.count; i++) {
        if ((points.waterOnly[i] === 1) !== (pass === 0)) continue;
        const x = world[i * 2] * view.k + view.x, y = world[i * 2 + 1] * view.k + view.y;
        if (x < -4 || y < -4 || x > WIDTH + 4 || y > HEIGHT + 4) continue;
        const size = pass === 0 ? 0.9 : (0.45 + Math.sqrt(points.population[i]) * 0.045) * growth;
        context.fillRect(x - size / 2, y - size / 2, size, size);
      }
    }
  }, [points, world, pointBins, binColors]);

  React.useEffect(() => {
    const target = cameraFor(bounds, projection, padding);
    if (!opened.current) {
      opened.current = true;
      if (startBounds !== undefined && !reduced) { camera.current = cameraFor(startBounds, projection, padding); holdUntil.current = performance.now() + 1200; }
    }
    // A deadline, so a re-run effect (as in development) keeps the opening hold.
    const hold = Math.max(0, holdUntil.current - performance.now());
    const from = camera.current;
    if (reduced || from.every((value, index) => Math.abs(value - target[index]) < 1e-9)) {
      camera.current = target; draw(); return;
    }
    const path = interpolateView(from, target);
    const duration = holdUntil.current ? 2200 : Math.min(1800, Math.max(500, path.duration * 0.55));
    let frame = 0, started = 0;
    const step = (now: number) => {
      started ||= now;
      const t = Math.min(1, (now - started) / duration);
      const eased = t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
      camera.current = path.at(eased);
      draw();
      if (t < 1) frame = requestAnimationFrame(step);
    };
    draw();
    const timer = window.setTimeout(() => { frame = requestAnimationFrame(step); }, hold);
    return () => { window.clearTimeout(timer); cancelAnimationFrame(frame); };
  }, [bounds, startBounds, projection, padding, reduced, draw]);

  React.useEffect(() => { draw(); }, [showPoints, draw]);
  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(() => draw());
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [draw]);

  return (
    <div className="dd-map-area dd-chapter-stage">
      <div className={`dd-map-frame${fadeIn ? " dd-fade-in" : ""}`} role="img" aria-label={label}>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="absolute inset-0 h-full w-full" aria-hidden="true">
          <g ref={groupRef}>{children}</g>
        </svg>
        <canvas ref={canvasRef} aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full transition-opacity duration-500" style={{ opacity: showPoints ? 1 : 0 }} />
        {overlay && <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true"><g ref={overlayRef}>{overlay}</g></svg>}
      </div>
      {badge && <div className="dd-stage-badge" aria-live="polite">{badge}</div>}
      {card && <div className="dd-stage-card" data-at={cardAt} data-wide={cardWide || undefined} aria-live={cardLive ? "polite" : "off"}>{card}</div>}
    </div>
  );
}

/** An SVG layer that fades with its step instead of mounting and unmounting. */
export function StageLayer({ visible, children }: { visible: boolean; children: React.ReactNode }) {
  return <g style={{ opacity: visible ? 1 : 0, transition: "opacity 450ms ease", pointerEvents: "none" }} aria-hidden={!visible}>{children}</g>;
}
