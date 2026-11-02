"use client";

import { ArrowRight, Code2, ExternalLink } from "lucide-react";

import type { StepId } from "@/lib/methods/sections";
import type { SimulationRate, SimulationSummary, SpecimenSearch } from "@/types/methods";

import { CorrectnessCheck } from "./correctness-check";

const linkButton = "inline-flex min-h-11 items-center justify-center gap-2 rounded-[3px] border border-mi-rule px-3 py-2 text-left text-sm font-medium text-mi-ink hover:bg-mi-wash focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink";
const number = (value: number) => value.toLocaleString("en-US");
const percent = (value: number, digits = 1) => `${(value * 100).toFixed(digits)}%`;

/** A concrete study finding and a runnable check of a known package guarantee. */
export function TestingOverview({ searches, simulation, onOpen, onImplementation }: {
  searches: SpecimenSearch[];
  simulation: SimulationSummary;
  onOpen: (step: StepId) => void;
  onImplementation: () => void;
}) {
  const specimenCount = new Set(searches.flatMap((search) => search.specimen ? [search.specimen.id] : [])).size;
  const methodCount = new Set(searches.map((search) => search.method)).size;
  const criterionCount = new Set(searches.map((search) => search.criterion)).size;
  const elections = simulation.by_candidates.reduce((sum, group) => sum + group.elections, 0);
  const finding = simulation.by_candidates.find((group) => group.candidates === 5);
  const plurality = finding?.condorcet_efficiency.plurality;
  const rankedPairs = finding?.condorcet_efficiency.ranked_pairs;

  return (
    <div className="min-w-0 space-y-6">
      {finding && plurality && rankedPairs && plurality.of > 0 ? (
        <section className="min-w-0 space-y-4 rounded-[4px] border border-mi-rule p-4 sm:p-5" aria-label="A finding from the saved simulation">
          <div>
            <p className="text-sm font-medium text-mi-ink-2">Simulation finding · {finding.candidates} candidates</p>
            <h3 className="mt-2 max-w-3xl text-xl font-semibold leading-snug text-mi-ink">Plurality missed a head-to-head winner {percent((plurality.of - plurality.count) / plurality.of)} of the time.</h3>
            <p className="mt-3 max-w-3xl text-base leading-relaxed text-mi-ink-2">
              In {number(finding.condorcet_winner.count)} of {number(finding.elections)} simulated elections, one candidate was preferred to every rival in a head-to-head race: the Condorcet winner. Among those elections, the methods elected that candidate at different rates.
            </p>
          </div>
          <div className="grid min-w-0 gap-3 sm:grid-cols-2" aria-label="Share electing the Condorcet winner when one exists">
            <FindingRate label="Plurality" value={plurality} />
            <FindingRate label="Ranked Pairs" value={rankedPairs} />
          </div>
          <p className="max-w-3xl text-sm leading-relaxed text-mi-ink-2">
            These rates describe this spatial preference model, with {simulation.config.voters} voters per election and <code className="font-mi-mono">{simulation.ballot_model}</code> ballots. Elections without a Condorcet winner are excluded. Intervals are {simulation.interval}; this is sampled evidence, not a prediction for real elections.
          </p>
          <button type="button" onClick={() => onOpen("efficiency")} className={linkButton}>Compare all seven methods <ArrowRight size={15} aria-hidden /></button>
        </section>
      ) : null}

      <CorrectnessCheck />

      <details className="min-w-0 rounded-[4px] border border-mi-rule p-4 sm:p-5">
        <summary className="min-h-11 cursor-pointer text-base font-medium text-mi-ink focus-visible:outline-2 focus-visible:outline-mi-ink">Explore the wider evidence</summary>
        <div className="grid min-w-0 gap-5 pt-2 lg:grid-cols-2">
          <section className="min-w-0 space-y-3">
            <h3 className="text-base font-semibold text-mi-ink">{number(specimenCount)} saved counterexamples</h3>
            <p className="text-sm leading-relaxed text-mi-ink-2">The gallery covers {methodCount} methods and {criterionCount} criteria, with saved ballots and results. Searches have stated bounds and ballot assumptions; a missing counterexample alone does not prove a criterion holds.</p>
            <div className="flex flex-wrap gap-2"><button type="button" onClick={() => onOpen("gallery")} className={linkButton}>Counterexample gallery</button><button type="button" onClick={() => onOpen("fairness")} className={linkButton}>Fairness criteria</button></div>
          </section>
          <section className="min-w-0 space-y-3">
            <h3 className="text-base font-semibold text-mi-ink">{number(elections)} seeded elections</h3>
            <p className="text-sm leading-relaxed text-mi-ink-2">Compare method disagreement across {simulation.config.candidate_counts.join(", ")} candidates, inspect one election, or explore the spatial model behind the results.</p>
            <div className="flex flex-wrap gap-2"><button type="button" onClick={() => onOpen("disagreement")} className={linkButton}>Method disagreement</button><button type="button" onClick={() => onOpen("one-election")} className={linkButton}>One election</button><button type="button" onClick={() => onOpen("atlas")} className={linkButton}>Spatial atlas</button></div>
          </section>
        </div>
        <dl className="mt-5 grid min-w-0 gap-3 border-t border-mi-rule pt-4 text-sm text-mi-ink-2 sm:grid-cols-2">
          <div><dt className="font-medium text-mi-ink">Election seed</dt><dd className="font-mi-mono">{simulation.config.seed}</dd></div>
          <div><dt className="font-medium text-mi-ink">Tiebreak seed</dt><dd className="font-mi-mono">{simulation.config.tiebreak_seed}</dd></div>
          <div className="min-w-0 sm:col-span-2"><dt className="font-medium text-mi-ink">Saved benchmark</dt><dd className="break-words font-mi-mono">{simulation.benchmark}</dd></div>
          <div className="min-w-0 sm:col-span-2"><dt className="font-medium text-mi-ink">Source SHA-256</dt><dd className="break-all font-mi-mono">{simulation.source_sha256}</dd></div>
        </dl>
      </details>

      <section className="space-y-4 rounded-[4px] bg-mi-wash p-4 sm:p-5" aria-label="Continue with the Python package">
        <h3 className="text-lg font-semibold text-mi-ink">Take the package with you.</h3>
        <p className="max-w-3xl text-base leading-relaxed text-mi-ink-2">Choose a method, inspect its source, and copy a runnable example with the ballots and assertions included.</p>
        <div className="flex flex-wrap gap-3">
          <button type="button" onClick={onImplementation} className={linkButton}><Code2 size={17} aria-hidden /> Reproduce a count</button>
          <a href="https://github.com/BenDotWillcox/voting-paradigm" className={linkButton}>Open the repository <ExternalLink size={15} aria-hidden /></a>
        </div>
      </section>
    </div>
  );
}

function FindingRate({ label, value }: { label: string; value: SimulationRate }) {
  const rate = value.of > 0 ? value.count / value.of : 0;
  return (
    <div className="min-w-0 space-y-3 rounded-[3px] bg-mi-wash p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2"><p className="font-medium text-mi-ink">{label}</p><p className="font-mi-mono text-2xl text-mi-ink">{percent(rate)}</p></div>
      <div aria-hidden className="h-2 overflow-hidden rounded-sm bg-mi-rule"><div className="h-full bg-mi-ink" style={{ width: `${rate * 100}%` }} /></div>
      <p className="text-sm leading-relaxed text-mi-ink-2">{number(value.count)} / {number(value.of)} elected the Condorcet winner.<span className="mt-1 block">95% interval: {percent(value.interval[0], 2)}–{percent(value.interval[1], 2)}</span></p>
    </div>
  );
}
