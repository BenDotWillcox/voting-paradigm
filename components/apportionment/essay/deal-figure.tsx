"use client";

import * as React from "react";

import type { EssayState } from "@/lib/apportionment/essay-data";
import { INK } from "@/lib/story/palette";

import { useStateFocus } from "./state-focus";

/**
 * Act III's pieces: the seats dealt by the method of equal proportions,
 * computed in the browser from the 2020 apportionment populations (the same
 * method as the build's race-2020.json; any difference from the published
 * apportionment throws), and the panels that show it.
 */

export const HOUSE_SIZE = 435;
/** The state used when the reader has not chosen one: it won seat 435. */
export const DEFAULT_LADDER_FIPS = "27";
const LEADERS = 8;

/** A state's claim to its `seat`-th seat (the Census Bureau's priority value). */
export function claimFor(population: number, seat: number): number {
  return population / Math.sqrt(seat * (seat - 1));
}

export interface Claim {
  fips: string;
  /** The seat claimed: the state's next one. */
  seat: number;
  priority: number;
}

/** One award of seats 51–435: the contest for it and who won. */
export interface Award {
  /** House seat number, 51..435. */
  seat: number;
  fips: string;
  /** The winner's new seat count. */
  claim: number;
  priority: number;
  /** The strongest claims for this seat, the winner first. */
  leaders: Claim[];
}

/** Seats 51 to 435, one award at a time. */
export function buildRace(states: readonly EssayState[]): Award[] {
  const held = new Map(states.map((state) => [state.fips, 1]));
  const awards: Award[] = [];
  for (let seat = states.length + 1; seat <= HOUSE_SIZE; seat++) {
    const claims = states
      .map((state) => {
        const next = (held.get(state.fips) ?? 1) + 1;
        return { fips: state.fips, seat: next, priority: claimFor(state.population, next) };
      })
      .sort((a, b) => b.priority - a.priority);
    const top = claims[0];
    awards.push({ seat, fips: top.fips, claim: top.seat, priority: top.priority, leaders: claims.slice(0, LEADERS) });
    held.set(top.fips, top.seat);
  }
  for (const state of states) {
    if (held.get(state.fips) !== state.seats) {
      throw new Error(`The race gives ${state.abbr} ${held.get(state.fips)} seats, not ${state.seats}`);
    }
  }
  return awards;
}

/**
 * Seats per state once `dealt` seats are out: the guaranteed first seats in
 * `order` (west to east, so they light across the chamber), then the race.
 */
export function seatsAfter(race: readonly Award[], order: readonly string[], dealt: number): Record<string, number> {
  const seats: Record<string, number> = {};
  for (let i = 0; i < Math.min(dealt, order.length); i++) seats[order[i]] = 1;
  for (let i = 0; i < Math.min(dealt - order.length, race.length); i++) seats[race[i].fips] = race[i].claim;
  return seats;
}

/**
 * Awards made at a point in the race step, at an even pace: the reader sets
 * the speed by scrolling. A short hold at each end shows the first contest
 * before any award and the finished race.
 */
export function racePace(progress: number): number {
  const total = HOUSE_SIZE - 50;
  const [start, end] = [0.03, 0.95];
  return Math.floor(Math.max(0, Math.min(1, (progress - start) / (end - start))) * total);
}

export function ordinal(n: number): string {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  return `${n}${["th", "st", "nd", "rd"][n % 10] ?? "th"}`;
}

export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * Where the dealing scenes put things: the chamber across the top of the
 * visual area and a panel (the claims or the race) below it.
 */
export function dealLayout(area: { left: number; width: number; height: number }): { chamber: Box; panel: Box } {
  // The chamber starts below the figure's unit label (top right).
  const offset = 28;
  const width = Math.round(Math.min(area.width * 0.62, (area.height * 0.42 - offset) * 1.9));
  const height = Math.round(width * 0.53);
  const chamber = { left: Math.round(area.left + (area.width - width) / 2), top: offset, width, height };
  const top = offset + height + 14;
  return { chamber, panel: { left: area.left, top, width: area.width, height: Math.max(80, area.height - top) } };
}

