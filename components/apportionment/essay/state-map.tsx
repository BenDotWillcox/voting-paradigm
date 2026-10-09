"use client";

import * as React from "react";

import type { EssayState } from "@/lib/apportionment/essay-data";
import { cn } from "@/lib/utils";

import { formatCount } from "./constituency";
import { useStateFocus } from "./state-focus";

/**
 * Tile-grid positions [column, row]: one equal square per state in roughly
 * geographic arrangement, so small states are as easy to pick as large ones.
 */
const TILES: Record<string, [number, number]> = {
  AK: [0, 0], ME: [10, 0],
  WI: [5, 1], VT: [9, 1], NH: [10, 1],
  WA: [0, 2], ID: [1, 2], MT: [2, 2], ND: [3, 2], MN: [4, 2], IL: [5, 2], MI: [6, 2], NY: [8, 2], MA: [9, 2],
  OR: [0, 3], NV: [1, 3], WY: [2, 3], SD: [3, 3], IA: [4, 3], IN: [5, 3], OH: [6, 3], PA: [7, 3], NJ: [8, 3], CT: [9, 3], RI: [10, 3],
  CA: [0, 4], UT: [1, 4], CO: [2, 4], NE: [3, 4], MO: [4, 4], KY: [5, 4], WV: [6, 4], VA: [7, 4], MD: [8, 4], DE: [9, 4],
  AZ: [1, 5], NM: [2, 5], KS: [3, 5], AR: [4, 5], TN: [5, 5], NC: [6, 5], SC: [7, 5],
  OK: [3, 6], LA: [4, 6], MS: [5, 6], AL: [6, 6], GA: [7, 6],
  HI: [0, 7], TX: [3, 7], FL: [8, 7],
};
const COLUMNS = 11;
const ROWS = 8;

/**
 * Classes of people per seat relative to the national average: a neutral
 * band within 3%, so tiny differences around the average don't read as
 * gaps, then three classes per arm with breaks at 3%, 10% and 20%.
 */
const CLASSES = [
  { token: "fewer-3", label: "20%+ fewer" },
  { token: "fewer-2", label: "10–20% fewer" },
  { token: "fewer-1", label: "3–10% fewer" },
  { token: "neutral", label: "Within 3%" },
  { token: "more-1", label: "3–10% more" },
  { token: "more-2", label: "10–20% more" },
  { token: "more-3", label: "20%+ more" },
] as const;
const BREAKS = [-0.2, -0.1, -0.03, 0.03, 0.1, 0.2];
const BREAK_LABELS = ["−20%", "−10%", "−3%", "+3%", "+10%", "+20%"];

export function gapClassFor(perSeat: number, nationalAverage: number) {
  const share = perSeat / nationalAverage - 1;
  // Within 3% (either side) is neutral; beyond it, each arm has three classes.
  const index = BREAKS.filter((edge, i) => (i < 3 ? share >= edge : share > edge)).length;
  return CLASSES[index];
}

interface StateTileMapProps {
  /** 2020 seats per state (FIPS -> seats), shown in each tile's label. */
  seats: Readonly<Record<string, number>>;
  /** 2020 national average apportionment population per seat. */
  nationalAverage: number;
  className?: string;
}

/**
 * "Select a state": a tile-grid map of buttons, each colored by how many
 * people share one of its House seats compared with the national average.
 * Choosing a state highlights its seats in every figure of the essay;
 * choosing it again clears it.
 */
