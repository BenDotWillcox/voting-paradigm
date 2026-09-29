import type { Metadata } from "next";
import Link from "next/link";

import { Prose, StoryHeader, StoryRoot } from "@/components/story/story-layout";

export const metadata: Metadata = {
  title: "Apportionment · Nebula Civitas",
  description:
    "The House has been capped at 435 seats since 1929. How big would it have to be for every state's districts to be the same size?",
};

/**
 * Story cover for demo 4. The full scrollytelling story replaces the body
 * in a later phase of prompts/storytelling-redesign.md; the interactive
 * explorer lives at /apportionment/explore.
 */
export default function ApportionmentStoryPage() {
  return (
    <StoryRoot>
      <StoryHeader
        kicker="Apportionment"
        title="The House stopped growing"
        dek="Congress capped the House at 435 seats in 1929. The country has nearly tripled since. Districts grew, and because seats come in whole numbers, they grew unequally from state to state."
      />
      <Prose>
        <p>
          A representative from Delaware serves nearly twice as many people as
          one from Montana. The popular fixes, such as sizing the House to the
          smallest state, barely narrow that gap: it only closes once the House
          grows past about a thousand seats.
        </p>
        <p>
          This page is becoming a scrolling story about why. Until then, the{" "}
          <Link href="/apportionment/explore">apportionment explorer</Link>{" "}
          lets you resize the House and watch seats assigned one at a time.
        </p>
      </Prose>
    </StoryRoot>
  );
}
