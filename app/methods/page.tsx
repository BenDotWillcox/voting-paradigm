import type { Metadata } from "next";
import Link from "next/link";

import { Prose, StoryHeader, StoryRoot } from "@/components/story/story-layout";

export const metadata: Metadata = {
  title: "Voting methods · Nebula Civitas",
  description:
    "Same voters, different winners: how the choice of voting method decides elections.",
};

/**
 * Story cover for demo 1. The full scrollytelling story (Condorcet cycle
 * first) replaces the body in Phase 2 of prompts/storytelling-redesign.md;
 * the interactive explorer lives at /methods/lab.
 */
export default function MethodsStoryPage() {
  return (
    <StoryRoot>
      <StoryHeader
        kicker="Voting methods"
        title="When the majority can’t make up its mind"
        dek="Three voters, three options, and every option loses a head-to-head vote. Majority rule has no answer, so every voting method invents one, and they don’t agree."
      />
      <Prose>
        <p>
          The same ballots can elect different winners depending on how they
          are counted. Plurality, instant-runoff, Borda, Ranked Pairs, score,
          approval, and quadratic voting each resolve disagreement in their own
          way, and each fails a different fairness criterion.
        </p>
        <p>
          This page is becoming a scrolling story that starts from a Condorcet
          cycle and works outward. Until then, the{" "}
          <Link href="/methods/lab">methods lab</Link> runs every method on the
          same electorates, with controls for polarization, strategy, and
          turnout.
        </p>
      </Prose>
    </StoryRoot>
  );
}