export function StateTileMap({ seats, nationalAverage, className }: StateTileMapProps) {
  const { states, focus, setFocus } = useStateFocus();
  const [hovered, setHovered] = React.useState<EssayState | null>(null);
  const shown = hovered ?? focus;

  return (
    <div className={className}>
      <div className="mb-2 flex items-baseline justify-between gap-3 font-sans text-sm">
        <span className="font-medium text-story-ink">Select a state</span>
        {focus ? (
          <button
            type="button"
            onClick={() => setFocus(null)}
            className="text-story-muted underline-offset-2 hover:text-story-ink hover:underline"
          >
            Clear
          </button>
        ) : null}
      </div>
      <div
        role="group"
        aria-label="Select a state"
        className="grid gap-[3px]"
        style={{
          gridTemplateColumns: `repeat(${COLUMNS}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${ROWS}, auto)`,
        }}
        onPointerLeave={() => setHovered(null)}
      >
        {states.map((state) => {
          const tile = TILES[state.abbr];
          if (!tile) return null;
          const selected = focus?.fips === state.fips;
          const count = seats[state.fips] ?? 0;
          const { token } = gapClassFor(state.averagePerSeat, nationalAverage);
          return (
            <button
              key={state.fips}
              type="button"
              aria-pressed={selected}
              aria-label={`${state.name}: ${count} ${count === 1 ? "seat" : "seats"}, ${formatCount(state.averagePerSeat)} people per seat`}
              onClick={() => setFocus(selected ? null : state.fips)}
              onPointerEnter={() => setHovered(state)}
              onFocus={() => setHovered(state)}
              onBlur={() => setHovered(null)}
              style={{
                gridColumn: tile[0] + 1,
                gridRow: tile[1] + 1,
                background: `var(--gap-${token})`,
                color: `var(--gap-${token}-ink)`,
              }}
              className={cn(
                "relative aspect-square rounded-[4px] font-sans text-[10px] font-semibold leading-none sm:text-xs",
                "transition-[scale,box-shadow] duration-200 ease-out",
                "hover:z-10 hover:scale-110 hover:shadow-md",
                "focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-story-accent",
                selected &&
                  "z-20 scale-115 shadow-lg ring-2 ring-story-ink ring-offset-2 ring-offset-story-page hover:scale-115"
              )}
            >
              {state.abbr}
            </button>
          );
        })}
      </div>

      <p className="mt-3 min-h-5 font-sans text-sm text-story-ink-2" aria-live="polite">
        {shown ? (
          <>
            <span className="font-semibold text-story-ink">{shown.name}</span>
            {" · "}
            {shown.seats} {shown.seats === 1 ? "seat" : "seats"}
            {" · "}
            <span className="tabular-nums">{formatCount(shown.averagePerSeat)}</span> people per seat
          </>
        ) : (
          <span className="text-story-muted">Hover over a state, or select one.</span>
        )}
      </p>

      {/* A list too, for small screens where tiles are tiny, and for anyone
          who would rather pick by name. */}
      <label className="mt-3 flex items-center gap-2 font-sans text-sm text-story-ink-2">
        <span>Or choose</span>
        <select
          value={focus?.fips ?? ""}
          onChange={(event) => setFocus(event.target.value || null)}
          className="min-w-0 flex-1 rounded-md border border-story-rule bg-story-surface px-2 py-1.5 text-story-ink"
        >
          <option value="">A state…</option>
          {[...states]
            .sort((a, b) => a.name.localeCompare(b.name))
            .map((state) => (
              <option key={state.fips} value={state.fips}>
                {state.name}
              </option>
            ))}
        </select>
      </label>

      <GapLegend nationalAverage={nationalAverage} />
    </div>
  );
}

/** Seven classes in one bar, labeled at their percentage breaks. */
function GapLegend({ nationalAverage }: { nationalAverage: number }) {
  return (
    <figure className="mt-3 font-sans text-xs text-story-muted">
      <figcaption className="mb-1.5 text-story-ink-2">
        Average people per House seat by state, 2020 census, compared with the U.S. average of{" "}
        <span className="tabular-nums">{formatCount(nationalAverage)}</span>
      </figcaption>
      <div className="flex gap-[2px]" role="list">
        {CLASSES.map((cls) => (
          <span
            key={cls.token}
            role="listitem"
            aria-label={cls.label}
            title={cls.label}
            className="h-2.5 flex-1 first:rounded-l-full last:rounded-r-full"
            style={{ background: `var(--gap-${cls.token})` }}
          />
        ))}
      </div>
      {/* The break values sit under the joins between classes. */}
      <div className="relative mt-1 h-4 tabular-nums">
        {BREAK_LABELS.map((label, i) => (
          <span key={label} className="absolute -translate-x-1/2" style={{ left: `${((i + 1) / CLASSES.length) * 100}%` }}>
            {label}
          </span>
        ))}
      </div>
      <div className="mt-0.5 flex justify-between">
        <span>Fewer people per seat</span>
        <span className="text-story-ink-2">Within 3% of average</span>
        <span>More people per seat</span>
      </div>
    </figure>
  );
}