/** The race: the strongest claims for the next seat, as bars that re-sort. */
export function RaceBars({
  race,
  awarded,
  box,
  visible,
}: {
  race: readonly Award[];
  /** Awards made so far, 0..385. */
  awarded: number;
  box: Box;
  visible: boolean;
}) {
  const { states, focus } = useStateFocus();
  const compact = box.width < 560;
  const finished = awarded >= race.length;
  const contest = race[Math.min(awarded, race.length - 1)];
  const shown = contest.leaders.slice(0, compact ? 6 : LEADERS);
  const byFips = new Map(states.map((state) => [state.fips, state]));
  // The reader's state keeps a row of its own when it is out of the running.
  let focusRow: Claim | null = null;
  if (focus && !shown.some((claim) => claim.fips === focus.fips)) {
    let seats = 1;
    for (let i = 0; i < Math.min(awarded, race.length); i++) if (race[i].fips === focus.fips) seats = race[i].claim;
    focusRow = { fips: focus.fips, seat: seats + 1, priority: claimFor(focus.population, seats + 1) };
  }
  const rows = focusRow ? [...shown, focusRow] : shown;
  const rowHeight = Math.max(18, Math.min(30, (box.height - 8) / (rows.length + (focusRow ? 0.6 : 0))));
  const labelWidth = compact ? 74 : 188;
  const valueWidth = compact ? 64 : 92;
  // Room for the leader's "→ seat N" tag on every row, so the leading bar
  // is never squeezed shorter than the ones below it.
  const tagWidth = compact ? 0 : 96;
  const barMax = Math.max(20, box.width - labelWidth - valueWidth - tagWidth - 12);
  const top = shown[0].priority;

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute font-sans transition-opacity duration-500"
      style={{ left: box.left, top: box.top, width: box.width, height: box.height, opacity: visible ? 1 : 0 }}
    >
      {rows.map((claim, rank) => {
        const state = byFips.get(claim.fips);
        const lead = rank === 0;
        const mine = claim.fips === focus?.fips;
        const y = rank * rowHeight + (claim === focusRow ? rowHeight * 0.6 : 0);
        const color = mine ? "var(--story-seat-focus)" : lead ? INK.primary : "var(--story-seat)";
        return (
          <div
            key={claim.fips}
            className="absolute inset-x-0 flex items-center transition-transform duration-300 ease-out"
            style={{ height: rowHeight, transform: `translateY(${y.toFixed(1)}px)` }}
          >
            <span
              className="shrink-0 truncate pr-2 text-right text-xs sm:text-sm"
              style={{ width: labelWidth, color: lead || mine ? INK.primary : INK.secondary, fontWeight: lead ? 700 : 500 }}
            >
              {compact ? state?.abbr : state?.name}
              <span className="font-normal text-story-muted"> · {ordinal(claim.seat)}</span>
            </span>
            <span
              className="h-[60%] shrink-0 rounded-sm transition-[width] duration-300 ease-out"
              style={{ width: Math.max(2, (claim.priority / top) * barMax), background: color }}
            />
            <span className="shrink-0 pl-2 text-xs tabular-nums sm:text-sm" style={{ color: lead ? INK.primary : INK.secondary, fontWeight: lead ? 700 : 400 }}>
              {Math.round(claim.priority).toLocaleString("en-US")}
            </span>
            {lead && !compact ? (
              <span className="ml-2 shrink-0 text-xs font-semibold whitespace-nowrap text-[var(--gap-more-3)]">
                {finished ? `won seat ${contest.seat}` : `→ seat ${contest.seat}`}
              </span>
            ) : null}
          </div>
        );
      })}
      {focusRow ? (
        <div
          className="absolute inset-x-0 border-t border-dashed border-story-rule"
          style={{ top: shown.length * rowHeight + rowHeight * 0.3 }}
        />
      ) : null}
    </div>
  );
}

/**
 * One state's claims to its 2nd, 3rd, ... seats as dots on a labeled log
 * scale (dots, not bars: bar lengths on a log axis would suggest ratios the
 * scale doesn't show), against the line that won the 435th seat: every
 * claim above it won a seat.
 */
