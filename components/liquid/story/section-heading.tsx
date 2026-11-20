import * as React from "react";

import { cn } from "@/lib/utils";

import { ClaimLabel, type Claim } from "./claim-label";

/*
 * Plain page primitives for the walkthrough. Deliberately neutral: the page
 * gets its own design once its content is complete, and does not borrow the
 * essays' editorial look meanwhile.
 */

/** A section's heading, with what the section may claim beside its kicker. */
export function LiquidHeading({
  id,
  kicker,
  claim,
  children,
}: {
  id: string;
  kicker: string;
  claim: Claim;
  children: React.ReactNode;
}) {
  return (
    <div id={id} className="mx-auto mt-24 mb-4 max-w-2xl scroll-mt-16 px-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium text-story-muted">{kicker}</p>
        <ClaimLabel claim={claim} />
      </div>
      <h2 className="mt-2 text-2xl font-semibold tracking-tight text-balance text-story-ink sm:text-3xl">
        {children}
      </h2>
    </div>
  );
}

/** A column of body text. */
export function LiquidText({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "mx-auto max-w-2xl space-y-4 px-4 text-base leading-relaxed text-story-ink [&_strong]:font-semibold",
        "[&_a]:underline [&_a]:underline-offset-4",
        className
      )}
    >
      {children}
    </div>
  );
}

/** Room for a figure between columns of text. */
export function LiquidFigure({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto my-10 max-w-4xl px-4">{children}</div>;
}
