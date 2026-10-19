"use client";

import * as React from "react";
import Link from "next/link";

import { useElementWidth } from "@/components/story/chart";
import { formatCount } from "@/components/apportionment/essay/constituency";
import { ordinal } from "@/components/apportionment/essay/deal-figure";
import { useStateFocus } from "@/components/apportionment/essay/state-focus";
import { signedPercent } from "@/components/apportionment/essay/state-swarm";
import type { EssayState } from "@/lib/apportionment/essay-data";
import {
  SWEEP_START,
  SWEEP_STOP,
  averageAt,
  claimFor,
  seatsFor,
  sizeForSeat,
  winningClaim,
} from "@/lib/apportionment/house-sizes";
import { INK } from "@/lib/story/palette";

/**
 * The reader's state at the chosen size: its seats against today's, people
 * per seat against the national average, the size at which it would win
 * its next seat, and its claims against the line set by the last seat
 * dealt. The state is shared with the essay (URL and storage).
 */
export function StatePanel({ size }: { size: number }) {
  const { states, focus, setFocus } = useStateFocus();
  const sorted = React.useMemo(() => [...states].sort((a, b) => a.name.localeCompare(b.name)), [states]);

  return (
    <section aria-labelledby="state-panel-title" className="font-sans">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
        <h2 id="state-panel-title" className="font-story-serif text-2xl font-medium text-story-ink">
          {focus ? `${focus.name} at ${size.toLocaleString("en-US")} seats` : "Your state"}
        </h2>
        <div className="flex items-center gap-3">
          <select
            value={focus?.fips ?? ""}
            onChange={(event) => setFocus(event.target.value || null)}
            aria-label="Choose a state"
            className="rounded-md border border-story-rule bg-story-surface px-2 py-1.5 text-sm text-story-ink"
          >
            <option value="">Choose a state…</option>
            {sorted.map((state) => (
              <option key={state.fips} value={state.fips}>
                {state.name}
              </option>
            ))}
          </select>
          {focus ? (
            <button
              type="button"
              onClick={() => setFocus(null)}
              className="text-sm text-story-muted underline-offset-2 hover:text-story-ink hover:underline"
            >
              Clear
            </button>
          ) : null}
        </div>
      </div>
      {focus ? (
        <StateDetail state={focus} size={size} />
      ) : (
        <p className="mt-1 text-sm text-story-ink-2">
          Choose a state here, on the map, or by clicking its dot to follow it across House sizes.
        </p>
      )}
    </section>
  );
}

function StateDetail({ state, size }: { state: EssayState; size: number }) {
  const seats = seatsFor(size)[state.fips];
  const perSeat = seats === state.seats ? state.averagePerSeat : state.population / seats;
  const share = perSeat / averageAt(size) - 1;
  const nextAt = sizeForSeat(state.fips, seats + 1);

  return (
    <div className="mt-3 grid gap-x-8 gap-y-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      <div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <div>
            <dt className="text-xs text-story-muted">Seats</dt>
            <dd className="font-semibold text-story-ink tabular-nums">
              {seats.toLocaleString("en-US")}
              {size !== SWEEP_START ? (
                <span className="font-normal text-story-muted"> (today: {state.seats})</span>
              ) : null}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-story-muted">People per seat</dt>
            <dd className="font-semibold text-story-ink tabular-nums">{formatCount(perSeat)}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-xs text-story-muted">Compared with the national average</dt>
            <dd className="text-story-ink tabular-nums">
              {signedPercent(share) === "0%" ? (
                <span className="text-story-ink-2">About the same as the national average</span>
              ) : (
                <>
                  <span className="font-semibold">{signedPercent(share)}</span>{" "}
                  <span className="text-story-ink-2">
                    {share > 0 ? "more people per seat" : "fewer people per seat"}
                  </span>
                </>
              )}
            </dd>
          </div>
          <div className="col-span-2">
            <dt className="text-xs text-story-muted">Its next seat</dt>
            <dd className="text-story-ink">
              {nextAt === null ? (
                <>
                  Its {ordinal(seats + 1)} seat would need a House larger than{" "}
                  {SWEEP_STOP.toLocaleString("en-US")}.
                </>
              ) : (
                <>
                  Its {ordinal(seats + 1)} seat comes at a House of{" "}
                  <span className="font-semibold tabular-nums">{nextAt.toLocaleString("en-US")}</span>
                  <span className="text-story-ink-2 tabular-nums"> (+{(nextAt - size).toLocaleString("en-US")})</span>
                </>
              )}
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-story-muted">
          <Link
            href={`/districts/explore?state=${state.fips}`}
            className="underline decoration-story-axis underline-offset-2 hover:text-story-ink"
          >
            See {state.name}’s district plan
          </Link>{" "}
          (today’s 435 seats)
        </p>
      </div>
      <SeatLadder state={state} size={size} seats={seats} />
    </div>
  );
}

/**
 * Ladder ticks: 1, 2 and 5 times each power of ten inside the range, or
 * the next finer steps when that gives fewer than three. A narrow range
 * (big delegations, whose claims sit close together) gets evenly spaced
 * round values instead.
 */
