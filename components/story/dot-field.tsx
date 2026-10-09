"use client";

import * as React from "react";

import { observeThemeChanges, resolveCssColor } from "@/lib/canvas-color";
import type { SeatDot } from "@/lib/story/hemicycle";

import { useElementWidth, useReducedMotion } from "./chart";

/**
 * neutral: an ordinary seat; added: a quieter highlight; focus: the strong
 * one; empty: a seat not yet filled, drawn as a ring.
 */
export type DotTone = "empty" | "neutral" | "added" | "focus";
const TONE_ORDER: Record<DotTone, number> = { empty: -1, neutral: 0, added: 1, focus: 2 };

interface DotFieldProps {
  dots: readonly SeatDot[];
  /** Dot radius in normalized units (outer radius = 1), from the layout. */
  dotRadius: number;
  /**
   * Largest dot radius this field will ever show (normalized). The frame is
   * padded for it so edge dots never clip and the chamber doesn't rescale as
   * the dot size changes between layouts. Defaults to `dotRadius`.
   */
  reserveRadius?: number;
  /** Color role per dot. Keep the identity stable (memoize) to avoid redraws. */
  toneFor?: (dot: SeatDot) => DotTone;
  /** CSS colors (or custom properties) for each tone. */
  colors?: Partial<Record<DotTone, string>>;
  onHover?: (dot: SeatDot | null, point: { x: number; y: number } | null) => void;
  ariaLabel: string;
  /** Transition length in ms; 0 or reduced motion snaps. */
  duration?: number;
  /**
   * How new dots arrive and missing ones leave. grow: in place. slide: from
   * beyond the right edge (and out the same way), so additions read as
   * arriving. A wholesale change (no dot in common) always grows.
   */
  enter?: "grow" | "slide";
  className?: string;
}

interface DotState {
  x: number;
  y: number;
  /** Opacity 0..1 (entering and leaving dots fade). */
  a: number;
  /** Radius scale 0..1 (entering dots grow). */
  s: number;
}

interface Transition {
  from: Map<string, DotState>;
  to: Map<string, DotState>;
  fromRadius: number;
  toRadius: number;
  start: number;
  /** Per-dot start delays (ms), where the default left-to-right sweep won't do. */
  delays: Map<string, number>;
}

const DEFAULT_COLORS: Record<DotTone, string> = {
  empty: "--story-axis",
  neutral: "--story-seat",
  added: "--story-seat-added",
  focus: "--story-seat-focus",
};
/** Where sliding dots enter and leave: just beyond the frame's right edge. */
const OFF_RIGHT = 1.3;

/**
 * A field of keyed dots on <canvas>, laid out in a hemicycle's normalized
 * coordinates. When `dots` changes, dots with the same key glide to their new
 * positions, new keys grow in (or slide in from the side) and missing keys
 * fade (or slide) out, with a slight stagger so growth reads as a sweep.
 * Handles tens of thousands
 * of dots: drawing is batched into one path per color.
 */
