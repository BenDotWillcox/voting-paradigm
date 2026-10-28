"use client";

import { ArrowDown, Code2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { AtlasView } from "@/lib/methods/atlas";
import { percent } from "@/lib/methods/simulation";
import { cn } from "@/lib/utils";
import type { ProfileResolveResponse, SampleElection, SimulationSummary } from "@/types/methods";

import { DisagreementStep, EfficiencyStep } from "./at-scale";
import { Atlas, type AtlasPoint } from "./atlas";
import { CorrectnessCheck } from "./correctness-check";
import { Subhead } from "./section-band";
import { SampleElectionView } from "./walkthrough";

const button = "inline-flex min-h-11 items-center justify-center gap-2 rounded-[3px] border border-mi-rule px-3 py-2 text-left text-sm font-medium text-mi-ink hover:bg-mi-wash focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink";
const panel = "min-w-0 scroll-mt-24 rounded-[4px] border border-mi-rule bg-mi-surface p-4 sm:p-6 lg:p-8";
const number = (value: number) => value.toLocaleString("en-US");

/** Saved study results, followed by an explorable view of the spatial model. */
export function SimulationEvidence({ simulation, samples, onAtlasPoint, onImplementation }: {
  simulation: SimulationSummary;
  samples: SampleElection[];
  onAtlasPoint: (response: ProfileResolveResponse, point: AtlasPoint, view: AtlasView) => void;
  onImplementation: () => void;
}) {
  const [sampleId, setSampleId] = useState<SampleElection["id"]>("split");
  const sample = samples.find((item) => item.id === sampleId) ?? samples[0];
  const finding = simulation.by_candidates.find((group) => group.candidates === 5);
  const plurality = finding?.condorcet_efficiency.plurality;
  const rankedPairs = finding?.condorcet_efficiency.ranked_pairs;
  const elections = simulation.by_candidates.reduce((total, group) => total + group.elections, 0);

  return (
    <div className="min-w-0 space-y-6 text-mi-ink [&_.text-xs]:text-sm [&_button]:min-h-11">
      <div className="grid gap-5 border-l-2 border-mi-ink pl-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start sm:pl-6">
        <p className="max-w-3xl text-base leading-relaxed text-mi-ink-2">
          Chosen examples show what can happen. These {number(elections)} seeded elections show how often it happened in one spatial preference model: {simulation.config.voters} voters, {simulation.config.candidate_counts.join(", ")} candidates, and the same <code className="font-mi-mono">{simulation.ballot_model}</code> ballot rules for every method. They describe this model, not a forecast of real elections.
        </p>
        <div className="flex flex-wrap gap-x-5 gap-y-2 font-mi-mono text-sm text-mi-ink-2 sm:flex-col sm:text-right" aria-label="Simulation scope">
          <span>{number(simulation.config.elections)} elections per size</span>
          <span>Seed {simulation.config.seed}</span>
        </div>
      </div>

      <section id="efficiency" className={panel} aria-labelledby="efficiency-heading">
        <div className="mb-6 grid gap-5 xl:grid-cols-[minmax(0,1fr)_20rem] xl:items-start">
          <div className="space-y-3">
            <Subhead tone={3} number="03.1">Recognizing a head-to-head winner</Subhead>
            <h3 id="efficiency-heading" className="max-w-3xl text-xl font-semibold leading-snug tracking-[-0.02em] sm:text-2xl">
              {plurality && plurality.of > 0 ? `With five candidates, Plurality missed the Condorcet winner ${((1 - plurality.count / plurality.of) * 100).toFixed(1)}% of the time.` : "Which methods find the Condorcet winner?"}
            </h3>
            {finding && plurality && rankedPairs ? <p className="max-w-3xl text-base leading-relaxed text-mi-ink-2">A Condorcet winner existed in {number(finding.condorcet_winner.count)} of {number(finding.elections)} five-candidate elections. Among those elections, Plurality elected it {number(plurality.count)} times; Ranked Pairs elected it {number(rankedPairs.count)} times.</p> : null}
          </div>
          {plurality && rankedPairs ? <dl className="grid grid-cols-2 gap-4 rounded-[3px] bg-mi-wash p-4" aria-label="Five-candidate Condorcet efficiency">
            <div><dt className="text-sm text-mi-ink-2">Plurality</dt><dd className="mt-1 font-mi-mono text-2xl tabular-nums sm:text-3xl">{percent(plurality)}</dd></div>
            <div><dt className="text-sm text-mi-ink-2">Ranked Pairs</dt><dd className="mt-1 font-mi-mono text-2xl tabular-nums sm:text-3xl">{percent(rankedPairs, 0)}</dd></div>
          </dl> : null}
        </div>
        <EfficiencyStep summary={simulation} />
        <p className="mt-5 border-t border-mi-rule pt-4 text-sm leading-relaxed text-mi-ink-2">The denominator is elections with a Condorcet winner. Finding that winner is one criterion; this plot does not rank every democratic value. The table includes 95% intervals for the rates, along with tiebreak rates.</p>
      </section>

      <section id="disagreement" className={panel} aria-labelledby="disagreement-heading">
        <div className="mb-6 max-w-3xl space-y-3">
          <Subhead tone={3} number="03.2">When methods part ways</Subhead>
          <h3 id="disagreement-heading" className="text-xl font-semibold leading-snug tracking-[-0.02em] sm:text-2xl">How often does changing the method change the winner?</h3>
          <p className="text-base leading-relaxed text-mi-ink-2">Every cell compares two methods on the same elections. Switch the number of candidates to see how their agreement changes within this study.</p>
        </div>
        <DisagreementStep summary={simulation} />
      </section>

      <section id="atlas" className={panel} aria-labelledby="atlas-heading">
        <div className="mb-6 max-w-3xl space-y-3">
          <Subhead tone={3} number="03.3">See the geography of a decision</Subhead>
          <h3 id="atlas-heading" className="text-xl font-semibold leading-snug tracking-[-0.02em] sm:text-2xl">Same preference space. Different winner regions.</h3>
          <p className="text-base leading-relaxed text-mi-ink-2">Each colored point represents a voter cloud centered there. Compare the methods’ maps, then select a point to inspect that electorate in the playground. These maps use a fixed cloud moved across a grid, separate from the random elections above.</p>
        </div>
        <LazyAtlas onLoadPoint={onAtlasPoint} />
      </section>

      {sample ? <details id="one-election" className={panel}>
        <summary className="min-h-11 cursor-pointer text-base font-semibold leading-relaxed focus-visible:outline-2 focus-visible:outline-mi-ink">Inspect one election behind the aggregate</summary>
        <div className="space-y-5 pt-3">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Sample election">
            {samples.map((item) => <button key={item.id} type="button" aria-pressed={sample.id === item.id} onClick={() => setSampleId(item.id)} className={cn(button, sample.id === item.id && "border-mi-ink bg-mi-wash")}>{item.id === "agree" ? "All methods agree" : "Different winners"}</button>)}
          </div>
          <SampleElectionView sample={sample} />
          <p className="text-sm leading-relaxed text-mi-ink-2">This is the first saved election matching the stated selection rule. {number(sample.matching)} of {number(sample.of)} elections with {sample.candidates} candidates matched that rule.</p>
        </div>
      </details> : null}

      <details id="correctness" className={panel}>
        <summary className="min-h-11 cursor-pointer text-base font-semibold leading-relaxed focus-visible:outline-2 focus-visible:outline-mi-ink">Reproduce a correctness check and inspect study provenance</summary>
        <div className="space-y-6 pt-3">
          <p className="max-w-3xl text-base leading-relaxed text-mi-ink-2">Simulation measures behavior on sampled inputs. A correctness check verifies an expected property on a known input. Both are useful, and they answer different questions.</p>
          <CorrectnessCheck />
          <dl className="grid min-w-0 gap-4 text-sm sm:grid-cols-2">
            <div><dt className="font-medium">Election seed</dt><dd className="mt-1 font-mi-mono text-mi-ink-2">{simulation.config.seed}</dd></div>
            <div><dt className="font-medium">Tiebreak seed</dt><dd className="mt-1 font-mi-mono text-mi-ink-2">{simulation.config.tiebreak_seed}</dd></div>
            <div><dt className="font-medium">Intervals</dt><dd className="mt-1 text-mi-ink-2">{simulation.interval}</dd></div>
            <div className="min-w-0"><dt className="font-medium">Benchmark</dt><dd className="mt-1 break-words font-mi-mono text-mi-ink-2">{simulation.benchmark}</dd></div>
            <div className="min-w-0 sm:col-span-2"><dt className="font-medium">Source SHA-256</dt><dd className="mt-1 break-all font-mi-mono text-mi-ink-2">{simulation.source_sha256}</dd></div>
          </dl>
          <button type="button" onClick={onImplementation} className={button}><Code2 size={16} aria-hidden /> Return to the Python source</button>
        </div>
      </details>

      <p className="flex items-start gap-3 px-1 text-base leading-relaxed text-mi-ink-2"><ArrowDown size={20} className="mt-1 shrink-0" aria-hidden />Now choose the inputs yourself. Build an electorate and compare its counts below.</p>
    </div>
  );
}

/** Mount once near the viewport; loading curated atlas data never starts a solve. */
function LazyAtlas({ onLoadPoint }: {
  onLoadPoint: (response: ProfileResolveResponse, point: AtlasPoint, view: AtlasView) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    if (active || !container.current || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setActive(true);
        observer.disconnect();
      }
    }, { rootMargin: "400px" });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, [active]);

  return <div ref={container} className="min-w-0 min-h-[20rem]">
    {active ? <Atlas onLoadPoint={onLoadPoint} /> : <div className="grid min-h-[20rem] place-items-center rounded-[3px] bg-mi-wash p-5 text-center">
      <div className="max-w-lg space-y-4"><p className="text-base leading-relaxed text-mi-ink-2">Explore the saved spatial maps for all seven methods.</p><button type="button" onClick={() => setActive(true)} className={button}>Load the spatial atlas</button></div>
    </div>}
  </div>;
}
