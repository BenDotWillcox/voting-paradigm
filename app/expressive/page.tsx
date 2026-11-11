import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { ScalarComparison } from "@/components/expressive/scalar-comparison";

export const metadata: Metadata = {
  title: "Expressive ballots",
  description:
    "Compare a yes/no tax question with a richer ballot, explore 100 voters’ preferences, and see how those same ballots combine into a tax rate.",
};

export default function ExpressivePage() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <Link
        href="/"
        className="mb-7 inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        All demos
      </Link>
      <header className="mb-8 max-w-3xl space-y-3">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">
          Demo 06 · Expressive ballots
        </p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          A ballot can say more than a single choice.
        </h1>
        <p className="text-base leading-relaxed text-muted-foreground sm:text-lg">
          What does a yes or no leave unsaid? Answer Colorado’s 2022 tax question two ways,
          then see what changes when a ballot can express room for compromise.
        </p>
        <nav aria-label="Demo sections" className="flex flex-wrap gap-x-6 gap-y-2 pt-2 text-sm">
          <a href="#rate-ballot" className="text-teal-700 underline-offset-4 hover:underline">01 · Two ways to answer</a>
          <a href="#ballot-comparison" className="text-teal-700 underline-offset-4 hover:underline">02 · Compare the results</a>
        </nav>
      </header>
      <ScalarComparison />
    </main>
  );
}
