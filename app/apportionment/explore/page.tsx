import type { Metadata } from "next";
import Link from "next/link";

import { StateFocusProvider } from "@/components/apportionment/essay/state-focus";
import { BackToEssay } from "@/components/apportionment/explorer/back-to-essay";
import { SizeExplorer } from "@/components/apportionment/explorer/size-explorer";
import { StoryRoot } from "@/components/story/story-layout";
import { loadEssayData } from "@/lib/apportionment/essay-data";
import {
  MEMBER_ALLOWANCE,
  MEMBER_SALARY,
  SWEEP_START,
  SWEEP_STOP,
  clampSize,
} from "@/lib/apportionment/house-sizes";

export const metadata: Metadata = {
  title: "Apportionment explorer · Nebula Civitas",
  description:
    "Try any House size from 435 to 11,036 seats: how the seats divide among the states, both representation gaps, and the cost, from the 2020 census.",
};

interface ExplorePageProps {
  /** `size`, or `cap` from links to the old explorer. */
  searchParams: Promise<{ size?: string; cap?: string }>;
}

/**
 * Demo 4's companion tool (prompts/demo-4-apportionment-essay.md): the
 * essay's Act IV at any House size. Every number comes from the same
 * module as the essay's (lib/apportionment/house-sizes.ts).
 */
export default async function ApportionmentExplorePage({ searchParams }: ExplorePageProps) {
  const { size, cap } = await searchParams;
  const data = await loadEssayData();

  return (
    <StoryRoot theme="apportionment">
      <StateFocusProvider states={data.states}>
        <div className="mx-auto max-w-7xl px-4">
          <header className="pt-8 pb-8 sm:pt-10">
            <BackToEssay />
            <h1 className="mt-4 font-story-serif text-4xl leading-tight font-medium tracking-[-0.01em] sm:text-5xl">
              Try any House size
            </h1>
            <p className="mt-3 max-w-2xl font-story-serif text-lg leading-snug text-pretty text-story-ink-2 sm:text-xl">
              The essay stopped at five sizes. Pick any size from {SWEEP_START} to{" "}
              {SWEEP_STOP.toLocaleString("en-US")} seats to see how the seats would divide among the states, using the
              2020 census and the same calculation as the essay.
            </p>
          </header>
          <SizeExplorer initialSize={parseSize(size ?? cap)} />
          <section
            aria-labelledby="explorer-method"
            className="mt-16 max-w-3xl border-t border-story-rule pt-6 font-sans text-sm leading-relaxed text-story-ink-2"
          >
            <h2 id="explorer-method" className="font-story-serif text-xl font-medium text-story-ink">
              How these numbers are made
            </h2>
            <p className="mt-2">
              Seats are dealt by the method of equal proportions, in law since 1941: every state gets one seat, then
              each further seat goes to the strongest claim. The populations are the 2020 census apportionment counts of
              the 50 states; the District of Columbia and the territories send non-voting delegates and are left out.
              People per seat is a state’s average: its population divided by its seats.
            </p>
            <p className="mt-2">
              Costs multiply the number of seats by a member’s salary (${MEMBER_SALARY.toLocaleString("en-US")}) and
              the average office allowance (${MEMBER_ALLOWANCE.toLocaleString("en-US")}), from the Congressional
              Research Service: an estimate at today’s rates, not a forecast.
            </p>
            <p className="mt-2">
              The essay and this page share one calculation, and a test checks it against the Python build at every
              size from {SWEEP_START} to {SWEEP_STOP.toLocaleString("en-US")}. Sources and caveats are in the
              essay’s{" "}
              <Link
                href="/apportionment#methods"
                className="underline decoration-story-axis underline-offset-4 hover:text-story-ink"
              >
                Methods &amp; sources
              </Link>
              .
            </p>
          </section>
        </div>
      </StateFocusProvider>
    </StoryRoot>
  );
}

function parseSize(raw: string | undefined): number {
  const value = Number.parseInt(raw ?? "", 10);
  return Number.isFinite(value) ? clampSize(value) : SWEEP_START;
}
