"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";

import { cn } from "@/lib/utils";

/**
 * A spatial winner map drawn as a size × size image and scaled up by CSS
 * with crisp cells: the atlas's maps and the methods home card. Colors come
 * from the methods tokens in scope at the canvas (`.methods-instrument`), so
 * the map follows the theme wherever it is placed.
 */

type Rgb = [number, number, number];

// How far toward the surface a tiebreak-decided cell is lightened
const TIE_FADE = 0.55;

export type MapKind = "winners" | "disagreement";

export function MapCanvas({
  cells,
  size,
  ties,
  kind = "winners",
  label,
  className,
}: {
  /** One character per cell, row-major: a candidate ID, "-" for none, or a digit. */
  cells: string;
  size: number;
  /** Cells a tiebreak decided, drawn lighter. */
  ties: readonly number[];
  kind?: MapKind;
  label?: string;
  className?: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const theme = useThemeClass();

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;
    const style = getComputedStyle(element);
    const token = (name: string): Rgb => parseHex(style.getPropertyValue(name));
    const surface = token("--mi-surface");
    const ink = token("--mi-ink");
    const candidates: Record<string, Rgb> = {};
    const tied = new Set(ties);
    element.width = size;
    element.height = size;
    const image = context.createImageData(size, size);
    for (let i = 0; i < cells.length; i++) {
      const value = cells[i];
      let color: Rgb;
      if (kind === "disagreement") color = mix(surface, ink, disagreementShade(Number(value)));
      else if (value === "-") color = mix(surface, ink, 0.08);
      else color = candidates[value] ??= token(`--mi-cand-${value.toLowerCase()}`);
      if (tied.has(i)) color = mix(color, surface, TIE_FADE);
      image.data.set([color[0], color[1], color[2], 255], i * 4);
    }
    context.putImageData(image, 0, 0);
  }, [cells, size, ties, kind, theme]);

  return (
    <canvas
      ref={canvas}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn("h-full w-full [image-rendering:pixelated]", className)}
    />
  );
}

/** Ink coverage for a disagreement count: one winner is blank, five nearly solid. */
export function disagreementShade(count: number): number {
  return Math.min(0.85, Math.max(0, (count - 1) * 0.24));
}

/** The class on <html>, which carries dark mode; maps redraw when it changes. */
function useThemeClass(): string {
  return useSyncExternalStore(
    (onChange) => {
      const observer = new MutationObserver(onChange);
      observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
      return () => observer.disconnect();
    },
    () => document.documentElement.className,
    () => ""
  );
}

function parseHex(value: string): Rgb {
  const match = /^#?([0-9a-f]{6})$/i.exec(value.trim());
  if (!match) return [128, 128, 128];
  const n = parseInt(match[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function mix(from: Rgb, to: Rgb, amount: number): Rgb {
  return [0, 1, 2].map((i) => Math.round(from[i] + (to[i] - from[i]) * amount)) as Rgb;
}