export function DotField({
  dots,
  dotRadius,
  reserveRadius,
  toneFor,
  colors,
  onHover,
  ariaLabel,
  duration = 900,
  enter = "grow",
  className,
}: DotFieldProps) {
  const [wrapperRef, width] = useElementWidth<HTMLDivElement>();
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const reducedMotion = useReducedMotion();
  const [themeTick, setThemeTick] = React.useState(0);

  const current = React.useRef(new Map<string, DotState>());
  const currentRadius = React.useRef(dotRadius);
  const transition = React.useRef<Transition | null>(null);
  const frame = React.useRef(0);
  const byKey = React.useMemo(() => new Map(dots.map((dot) => [dot.key, dot])), [dots]);

  // Geometry: the chamber plus a margin of one (largest) dot radius on every
  // side, so the end seats of the bottom row fit horizontally and vertically.
  const pad = Math.max(reserveRadius ?? 0, dotRadius, 0.01);
  const outer = Math.max(0, (width / 2 - 2) / (1 + pad));
  const height = Math.ceil(outer * (1 + 2 * pad) + 4);
  const baseline = height - outer * pad - 2;

  const draw = React.useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || width === 0) return;
    const dpr = window.devicePixelRatio || 1;
    const pixelWidth = Math.round(width * dpr);
    const pixelHeight = Math.round(height * dpr);
    if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
    if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const resolved: Record<DotTone, string> = {
      empty: resolveCssColor(canvas, colors?.empty ?? DEFAULT_COLORS.empty),
      neutral: resolveCssColor(canvas, colors?.neutral ?? DEFAULT_COLORS.neutral),
      added: resolveCssColor(canvas, colors?.added ?? DEFAULT_COLORS.added),
      focus: resolveCssColor(canvas, colors?.focus ?? DEFAULT_COLORS.focus),
    };
    const radius = Math.max(0.6, currentRadius.current * outer);
    // Batch by (tone, opacity bucket): one path and fill per group.
    const groups = new Map<string, { tone: DotTone; alpha: number; path: Path2D }>();
    for (const [key, state] of current.current) {
      if (state.a <= 0.01) continue;
      const dot = byKey.get(key);
      const tone: DotTone = dot && toneFor ? toneFor(dot) : "neutral";
      const alpha = Math.round(state.a * 10) / 10;
      const groupKey = `${tone}:${alpha}`;
      let group = groups.get(groupKey);
      if (!group) {
        group = { tone, alpha, path: new Path2D() };
        groups.set(groupKey, group);
      }
      const px = width / 2 + state.x * outer;
      const py = baseline - state.y * outer;
      // Rings sit inside the seat, so a filled seat covers the same area.
      const r = radius * state.s * (tone === "empty" ? 0.82 : 1);
      group.path.moveTo(px + r, py);
      group.path.arc(px, py, r, 0, Math.PI * 2);
    }
    // Neutral first so highlighted seats sit on top.
    const ordered = [...groups.values()].sort((a, b) => TONE_ORDER[a.tone] - TONE_ORDER[b.tone]);
    for (const group of ordered) {
      ctx.globalAlpha = group.alpha;
      if (group.tone === "empty") {
        ctx.strokeStyle = resolved.empty;
        ctx.lineWidth = Math.max(1, radius * 0.3);
        ctx.stroke(group.path);
      } else {
        ctx.fillStyle = resolved[group.tone];
        ctx.fill(group.path);
      }
    }
    ctx.globalAlpha = 1;
  }, [width, height, outer, baseline, byKey, toneFor, colors]);

  // Start a transition whenever the dots (or their size) change.
  React.useEffect(() => {
    const to = new Map<string, DotState>();
    for (const dot of dots) to.set(dot.key, { x: dot.x, y: dot.y, a: 1, s: 1 });
    const slide = enter === "slide" && dots.some((dot) => current.current.has(dot.key));
    const from = new Map<string, DotState>();
    const delays = new Map<string, number>();
    const arriving: Array<[string, DotState]> = [];
    for (const [key, target] of to) {
      const existing = current.current.get(key);
      if (existing) from.set(key, existing);
      else if (slide) {
        from.set(key, { x: Math.max(target.x + 0.7, OFF_RIGHT), y: target.y, a: 0, s: 1 });
        arriving.push([key, target]);
      } else from.set(key, { ...target, a: 0, s: 0 });
    }
    // Sliding in, the farthest seats set off first, so the stream fills
    // the chamber from the inside out.
    arriving
      .sort((a, b) => a[1].x - b[1].x)
      .forEach(([key], rank) => delays.set(key, (rank / Math.max(1, arriving.length)) * duration * 0.6));
    for (const [key, state] of current.current) {
      if (!to.has(key)) {
        from.set(key, state);
        to.set(key, slide ? { x: Math.max(state.x + 0.7, OFF_RIGHT), y: state.y, a: 0, s: 1 } : { ...state, a: 0, s: 0.4 });
      }
    }

    const snap =
      reducedMotion ||
      duration <= 0 ||
      current.current.size === 0 ||
      document.visibilityState === "hidden";
    if (snap) {
      current.current = new Map([...to].filter(([, state]) => state.a > 0));
      currentRadius.current = dotRadius;
      transition.current = null;
      draw();
      return;
    }
    // The animation loop below picks this up. Re-running for a new `draw`
    // (resize, tone change) restarts from the current positions, so settled
    // dots stay put.
    transition.current = {
      from,
      to,
      fromRadius: currentRadius.current,
      toRadius: dotRadius,
      start: performance.now(),
      delays,
    };
  }, [dots, dotRadius, reducedMotion, duration, enter, draw]);

  // Animation loop: runs only while a transition is in flight.
  React.useEffect(() => {
    const tick = (now: number) => {
      const active = transition.current;
      if (!active) return;
      const total = duration * 1.3;
      const next = new Map<string, DotState>();
      let done = true;
      for (const [key, to] of active.to) {
        const from = active.from.get(key) ?? to;
        const delay = active.delays.get(key) ?? ((from.x + 1) / 2) * duration * 0.3;
        const t = clamp01((now - active.start - delay) / duration);
        if (t < 1) done = false;
        const e = easeInOutCubic(t);
        next.set(key, {
          x: from.x + (to.x - from.x) * e,
          y: from.y + (to.y - from.y) * e,
          a: from.a + (to.a - from.a) * e,
          s: from.s + (to.s - from.s) * e,
        });
      }
      const overall = easeInOutCubic(clamp01((now - active.start) / total));
      currentRadius.current = active.fromRadius + (active.toRadius - active.fromRadius) * overall;
      current.current = done ? new Map([...next].filter(([, s]) => s.a > 0)) : next;
      draw();
      if (done) {
        currentRadius.current = active.toRadius;
        transition.current = null;
        draw();
        return;
      }
      frame.current = requestAnimationFrame(tick);
    };
    if (transition.current) {
      cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(tick);
    }
    return () => cancelAnimationFrame(frame.current);
  }, [dots, dotRadius, duration, draw]);

  // Static redraws: resize, tone changes, theme switches.
  React.useEffect(() => {
    if (!transition.current) draw();
  }, [draw, themeTick]);
  React.useEffect(() => observeThemeChanges(() => setThemeTick((tick) => tick + 1)), []);

  const handlePointerMove = React.useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>) => {
      if (!onHover) return;
      const rect = event.currentTarget.getBoundingClientRect();
      const px = event.clientX - rect.left;
      const py = event.clientY - rect.top;
      const reach = Math.max(6, dotRadius * outer * 1.8);
      let best: SeatDot | null = null;
      let bestDistance = reach;
      for (const dot of dots) {
        const dx = width / 2 + dot.x * outer - px;
        const dy = baseline - dot.y * outer - py;
        const distance = Math.hypot(dx, dy);
        if (distance < bestDistance) {
          best = dot;
          bestDistance = distance;
        }
      }
      onHover(best, best ? { x: px, y: py } : null);
    },
    [onHover, dots, dotRadius, outer, width, baseline]
  );

  return (
    <div ref={wrapperRef} className={className}>
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={ariaLabel}
        style={{ width: "100%", height: width ? height : 0, display: "block" }}
        onPointerMove={onHover ? handlePointerMove : undefined}
        onPointerLeave={onHover ? () => onHover(null, null) : undefined}
      />
    </div>
  );
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}
