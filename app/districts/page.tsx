import type { Metadata } from "next";
import Link from "next/link";

import { Prose, StoryHeader, StoryRoot } from "@/components/story/story-layout";

export const metadata: Metadata = {
  title: "Districting · Nebula Civitas",
  description:
    "Congressional lines are drawn by hand. What would a transparent, population-first algorithm draw instead?",
};

/**
 * Story cover for demo 3. The full scrollytelling story replaces the body
 * in Phase 3 of prompts/storytelling-redesign.md; the interactive explorer
 * lives at /districts/explore.
 */
export default function DistrictsStoryPage() {
  return (
    <StoryRoot>
      <StoryHeader
        kicker="Districting"
        title="Who draws the lines"
        dek="Every ten years, states redraw their congressional districts. In most, the legislature draws the map itself. An algorithm given only census data and an explicit rule can draw one anyone can reproduce."
      />
      <Prose>
        <p>
          This demo draws every state&rsquo;s districts with a balanced power
          diagram: a geometric method that groups census tracts around district
          centers until each district holds an equal share of the population.
          The same inputs and seed always produce the same map.
        </p>
        <p>
          This page is becoming a scrolling story that follows the algorithm
          step by step and compares its maps with the enacted ones. Until then,
          the <Link href="/districts/explore">districting explorer</Link> shows
          the plan for every state, down to the census tract.
        </p>
      </Prose>
    </StoryRoot>
  );
}