function logTicks(lo: number, hi: number): number[] {
  if (hi / lo < 1.5) {
    const raw = (hi - lo) / 3;
    const power = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 5, 10].map((m) => m * power).find((candidate) => candidate >= raw) ?? raw;
    const ticks: number[] = [];
    for (let tick = Math.ceil(lo / step) * step; tick <= hi; tick += step) ticks.push(tick);
    return ticks;
  }
  const within = (steps: readonly number[]) => {
    const ticks: number[] = [];
    for (let power = Math.floor(Math.log10(lo)); power <= Math.ceil(Math.log10(hi)); power++) {
      for (const step of steps) {
        const tick = step * 10 ** power;
        if (tick >= lo && tick <= hi) ticks.push(tick);
      }
    }
    return ticks;
  };
  for (const steps of [[1, 2, 5], [1, 2, 3, 5], [1, 2, 3, 5, 7]]) {
    const ticks = within(steps);
    if (ticks.length >= 3) return ticks;
  }
  return within([1, 1.5, 2, 3, 4, 5, 6, 7, 8]);
}

const compactNumber = new Intl.NumberFormat("en-US", { notation: "compact", maximumSignificantDigits: 3 });
const MAX_CLAIMS = 40;

/**
 * One state's claims to its 2nd, 3rd, ... seats as dots on a log scale,
 * against the line set by the claim that won the last seat dealt: every
 * claim above it won a seat. Big delegations show their last 40 claims.
 */
function SeatLadder({ state, size, seats }: { state: EssayState; size: number; seats: number }) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const height = 200;
  const cutoff = winningClaim(size).priority;
  const last = seats + 2;
  const first = Math.max(2, last - MAX_CLAIMS + 1);
  const claims = Array.from({ length: last - first + 1 }, (_, i) => ({
    seat: first + i,
    priority: claimFor(state.population, first + i),
  }));
  // The scale fits the claims shown, padded by a sixth of their own range,
  // so a big delegation's close-together claims still spread out.
  const values = [...claims.map((c) => c.priority), cutoff];
  const pad = Math.exp(Math.max(0.01, Math.log(Math.max(...values) / Math.min(...values)) / 6));
  const lo = Math.min(...values) / pad;
  const hi = Math.max(...values) * pad;
  const plot = { left: 40, right: Math.max(60, width - 8), top: 40, bottom: height - 22 };
  const y = (v: number) => plot.bottom - ((Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))) * (plot.bottom - plot.top);
  const step = (plot.right - plot.left) / claims.length;
  const radius = Math.max(2.5, Math.min(6, step * 0.34));
  const x = (i: number) => plot.left + (i + 0.5) * step;
  const won = seats - 1;

  return (
    <figure>
      <div ref={ref} className="relative" style={{ height }}>
        {width > 0 ? (
          <svg
            width={width}
            height={height}
            role="img"
            aria-label={`${state.name}'s claims to its ${ordinal(first)} through ${ordinal(last)} seats against the claim that won seat ${size}: ${won} won a seat.`}
            className="overflow-visible font-sans"
          >
            <text x={0} y={10} fontSize={11} fill={INK.muted}>
              Claims to each seat (logarithmic scale)
            </text>
            {/* The line's key sits above the plot: near the line, big
                delegations' claims crowd any label. */}
            <line x1={0} x2={18} y1={24} y2={24} stroke="var(--gap-more-3)" strokeWidth={1.5} strokeDasharray="5 4" />
            <text x={24} y={24} dy="0.32em" fontSize={11} fontWeight={600} fill="var(--gap-more-3)" className="tabular-nums">
              The claim that won seat {size.toLocaleString("en-US")}: {Math.round(cutoff).toLocaleString("en-US")}
            </text>
            {logTicks(lo, hi).map((tick) => (
              <g key={tick}>
                <line x1={plot.left} x2={plot.right} y1={y(tick)} y2={y(tick)} stroke={INK.grid} />
                <text x={plot.left - 6} y={y(tick)} dy="0.32em" textAnchor="end" fontSize={10} fill={INK.muted}>
                  {compactNumber.format(tick)}
                </text>
              </g>
            ))}
            {claims.map((claim, i) => {
              const win = claim.seat <= seats;
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
            <line
              x1={plot.left - 4}
              x2={plot.right + 4}
              y1={y(cutoff)}
              y2={y(cutoff)}
              stroke="var(--gap-more-3)"
              strokeWidth={1.5}
              strokeDasharray="5 4"
            />
            <text x={x(0)} y={plot.bottom + 15} textAnchor="middle" fontSize={10} fill={INK.muted}>
              {ordinal(first)}
            </text>
            <text x={x(claims.length - 1)} y={plot.bottom + 15} textAnchor="middle" fontSize={10} fill={INK.muted}>
              {ordinal(last)}
            </text>
          </svg>
        ) : null}
      </div>
      <figcaption className="mt-1 text-xs text-story-ink-2">
        {won === 0
          ? `${state.name} keeps only its guaranteed seat: its claim to a 2nd falls below the line.`
          : `Every claim above the line won a seat: ${won.toLocaleString("en-US")} on top of its guaranteed one.`}
      </figcaption>
    </figure>
  );
}
