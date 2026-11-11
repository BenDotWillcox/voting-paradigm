import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { LiquidDemo } from "@/components/liquid/liquid-demo";
import { getDelegationScenario, resolveBallotPaper } from "@/lib/delegation-api";
import type { DelegationScenario, ResolveBallotPaperResponse } from "@/types/delegation";

export const metadata: Metadata = {
  title: "Liquid democracy",
  description:
    "Hand categories of decisions, in your own words, to people you trust, then follow each ballot question through the delegation network to whoever ends up deciding.",
};

// The network is rebuilt by the Python service on request, never at build time.
export const dynamic = "force-dynamic";

async function load(): Promise<{
  scenario: DelegationScenario;
  initial: ResolveBallotPaperResponse;
} | null> {
  try {
    const scenario = await getDelegationScenario();
    const initial = await resolveBallotPaper({
      ballot_paper: scenario.ballot_papers[0].id,
      viewer_delegations: [],
      viewer_votes: {},
      threshold: scenario.threshold,
      tiebreak_seed: 0,
    });
    return { scenario, initial };
  } catch (error) {
    console.error("Error loading the liquid democracy scenario:", error);
    return null;
  }
}

export default async function LiquidPage() {
  const loaded = await load();

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <Link
        href="/"
        className="mb-7 inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        All demos
      </Link>
      <header className="mb-10 max-w-3xl space-y-3">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-700 dark:text-indigo-300">
          Demo 05 · Liquid democracy
        </p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Keep the decisions you care about. Hand the rest to people you trust.
        </h1>
        <p className="text-base leading-relaxed text-muted-foreground sm:text-lg">
          Nobody can research every question on a ballot, and one representative cannot
          match your views on everything. Here you delegate by category, in your own words,
          and each question is routed for each voter separately.
        </p>
        <nav aria-label="Demo sections" className="flex flex-wrap gap-x-6 gap-y-2 pt-2 text-sm">
          <a href="#delegations" className="text-indigo-700 underline-offset-4 hover:underline dark:text-indigo-300">
            01 · Your delegations
          </a>
          <a href="#ballot" className="text-indigo-700 underline-offset-4 hover:underline dark:text-indigo-300">
            02 · Run a ballot paper
          </a>
          <a href="#method" className="text-indigo-700 underline-offset-4 hover:underline dark:text-indigo-300">
            Method
          </a>
        </nav>
      </header>

      {loaded ? (
        <LiquidDemo scenario={loaded.scenario} initial={loaded.initial} />
      ) : (
        <div className="max-w-3xl rounded-lg border p-5 text-sm leading-relaxed text-muted-foreground">
          <p className="font-medium text-foreground">The delegation service is not reachable.</p>
          <p>
            This page resolves every ballot question through the Python service, which is
            not answering right now. Please try again shortly.
          </p>
        </div>
      )}

      <section id="method" className="mt-16 max-w-3xl scroll-mt-20 space-y-3 border-t pt-8 text-sm leading-relaxed text-muted-foreground">
        <h2 className="text-base font-semibold text-foreground">Method and limits</h2>
        <p>
          The network is synthetic and seeded{loaded ? ` (seed ${loaded.scenario.seed})` : ""}:
          three districts of 80 residents, 20 people outside the city who can still be
          delegates, and you. A third keep every decision, the rest hand three to seven
          categories to a well-known person or a neighbour. Those behaviours and their
          shares are assumptions chosen to make delegation visible, not data about real
          voters, and everyone&apos;s yes or no comes from a toy one-dimensional model.
        </p>
        <p>
          Whether a question is about a category is one yes/no judgment from a hosted
          decision model{loaded ? ` (${loaded.scenario.model})` : ""}. The model is not
          repeatable to the last digit, so its first answer is recorded and every run
          replays the record. On a labelled set of 68 questions and 30 categories, routing
          at the 0.7 threshold sent 4 of 292 delegated votes to a category the question was
          not about and kept 21 of 309 that had an acceptable category. One author wrote
          both the categories and the labels.
        </p>
        <p>
          A delegation that would close a loop within one category is refused when it is
          made. A loop that only appears for some questions is allowed with a warning, and
          when it happens everyone on it keeps their own decision, so every vote ends with
          exactly one person. A ballot counted for you is a copy of that person&apos;s ballot;
          there are no weighted votes. Nothing you enter here is stored.
        </p>
      </section>
    </main>
  );
}
