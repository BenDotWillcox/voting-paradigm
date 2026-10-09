import type { Metadata } from "next";

import { Coda } from "@/components/apportionment/essay/coda";
import { HouseStory } from "@/components/apportionment/essay/house-story";
import { IntroScene } from "@/components/apportionment/essay/intro-scene";
import { MethodsAndSources } from "@/components/apportionment/essay/methods";
import { PersonaProvider } from "@/components/apportionment/essay/persona";
import { PersonHandoff } from "@/components/apportionment/essay/person-handoff";
import { StateFocusProvider } from "@/components/apportionment/essay/state-focus";
import { StoryNav } from "@/components/apportionment/essay/story-nav";
import { TearText } from "@/components/apportionment/essay/tear-text";
import { WhatItTakes } from "@/components/apportionment/essay/what-it-takes";
import { StoryRoot } from "@/components/story/story-layout";
import { loadEssayData } from "@/lib/apportionment/essay-data";

export const metadata: Metadata = {
  title: "The Representation Gap · Nebula Civitas",
  description:
    "For more than a century, the House of Representatives grew with the country. Then Congress froze it at 435 seats. What did that decision cost, and what would it take to undo it?",
};

/**
 * Demo 4: the apportionment essay (prompts/demo-4-apportionment-essay.md).
 * Static: every figure is built from the committed artifacts in
 * public/data/apportionment-story/, and every cited claim resolves to a
 * verified entry in data/apportionment/facts.json at build time.
 */
export default async function ApportionmentStoryPage() {
  const data = await loadEssayData();
  const present = data.history[data.history.length - 1];
  const nationalAverage = Math.round(data.totalPopulation / present.houseSize);

  return (
    <StoryRoot theme="apportionment">
      <StateFocusProvider states={data.states}>
        <PersonaProvider>
          {/* At least a screen tall, so the next section starts below the fold. */}
          <div className="min-h-svh">
            <header id="top" className="mx-auto max-w-5xl px-4 pt-12 pb-6 text-center sm:pt-14">
              <h1 className="font-story-serif text-5xl leading-[1.05] font-medium tracking-[-0.02em] sm:text-7xl lg:text-[5.25rem]">
                <TearText left="The Representation" right="Gap" />
              </h1>
              <p className="mx-auto mt-5 max-w-2xl font-story-serif text-xl leading-snug text-pretty text-story-ink-2 sm:text-2xl">
                For more than a century, the House of Representatives grew with
                the country. Then Congress froze it at 435 seats. What did that
                decision cost, and what would it take to undo it?
              </p>
            </header>
            <IntroScene seats={present.stateSeats} nationalAverage={nationalAverage} />
          </div>
          <PersonHandoff />
          <HouseStory data={data} />
          <Coda />
          <WhatItTakes />
          <MethodsAndSources />
          <StoryNav />
        </PersonaProvider>
      </StateFocusProvider>
    </StoryRoot>
  );
}
