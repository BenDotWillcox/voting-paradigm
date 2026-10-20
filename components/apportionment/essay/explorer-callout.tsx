"use client";

import Link from "next/link";

import { sizeForSeat } from "@/lib/apportionment/house-sizes";

import { ordinal } from "./deal-figure";
import { saveReturnPoint } from "./return-point";
import { useStateFocus } from "./state-focus";

/**
 * The essay's last invitation to the explorer, about the reader's state
 * when they chose one: its seats today and the House size at which it
 * would gain its next.
 */
export function ExplorerCallout() {
  const { focus } = useStateFocus();
  const nextAt = focus ? sizeForSeat(focus.fips, focus.seats + 1) : null;
  const href = focus ? `/apportionment/explore?state=${focus.abbr.toLowerCase()}` : "/apportionment/explore";

  return (
    <aside
      aria-labelledby="explorer-callout-title"
      className="mt-12 rounded-xl bg-story-surface p-5 font-sans ring-1 ring-story-rule sm:p-6"
    >
      <p className="text-sm text-story-muted">Try it yourself</p>
      <h3 id="explorer-callout-title" className="mt-1 font-story-serif text-2xl leading-snug font-medium text-story-ink">
        {focus ? `See how ${focus.name} does at any House size` : "See how your state does at any House size"}
      </h3>
      <p className="mt-2 text-base leading-relaxed text-story-ink-2">
        {focus ? (
          <>
            {focus.name} has {focus.seats} {focus.seats === 1 ? "seat" : "seats"} today
            {nextAt !== null ? (
              <>
                ; its {ordinal(focus.seats + 1)} would come at a House of{" "}
                <span className="font-semibold text-story-ink tabular-nums">{nextAt.toLocaleString("en-US")}</span> seats
              </>
            ) : null}
            . Pick any size from 435 to 11,036 and see its seats, its people per seat, and both gaps.
          </>
        ) : (
          <>
            Pick any size from 435 to 11,036 and see how the seats divide among the states, both gaps, the cost, and
            who gets each next seat.
          </>
        )}
      </p>
      <Link
        href={href}
        onClick={saveReturnPoint}
        className="mt-4 inline-flex items-center rounded-full bg-story-ink px-5 py-2 text-sm font-medium text-story-page shadow-sm transition-opacity hover:opacity-90"
      >
        Open the explorer →
      </Link>
    </aside>
  );
}
