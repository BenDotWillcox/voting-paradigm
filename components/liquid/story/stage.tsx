"use client";

import { RotateCcw } from "lucide-react";
import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";
import { INK } from "@/lib/story/palette";
import { cn } from "@/lib/utils";

/*
 * The shared stage for the liquid story's mechanism animations
 * (prompts/demo-5-walkthrough.md, "Animations and diagrams"): a player that
 * runs a scene once when it scrolls into view and holds its end state, and
 * the scenes' visual vocabulary. A vote is a glowing orb, a resident a node,
 * a delegation a directed edge, and each topic has its own series colour.
 */

/** Progress through [start, end] at time t, clamped to 0..1. */
export function span(t: number, start: number, end: number): number {
  if (end <= start) return t >= end ? 1 : 0;
  return Math.min(1, Math.max(0, (t - start) / (end - start)));
}

export function lerp(a: number, b: number, x: number): number {
  return a + (b - a) * x;
}

export function easeInOut(x: number): number {
  return x < 0.5 ? 2 * x * x : 1 - (-2 * x + 2) ** 2 / 2;
}

export function easeOut(x: number): number {
  return 1 - (1 - x) ** 3;
}

export interface ScenePlayer {
  /** Attach to the scene's container: it starts the first time it is in view. */
  ref: React.RefObject<HTMLDivElement | null>;
  /** Elapsed time in ms, 0..duration. */
  t: number;
  playing: boolean;
  done: boolean;
  replay: () => void;
}

/**
 * Runs a scene once when it first scrolls into view, then holds its end
 * state; `replay` runs it again. Reduced motion shows the end state at once
 * and never animates. Nothing here touches scrolling.
 */
export function useScenePlayer(duration: number): ScenePlayer {
  const ref = React.useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();
  const [t, setT] = React.useState(0);
  const [run, setRun] = React.useState(0);

  React.useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setRun((value) => (value === 0 ? 1 : value));
          observer.disconnect();
        }
      },
      { threshold: 0.4 }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  React.useEffect(() => {
    if (run === 0 || reduced) return;
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const elapsed = Math.min(duration, now - start);
      setT(elapsed);
      if (elapsed < duration) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [run, reduced, duration]);

  const replay = React.useCallback(() => setRun((value) => value + 1), []);
  const shown = reduced ? duration : t;
  return { ref, t: shown, playing: !reduced && run > 0 && shown < duration, done: shown >= duration, replay };
}

/** Plays the scene again. Disabled while it plays. */
export function ReplayButton({ player, className }: { player: ScenePlayer; className?: string }) {
  return (
    <button
      type="button"
      onClick={player.replay}
      disabled={player.playing}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 font-sans text-xs text-story-ink-2 ring-1 ring-story-rule",
        "hover:text-story-ink disabled:opacity-40",
        className
      )}
    >
      <RotateCcw aria-hidden="true" className="h-3.5 w-3.5" />
      Replay
    </button>
  );
}

// ---------------------------------------------------------------------------
// The vocabulary, in SVG
// ---------------------------------------------------------------------------

/** The blur behind every orb on one SVG; render once per SVG with a unique id. */
export function OrbDefs({ id }: { id: string }) {
  return (
    <defs>
      <filter id={id} x="-150%" y="-150%" width="400%" height="400%">
        <feGaussianBlur stdDeviation="3" />
      </filter>
    </defs>
  );
}

/** A vote: a glowing orb in its topic's colour. */
export function Orb({
  x,
  y,
  r = 6,
  color,
  glowId,
  opacity = 1,
}: {
  x: number;
  y: number;
  r?: number;
  color: string;
  glowId: string;
  opacity?: number;
}) {
  if (opacity <= 0 || r <= 0) return null;
  return (
    <g transform={`translate(${x},${y})`} opacity={opacity} pointerEvents="none">
      <circle r={r * 1.9} style={{ fill: color }} opacity={0.45} filter={`url(#${glowId})`} />
      <circle r={r} style={{ fill: color }} />
      <circle r={r * 0.38} cx={-r * 0.28} cy={-r * 0.28} fill="#fff" opacity={0.55} />
    </g>
  );
}

