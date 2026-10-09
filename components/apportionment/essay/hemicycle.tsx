"use client";

import * as React from "react";

import { ChartTooltip } from "@/components/story/chart";
import { DotField, type DotTone } from "@/components/story/dot-field";
import { assignSeats, hemicycleLayout, type SeatDot } from "@/lib/story/hemicycle";

import { useStateFocus } from "./state-focus";

interface HemicycleProps {
  /** Seats per state (FIPS -> seats); the House size is their sum. */
  seats: Readonly<Record<string, number>>;
  /** State order around the chamber, left to right. */
  order: readonly string[];
  ariaLabel: string;
  /** Reserve room for dots this large (normalized); see DotField. */
  reserveRadius?: number;
  /** Highlight the reader's state (off for historical chambers). */
  highlightFocus?: boolean;
  /**
   * Seats by age instead of by state: the original seats on the left, then
   * every seat added since, the newest at the right end. Seats beyond
   * `original` are "added" (muted); those beyond `previous` (the size at the
   * apportionment before) are new this time (strong). New seats slide in
   * from the side and removed ones slide out. Counts match the House's
   * growth exactly, which per-state seats cannot (states gain and lose
   * seats in the same census).
   */
  byAge?: { original: number; previous: number | null };
  /**
   * Seats dealt so far per state (FIPS -> seats): the rest of each state's
   * wedge shows as empty rings. Omit for a full chamber.
   */
  filled?: Readonly<Record<string, number>>;
  className?: string;
}

/**
 * The House as a parliament diagram: one dot per seat, each state a
 * contiguous wedge (west to east), the reader's state highlighted, or (with
 * `byAge`) seats in the order they were added. Changing `seats` animates
 * seats gliding to their new places.
 */
export function Hemicycle({
  seats,
  order,
  ariaLabel,
  reserveRadius,
  highlightFocus = true,
  byAge,
  filled,
  className,
}: HemicycleProps) {
  const { focus, states } = useStateFocus();
  const [hovered, setHovered] = React.useState<{
    dot: SeatDot;
    point: { x: number; y: number };
  } | null>(null);
  const [width, setWidth] = React.useState(0);
  const wrapperRef = React.useRef<HTMLDivElement | null>(null);

  const total = React.useMemo(
    () => Object.values(seats).reduce((sum, count) => sum + count, 0),
    [seats]
  );
  const layout = React.useMemo(() => hemicycleLayout(total), [total]);
  const ageOrder = byAge !== undefined;
  const dots = React.useMemo(
    () =>
      ageOrder
        ? layout.slots.map((slot, i) => ({ key: `seat-${i}`, fips: "", x: slot.x, y: slot.y }))
        : assignSeats(layout, order, seats),
    [ageOrder, layout, order, seats]
  );

  const focusFips = highlightFocus ? focus?.fips ?? null : null;
  const original = byAge?.original ?? 0;
  const previous = byAge?.previous ?? null;
  const toneFor = React.useCallback(
    (dot: SeatDot): DotTone => {
      if (!ageOrder) {
        if (filled && Number(dot.key.slice(dot.key.lastIndexOf("-") + 1)) >= (filled[dot.fips] ?? 0)) return "empty";
        return dot.fips === focusFips ? "focus" : "neutral";
      }
      const index = Number(dot.key.slice("seat-".length));
      if (previous !== null && total > previous && index >= previous) return "focus";
      return index >= original ? "added" : "neutral";
    },
    [ageOrder, filled, focusFips, original, previous, total]
  );
  const handleHover = React.useCallback(
    (dot: SeatDot | null, point: { x: number; y: number } | null) => {
      setHovered(dot && point ? { dot, point } : null);
      if (wrapperRef.current) setWidth(wrapperRef.current.clientWidth);
    },
    []
  );

  const hoveredState = hovered ? states.find((s) => s.fips === hovered.dot.fips) : null;

  return (
    <div ref={wrapperRef} className={`relative ${className ?? ""}`}>
      <DotField
        dots={dots}
        dotRadius={layout.dotRadius}
        enter={ageOrder ? "slide" : "grow"}
        reserveRadius={reserveRadius}
        toneFor={toneFor}
        onHover={handleHover}
        ariaLabel={ariaLabel}
      />
      {hovered && hoveredState ? (
        <ChartTooltip x={hovered.point.x} y={hovered.point.y} width={width}>
          <div className="font-semibold">{hoveredState.name}</div>
          <div className="tabular-nums text-story-ink-2">
            {seats[hoveredState.fips]} of {total} seats
          </div>
        </ChartTooltip>
      ) : null}
    </div>
  );
}
