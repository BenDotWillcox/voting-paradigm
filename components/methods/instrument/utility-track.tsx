"use client";

import { useRef } from "react";

import { UTILITY_SCALE, formatUtility } from "@/lib/methods/profile";
import { cn } from "@/lib/utils";

import { CandidateGlyph } from "./glyph";

// Drag and arrow keys move a candidate in half-point steps
const STEP = 5;
const PAGE = 10;

/**
 * One voter type's utilities: each candidate is a glyph on a 0–10 track.
 * Order along the track is the voter's ranking; spacing is how much more
 * they prefer one candidate to another. Each glyph is a slider: drag it, or
 * focus it and use the arrow keys (Page Up/Down for bigger steps, Home/End
 * for the ends).
 */
export function UtilityTrack({
  candidates,
  utilities,
  label,
  onChange,
}: {
  candidates: string[];
  utilities: Record<string, number>;
  label: string;
  onChange: (candidate: string, value: number) => void;
}) {
  const group = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const dragging = useRef<string | null>(null);
  const lanes = assignLanes(candidates, utilities);

  function valueAt(clientX: number): number {
    const rect = track.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return 0;
    const fraction = (clientX - rect.left) / rect.width;
    const value = Math.round((fraction * UTILITY_SCALE) / STEP) * STEP;
    return Math.max(0, Math.min(UTILITY_SCALE, value));
  }

  return (
    <div
      ref={group}
      role="group"
      aria-label={label}
      className="relative h-11 min-w-0 flex-1 px-2.5"
      onPointerMove={(event) => {
        const id = dragging.current;
        if (id === null) return;
        const value = valueAt(event.clientX);
        if (value !== utilities[id]) onChange(id, value);
      }}
      onPointerUp={() => {
        dragging.current = null;
      }}
      onPointerCancel={() => {
        dragging.current = null;
      }}
    >
      <div ref={track} className="absolute inset-x-2.5 top-1/2 h-px bg-mi-rule">
        {Array.from({ length: 11 }, (_, i) => (
          <span
            key={i}
            aria-hidden
            className={cn("absolute top-1/2 w-px -translate-y-1/2 bg-mi-rule", i % 5 === 0 ? "h-2.5" : "h-1.5")}
            style={{ left: `${i * 10}%` }}
          />
        ))}
        {candidates.map((id) => {
          const value = utilities[id] ?? 0;
          return (
            <div
              key={id}
              role="slider"
              tabIndex={0}
              aria-label={`${id}`}
              aria-valuemin={0}
              aria-valuemax={UTILITY_SCALE}
              aria-valuenow={value}
              aria-valuetext={`${id}: ${formatUtility(value)} out of 10`}
              title={`${id}: ${formatUtility(value)}`}
              className={cn(
                "absolute grid size-7 -translate-x-1/2 -translate-y-1/2 cursor-grab touch-none place-items-center rounded-full outline-none select-none",
                "focus-visible:ring-1 focus-visible:ring-mi-ink active:cursor-grabbing"
              )}
              style={{ left: `${value}%`, top: `${lanes[id] * 9}px` }}
              onPointerDown={(event) => {
                if (event.button !== 0) return;
                event.preventDefault();
                (event.currentTarget as HTMLElement).focus();
                // The group holds capture, so moving thumbs never drop it
                group.current?.setPointerCapture(event.pointerId);
                dragging.current = id;
              }}
              onKeyDown={(event) => {
                const next = keyValue(event.key, value);
                if (next === null) return;
                event.preventDefault();
                onChange(id, next);
              }}
            >
              <CandidateGlyph id={id} size={17} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function keyValue(key: string, value: number): number | null {
  const clamp = (v: number) => Math.max(0, Math.min(UTILITY_SCALE, v));
  if (key === "ArrowRight" || key === "ArrowUp") return clamp(value + STEP);
  if (key === "ArrowLeft" || key === "ArrowDown") return clamp(value - STEP);
  if (key === "PageUp") return clamp(value + PAGE);
  if (key === "PageDown") return clamp(value - PAGE);
  if (key === "Home") return 0;
  if (key === "End") return UTILITY_SCALE;
  return null;
}

/**
 * Glyphs closer than this (in utility points) sit in alternating lanes above
 * and below the line, so neither hides the other.
 */
const CROWDED = 9;

function assignLanes(candidates: string[], utilities: Record<string, number>): Record<string, number> {
  const sorted = [...candidates].sort((a, b) => (utilities[a] ?? 0) - (utilities[b] ?? 0));
  const lanes: Record<string, number> = {};
  let previous: number | null = null;
  let lane = 0;
  for (const id of sorted) {
    const value = utilities[id] ?? 0;
    lane = previous !== null && value - previous < CROWDED ? (lane === -1 ? 1 : -1) : 0;
    lanes[id] = lane;
    previous = value;
  }
  return lanes;
}