/** A ballot: scribbled lines where the question would be, and a yes and a no box. */
export function Ballot({
  x,
  y,
  scale = 1,
  opacity = 1,
  accent,
}: {
  x: number;
  y: number;
  scale?: number;
  opacity?: number;
  /** The question's topic colour, on the card's tab. */
  accent: string;
}) {
  if (opacity <= 0 || scale <= 0) return null;
  const w = 58;
  const h = 72;
  return (
    <g transform={`translate(${x},${y}) scale(${scale})`} opacity={opacity} pointerEvents="none">
      <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={5} style={{ fill: INK.surface, stroke: INK.secondary }} strokeWidth={1.2} />
      <rect x={-w / 2 + 6} y={-h / 2 + 6} width={14} height={4} rx={2} style={{ fill: accent }} />
      {[0, 1, 2].map((line) => (
        <path
          key={line}
          d={`M${-w / 2 + 7},${-h / 2 + 19 + line * 9} q4,-3 8,0 t8,0 t8,0 t8,0 t${line === 2 ? 4 : 8},0`}
          fill="none"
          style={{ stroke: INK.muted }}
          strokeWidth={1.4}
          strokeLinecap="round"
        />
      ))}
      {[0, 1].map((box) => (
        <g key={box} transform={`translate(${-w / 2 + 7},${h / 2 - 22 + box * 11})`}>
          <rect width={7} height={7} rx={1.5} fill="none" style={{ stroke: INK.secondary }} strokeWidth={1.1} />
          <text x={11} y={6.5} fontSize={8} style={{ fill: INK.secondary }}>
            {box === 0 ? "Yes" : "No"}
          </text>
        </g>
      ))}
    </g>
  );
}

/** A resident: a node, with an optional label beside or below it. */
export function Person({
  x,
  y,
  r = 9,
  color,
  ring,
  label,
  labelAt = "below",
  emphasis = false,
}: {
  x: number;
  y: number;
  r?: number;
  /** Fill; defaults to the quiet node colour. */
  color?: string;
  /** A ring in this colour (a node that has just received a vote). */
  ring?: string;
  label?: string;
  labelAt?: "below" | "above" | "right" | "left";
  emphasis?: boolean;
}) {
  const offset = r + 12;
  const text =
    labelAt === "below"
      ? { x: 0, y: offset + 2, anchor: "middle" as const }
      : labelAt === "above"
        ? { x: 0, y: -offset + 6, anchor: "middle" as const }
        : labelAt === "right"
          ? { x: r + 6, y: 4, anchor: "start" as const }
          : { x: -r - 6, y: 4, anchor: "end" as const };
  return (
    <g transform={`translate(${x},${y})`}>
      {ring ? <circle r={r + 4} fill="none" style={{ stroke: ring }} strokeWidth={2} /> : null}
      <circle r={r} style={{ fill: color ?? INK.surface, stroke: color ?? INK.secondary }} strokeWidth={1.5} />
      {label ? (
        <text
          x={text.x}
          y={text.y}
          textAnchor={text.anchor}
          fontSize={11}
          fontWeight={emphasis ? 600 : 400}
          style={{ fill: emphasis ? INK.primary : INK.secondary }}
        >
          {label}
        </text>
      ) : null}
    </g>
  );
}

export interface Point {
  x: number;
  y: number;
}

/** Where a straight edge from a to b leaves a's rim and meets b's. */
export function trimmed(a: Point, b: Point, ra: number, rb: number): { from: Point; to: Point } {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const length = Math.hypot(dx, dy) || 1;
  const ux = dx / length;
  const uy = dy / length;
  return { from: { x: a.x + ux * ra, y: a.y + uy * ra }, to: { x: b.x - ux * rb, y: b.y - uy * rb } };
}

/** A delegation: a directed edge, drawn up to `progress` of its length. */
export function Edge({
  from,
  to,
  color,
  progress = 1,
  opacity = 1,
  width = 1.6,
  arrow = true,
}: {
  from: Point;
  to: Point;
  color: string;
  progress?: number;
  opacity?: number;
  width?: number;
  arrow?: boolean;
}) {
  if (progress <= 0 || opacity <= 0) return null;
  const end = { x: lerp(from.x, to.x, progress), y: lerp(from.y, to.y, progress) };
  const angle = (Math.atan2(to.y - from.y, to.x - from.x) * 180) / Math.PI;
  return (
    <g opacity={opacity} pointerEvents="none">
      <line x1={from.x} y1={from.y} x2={end.x} y2={end.y} style={{ stroke: color }} strokeWidth={width} strokeLinecap="round" />
      {arrow && progress >= 1 ? (
        <path d="M0,0 L-7,-3.5 L-7,3.5 Z" transform={`translate(${to.x},${to.y}) rotate(${angle})`} style={{ fill: color }} />
      ) : null}
    </g>
  );
}

/** The point at progress x along a straight segment. */
export function along(a: Point, b: Point, x: number): Point {
  return { x: lerp(a.x, b.x, x), y: lerp(a.y, b.y, x) };
}
