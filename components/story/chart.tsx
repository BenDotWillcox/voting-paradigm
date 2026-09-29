"use client";

import * as React from "react";

import { INK } from "@/lib/story/palette";

/**
 * SVG chart primitives for story figures. Marks follow the dataviz spec:
 * hairline solid gridlines one step off the surface, recessive axes, 2px
 * lines, >= 8px markers with a 2px surface ring, text in ink tokens.
 */

// Layout effects warn during SSR in React 18; measure before paint on the client only.
const useIsomorphicLayoutEffect =
  typeof window === "undefined" ? React.useEffect : React.useLayoutEffect;

/** Width of an element, tracked with ResizeObserver (0 until measured). */
export function useElementWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = React.useRef<T | null>(null);
  const [width, setWidth] = React.useState(0);
  useIsomorphicLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    setWidth(Math.round(node.getBoundingClientRect().width));
    const observer = new ResizeObserver((entries) => {
      setWidth(Math.round(entries[0]?.contentRect.width ?? 0));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/** True when the viewer asked the OS to minimize motion. */
export function useReducedMotion(): boolean {
  return React.useSyncExternalStore(
    (onChange) => {
      const query = window.matchMedia("(prefers-reduced-motion: reduce)");
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false
  );
}

export interface Margin {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

interface AxisXProps {
  /** Maps a value to x within the plot area. */
  x: (value: number) => number;
  ticks: number[];
  format?: (value: number) => string;
  /** y of the axis line (plot-area height). */
  y: number;
  /** Draw vertical gridlines up to the top of the plot area. */
  grid?: boolean;
  label?: string;
  /** Plot-area width, used to place the axis label. */
  width?: number;
}

export function AxisX({ x, ticks, format = String, y, grid = false, label, width }: AxisXProps) {
  return (
    <g aria-hidden="true" fontSize={12}>
      {ticks.map((tick) => {
        const tx = x(tick);
        return (
          <g key={tick} transform={`translate(${tx},0)`}>
            {grid ? <line y1={0} y2={y} stroke={INK.grid} strokeWidth={1} /> : null}
            <line y1={y} y2={y + 4} stroke={INK.axis} strokeWidth={1} />
            <text y={y + 18} textAnchor="middle" fill={INK.muted} className="tabular-nums">
              {format(tick)}
            </text>
          </g>
        );
      })}
      {label && width ? (
        <text x={width} y={y + 36} textAnchor="end" fill={INK.muted}>
          {label}
        </text>
      ) : null}
    </g>
  );
}

interface AxisYProps {
  y: (value: number) => number;
  ticks: number[];
  format?: (value: number) => string;
  /** Plot-area width, for horizontal gridlines. */
  width: number;
  grid?: boolean;
}

export function AxisY({ y, ticks, format = String, width, grid = true }: AxisYProps) {
  return (
    <g aria-hidden="true" fontSize={12}>
      {ticks.map((tick) => {
        const ty = y(tick);
        return (
          <g key={tick} transform={`translate(0,${ty})`}>
            {grid ? <line x1={0} x2={width} stroke={INK.grid} strokeWidth={1} /> : null}
            <text x={-8} dy="0.32em" textAnchor="end" fill={INK.muted} className="tabular-nums">
              {format(tick)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

interface AnnotationProps {
  /** Point being annotated. */
  x: number;
  y: number;
  /** Label offset from the point. */
  dx: number;
  dy: number;
  children: React.ReactNode;
  /** Secondary line, kept on the side of the label away from the point. */
  detail?: React.ReactNode;
  /** Text alignment at the label position; inferred from dx by default. */
  align?: "start" | "middle" | "end";
}

const LINE_HEIGHT = 16;

/**
 * A direct label with a leader line. Text wears ink tokens with a surface
 * halo so it stays legible over marks. The leader stops short of the text
 * block on whichever side faces the point.
 */
export function Annotation({ x, y, dx, dy, children, detail, align }: AnnotationProps) {
  const anchor = align ?? (dx < -4 ? "end" : dx > 4 ? "start" : "middle");
  const lx = x + dx;
  const ly = y + dy;
  const above = dy < 0;
  const lines = detail ? 2 : 1;
  // Baseline of the first line; the block grows away from the point.
  const firstBaseline = above ? ly - (lines - 1) * LINE_HEIGHT : ly + 12;
  const leaderEnd = above ? ly + 5 : ly;
  const halo = {
    stroke: INK.surface,
    strokeWidth: 4,
    strokeLinejoin: "round" as const,
    paintOrder: "stroke" as const,
  };
  return (
    <g pointerEvents="none" fontSize={13}>
      <line x1={x} y1={y} x2={lx} y2={leaderEnd} stroke={INK.secondary} strokeWidth={1} />
      <text x={lx} y={firstBaseline} textAnchor={anchor} fontWeight={600} fill={INK.primary} {...halo}>
        {children}
      </text>
      {detail ? (
        <text
          x={lx}
          y={firstBaseline + LINE_HEIGHT}
          textAnchor={anchor}
          fill={INK.secondary}
          {...halo}
        >
          {detail}
        </text>
      ) : null}
    </g>
  );
}

/**
 * Hover card positioned in the chart's pixel space. Flips to the left of the
 * pointer past 60% of the width so it never overflows.
 */
export function ChartTooltip({
  x,
  y,
  width,
  children,
}: {
  x: number;
  y: number;
  width: number;
  children: React.ReactNode;
}) {
  const flip = x > width * 0.6;
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-10 w-max max-w-60 rounded-md bg-story-surface px-3 py-2 text-xs text-story-ink shadow-md ring-1 ring-story-rule"
      style={{
        left: x,
        top: y,
        transform: `translate(${flip ? "calc(-100% - 14px)" : "14px"}, -50%)`,
      }}
    >
      {children}
    </div>
  );
}
