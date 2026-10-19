"use client";

import * as React from "react";

import { useStateFocus } from "@/components/apportionment/essay/state-focus";
import { ordinal } from "@/components/apportionment/essay/deal-figure";
import { SWEEP_STOP, nextClaims, winningClaim, type Claim } from "@/lib/apportionment/house-sizes";
import { INK } from "@/lib/story/palette";

const SHOWN = 8;

/**
 * The race for the next seat at the chosen size, drawn like the essay's:
 * every state's claim to its next seat, strongest first, and the reader's
 * state on its own row when it's out of the running. Adding the seat moves
 * the House up by one, so the reader can deal seats one at a time.
 */
export function NextSeat({ size, onAdd }: { size: number; onAdd: () => void }) {
  const { states, focus } = useStateFocus();
  const nameOf = (fips: string) => states.find((state) => state.fips === fips)?.name ?? fips;
  const claims = React.useMemo(() => nextClaims(size), [size]);
  const last = React.useMemo(() => winningClaim(size), [size]);
  const shown = claims.slice(0, SHOWN);
  const focusRank = focus ? claims.findIndex((claim) => claim.fips === focus.fips) : -1;
  const focusRow = focusRank >= SHOWN ? claims[focusRank] : null;
  const top = shown[0].priority;
  const atLimit = size >= SWEEP_STOP;

  return (
    <section aria-labelledby="next-seat-title" className="font-sans">
      <h2 id="next-seat-title" className="font-story-serif text-2xl font-medium text-story-ink">
        Who gets the next seat?
      </h2>
      <p className="mt-1 text-sm text-story-ink-2">
        Seat {size.toLocaleString("en-US")} went to {nameOf(last.fips)}, its {ordinal(last.seat)}. Seat{" "}
        {(size + 1).toLocaleString("en-US")} goes to the strongest claim: a state’s population ÷ √(<i>n</i> × (
        <i>n</i> − 1)) for its <i>n</i>th seat.
      </p>
      <ol className="mt-3 space-y-1">
        {shown.map((claim, rank) => (
          <ClaimRow
            key={claim.fips}
            claim={claim}
            name={nameOf(claim.fips)}
            width={claim.priority / top}
            lead={rank === 0}
            mine={claim.fips === focus?.fips}
            tag={rank === 0 ? `→ seat ${(size + 1).toLocaleString("en-US")}` : undefined}
            shortTag={rank === 0 ? "wins" : undefined}
          />
        ))}
        {focusRow ? (
          <>
            <li aria-hidden="true" className="border-t border-dashed border-story-rule" />
            <ClaimRow
              claim={focusRow}
              name={nameOf(focusRow.fips)}
              width={focusRow.priority / top}
              lead={false}
              mine
              tag={`${ordinal(focusRank + 1)} in line`}
              shortTag={ordinal(focusRank + 1)}
            />
          </>
        ) : null}
      </ol>
      <button
        type="button"
        onClick={onAdd}
        disabled={atLimit}
        className="mt-4 rounded-full bg-story-ink px-4 py-1.5 text-sm font-medium text-story-page shadow-sm transition-opacity hover:opacity-90 disabled:opacity-40"
      >
        Add seat {(size + 1).toLocaleString("en-US")}
      </button>
      {atLimit ? (
        <p className="mt-2 text-xs text-story-muted">
          {SWEEP_STOP.toLocaleString("en-US")} seats is the largest House the 30,000-person benchmark allows.
        </p>
      ) : null}
    </section>
  );
}

function ClaimRow({
  claim,
  name,
  width,
  lead,
  mine,
  tag,
  shortTag,
}: {
  claim: Claim;
  name: string;
  width: number;
  lead: boolean;
  mine: boolean;
  tag?: string;
  /** The tag on phones, where the long one would squeeze the bars. */
  shortTag?: string;
}) {
  const color = mine ? "var(--story-seat-focus)" : lead ? INK.primary : "var(--story-seat)";
  return (
    // The same columns on every row, so the leader's tag never squeezes its bar.
    <li className="grid grid-cols-[6.5rem_minmax(0,1fr)_4rem_2.25rem] items-center gap-2 text-xs sm:grid-cols-[10rem_minmax(0,1fr)_5rem_6.75rem] sm:text-sm">
      <span className="truncate text-right" style={{ color: lead || mine ? INK.primary : INK.secondary, fontWeight: lead ? 700 : 500 }}>
        {name}
        <span className="font-normal text-story-muted"> · {ordinal(claim.seat)}</span>
      </span>
      <span className="h-3">
        <span
          className="block h-full rounded-sm transition-[width] duration-300 ease-out"
          style={{ width: `${Math.max(1, width * 100).toFixed(1)}%`, background: color }}
        />
      </span>
      <span className="text-right tabular-nums" style={{ color: lead ? INK.primary : INK.secondary, fontWeight: lead ? 700 : 400 }}>
        {Math.round(claim.priority).toLocaleString("en-US")}
      </span>
      <span className={lead ? "text-xs font-semibold whitespace-nowrap text-[var(--gap-more-3)]" : "text-xs whitespace-nowrap text-story-muted"}>
        <span className="sm:hidden">{shortTag}</span>
        <span className="hidden sm:inline">{tag}</span>
      </span>
    </li>
  );
}
