import * as React from "react";

import { ClaimLabel, type Claim } from "./claim-label";

/** A walkthrough section's heading, with what the section may claim beside its kicker. */
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
    <div id={id} className="mx-auto mt-28 mb-2 max-w-[38rem] scroll-mt-16 px-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium tracking-wide text-story-accent">{kicker}</p>
        <ClaimLabel claim={claim} />
      </div>
      <h2 className="mt-2 font-story-serif text-3xl leading-tight font-medium tracking-[-0.01em] text-balance sm:text-4xl">
        {children}
      </h2>
    </div>
  );
}
