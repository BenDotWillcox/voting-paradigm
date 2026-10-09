import Link from "next/link";
import * as React from "react";

import { FactSources } from "./fact-note";

/**
 * The answer to the question the essay opens with ("what would it take to
 * undo it?"): an ordinary law, and the choice between a new fixed number
 * and a rule that grows the House with each census.
 */
export function WhatItTakes() {
  return (
    <section
      id="what-it-takes"
      aria-labelledby="what-it-takes-heading"
      className="mx-auto mt-20 max-w-[38rem] px-4 font-story-serif text-[1.1875rem] leading-[1.7] text-story-ink"
    >
      <h2 id="what-it-takes-heading" className="text-3xl leading-tight font-medium tracking-[-0.01em] sm:text-4xl">
        What would it take to undo it?
      </h2>
      <p className="mt-6">
        No constitutional amendment. The size of the House is set by ordinary
        law: Congress chose 433 seats in 1911 and, in 1929, kept whatever
        number the House then had. It can change that number the same way,
        within the Constitution’s cap of one representative per 30,000
        people, and bills to enlarge the House were introduced as recently as
        the 118th Congress.
      </p>
      <p className="mt-6">
        The real decision is what kind of law. Congress could pick a new fixed
        number, as it did in 1911, and the population would keep growing past
        it, as it has grown past 435. Or it could adopt a rule that recomputes
        the size after every census, such as the Wyoming Rule or the cube
        root, so the House grows with the country.
      </p>
      <p className="mt-6">
        Either way, the choice settles how many people each member represents.
        It does not settle how evenly that number falls across states, or how
        well a larger House would work.
      </p>
      <FactSources
        ids={[
          "house-size-statutory",
          "apportionment-act-1911",
          "permanent-apportionment-act-1929-text",
          "wyoming-rule",
          "cube-root-law",
        ]}
      />
      <p className="mt-10 text-lg">
        Try any House size yourself: the{" "}
        <Link
          href="/apportionment/explore"
          className="underline decoration-story-axis underline-offset-4 hover:decoration-story-ink"
        >
          apportionment explorer
        </Link>{" "}
        resizes the House and assigns every seat.
      </p>
    </section>
  );
}