export function ClaimLadder({
  race,
  box,
  visible,
}: {
  race: readonly Award[];
  box: Box;
  visible: boolean;
}) {
  const { states, focus } = useStateFocus();
  const state = focus ?? states.find((s) => s.fips === DEFAULT_LADDER_FIPS) ?? states[0];
  const compact = box.width < 560;
  const cutoff = race[race.length - 1].priority;
  const claims = Array.from({ length: state.seats }, (_, i) => ({
    seat: i + 2,
    priority: claimFor(state.population, i + 2),
  }));
  const formulaHeight = compact ? 40 : 50;
  const plot = {
    left: box.left + (compact ? 34 : 52),
    right: box.left + box.width - (compact ? 6 : 140),
    top: box.top + formulaHeight + 24,
    bottom: box.top + box.height - 22,
  };
  const [lo, hi] = [300_000, 30_000_000];
  const y = (v: number) =>
    plot.bottom - ((Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))) * (plot.bottom - plot.top);
  const step = Math.min(compact ? 22 : 34, (plot.right - plot.left) / claims.length);
  const radius = Math.max(2.5, Math.min(compact ? 5 : 7, step * 0.34));
  const x = (i: number) => plot.left + (i + 0.5) * step;
  const won = claims.filter((c) => c.priority >= cutoff - 1e-6);
  const second = claims[0];

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 font-sans transition-opacity duration-500"
      style={{ opacity: visible ? 1 : 0 }}
    >
      <div className="absolute text-xs sm:text-sm" style={{ left: box.left, top: box.top, width: box.width }}>
        <p className="font-semibold text-story-ink">
          Claim to a state’s <i>n</i>th seat = population ÷ √(<i>n</i> × (<i>n</i> − 1))
        </p>
        <p className="mt-0.5 text-story-ink-2 tabular-nums">
          {state.name}, {ordinal(2)} seat: {state.population.toLocaleString("en-US")} ÷ √(2 × 1) ={" "}
          {Math.round(second.priority).toLocaleString("en-US")}
        </p>
      </div>
      <svg width="100%" height="100%" className="absolute inset-0 overflow-visible">
        <text x={box.left} y={plot.top - 10} fontSize={11} fill={INK.muted}>
          Claim (logarithmic scale)
        </text>
        {[1_000_000, 3_000_000, 10_000_000, 30_000_000].map((tick) => (
          <g key={tick}>
            <line x1={plot.left} x2={plot.right} y1={y(tick)} y2={y(tick)} stroke={INK.grid} />
            <text x={plot.left - 6} y={y(tick)} dy="0.32em" textAnchor="end" fontSize={11} fill={INK.muted}>
              {tick >= 1_000_000 ? `${tick / 1_000_000}M` : `${tick / 1000}k`}
            </text>
          </g>
        ))}
        {claims.map((claim, i) => {
          const win = claim.priority >= cutoff - 1e-6;
          return (
            <circle
              key={claim.seat}
              cx={x(i)}
              cy={y(claim.priority)}
              r={radius}
              fill={win ? "var(--story-seat-focus)" : INK.surface}
              stroke={win ? INK.surface : INK.secondary}
              strokeWidth={1.5}
            />
          );
        })}
        <line x1={plot.left} x2={plot.right} y1={plot.bottom} y2={plot.bottom} stroke={INK.axis} />
        {/* The line: the claim that won seat 435. */}
        <line
          x1={plot.left - 4}
          x2={plot.right + 4}
          y1={y(cutoff)}
          y2={y(cutoff)}
          stroke="var(--gap-more-3)"
          strokeWidth={1.5}
          strokeDasharray="5 4"
        />
        <text
          x={compact ? plot.right : plot.right + 10}
          y={y(cutoff) + (compact ? -6 : 0)}
          dy={compact ? 0 : "0.32em"}
          textAnchor={compact ? "end" : "start"}
          fontSize={compact ? 11 : 12}
          fontWeight={600}
          fill="var(--gap-more-3)"
          className="tabular-nums"
        >
          Seat 435: {Math.round(cutoff).toLocaleString("en-US")}
        </text>
        <text x={x(0)} y={plot.bottom + 15} textAnchor="middle" fontSize={11} fill={INK.muted}>
          {ordinal(2)}
        </text>
        {claims.length > 1 ? (
          <text
            x={x(claims.length - 1)}
            y={plot.bottom + 15}
            textAnchor="middle"
            fontSize={11}
            fill={INK.muted}
          >
            {ordinal(claims[claims.length - 1].seat)}
          </text>
        ) : null}
        {!compact ? (
          <text x={plot.right + 10} y={y(cutoff) + 18} fontSize={12} fill={INK.secondary}>
            {won.length === 0 ? "No claim cleared it" : `${won.length} claim${won.length === 1 ? "" : "s"} cleared it`}
          </text>
        ) : null}
      </svg>
    </div>
  );
}

/** The words for the ladder step, about whichever state the figure shows. */
export function LadderText() {
  const { states, focus } = useStateFocus();
  const state = focus ?? states.find((s) => s.fips === DEFAULT_LADDER_FIPS) ?? states[0];
  const race = React.useMemo(() => buildRace(states), [states]);
  const lastSeat = race[race.length - 1];
  if (state.seats === 1) {
    return (
      <>
        {state.name} keeps only its guaranteed seat: its claim to a second falls below the line, the claim
        that won the 435th seat.
      </>
    );
  }
  return (
    <>
      Every one of {state.name}’s claims above the line won a seat, {state.seats - 1} in all, on top of its
      guaranteed one. The line is the claim that won the 435th seat
      {lastSeat.fips === state.fips ? `, which was ${state.name}’s ${ordinal(state.seats)}` : ""}.
    </>
  );
}
