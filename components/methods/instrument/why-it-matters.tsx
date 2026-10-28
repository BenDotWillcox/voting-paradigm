"use client";

import { ArrowDown, ArrowRight, ExternalLink } from "lucide-react";
import { useRef, useState } from "react";

import type { IRVSource } from "@/lib/methods/irv-inspector";
import type { StepId } from "@/lib/methods/sections";
import { storyCopy, type Story, type StoryStep } from "@/lib/methods/stories";
import { BALLOT_RULES, WALK_PRESET, type BallotKind } from "@/lib/methods/walkthrough";
import { cn } from "@/lib/utils";
import type { Specimen, SpecimenRole, SpecimenSearch, VotingMethod } from "@/types/methods";

import type { PresetOption } from "./methods-instrument";
import { OpeningComparison, ParticipationExperiment } from "./opening";
import { ParadoxGallery } from "./paradox-gallery";
import { BallotView, FairnessView, HeadToHeadView, StoryView, VotersView } from "./walkthrough";

const SEP = "https://plato.stanford.edu/entries/social-choice/";
const button = "inline-flex min-h-11 items-center justify-center gap-2 rounded-[3px] border border-mi-rule px-3 py-2 text-left text-sm font-medium text-mi-ink hover:bg-mi-wash focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink";
const scenarioLabels: Record<StoryStep, string> = {
  "paradox-no-show": "Turnout backfires",
  "paradox-spoiler": "A similar candidate joins",
  "paradox-monotonicity": "More support, worse result",
};
const scenarioOrder: StoryStep[] = ["paradox-no-show", "paradox-spoiler", "paradox-monotonicity"];
const ballotKinds: BallotKind[] = ["single", "ranked", "approval", "score", "quadratic"];

/** Why the implementation choices matter, using saved package results throughout. */
export function WhyItMatters({ presets, stories, irvSource, searches, onMethod, onSpecimen, initialExample = "paradox-no-show", initialReference }: {
  presets: PresetOption[];
  stories: Story[];
  irvSource: IRVSource;
  searches: SpecimenSearch[];
  onMethod: (method: VotingMethod) => void;
  onSpecimen: (specimen: Specimen, role?: SpecimenRole) => void;
  initialExample?: StoryStep;
  initialReference?: StepId;
}) {
  const reference = presets.find((preset) => preset.id === WALK_PRESET) ?? presets[0];
  const [selectedStory, setSelectedStory] = useState<StoryStep>(initialExample);
  const [ballotKind, setBallotKind] = useState<BallotKind>(() => ballotKinds.find((kind) => initialReference === `ballot-${kind}`) ?? "ranked");
  const galleryDetails = useRef<HTMLDetailsElement>(null);
  const scenarios = scenarioOrder.flatMap((step) => stories.filter((story) => story.step === step));
  const activeStory = scenarios.find((story) => story.step === selectedStory) ?? scenarios[0];
  if (!reference) return null;

  function openGallery() {
    if (!galleryDetails.current) return;
    galleryDetails.current.open = true;
    galleryDetails.current.scrollIntoView({ block: "start" });
    galleryDetails.current.querySelector("summary")?.focus({ preventScroll: true });
  }

  return (
    <div className="min-w-0 space-y-12 [&_.text-xs]:text-sm [&_summary]:min-h-11">
      <section id="comparison" className="min-w-0 scroll-mt-28 space-y-5" aria-labelledby="comparison-title">
        <div className="max-w-3xl space-y-3">
          <p className="text-sm font-medium text-mi-ink-2">Same preferences. Different decisions.</p>
          <h3 id="comparison-title" className="text-2xl font-semibold leading-tight tracking-[-0.02em] text-mi-ink sm:text-3xl">{reference.resolution.total_voters} voters. Three different winners.</h3>
          <p className="text-base leading-relaxed text-mi-ink-2">The code above decides which information counts. Here, no voter changes their mind: the method alone changes who wins.</p>
        </div>
        <OpeningComparison profile={reference.profile} resolution={reference.resolution} onMethod={onMethod} showPackageIntro={false} />
      </section>

      <section id="fairness" className="min-w-0 scroll-mt-28 space-y-5" aria-labelledby="criteria-title">
        <div className="max-w-3xl space-y-2">
          <p className="text-sm font-medium text-mi-ink-2">What should a voting rule protect?</p>
          <h3 id="criteria-title" className="text-xl font-semibold leading-snug text-mi-ink sm:text-2xl">Make the trade-offs explicit.</h3>
          <p className="text-base leading-relaxed text-mi-ink-2">A different winner is the observation. Criteria let us ask whether the change violates a property we wanted the rule to preserve.</p>
        </div>
        <div className="grid min-w-0 gap-4 md:grid-cols-3">
          {[
            { title: "Respect majority preferences", text: "Does a first-choice majority win? What about a candidate who beats every rival head to head?", example: "The comparison above separates those tests." },
            { title: "Reward support", text: "Can moving a winner higher make it lose? Can turning out leave new voters with an outcome they prefer less?", example: "Try the two instant-runoff examples below." },
            { title: "Resist changes to the field", text: "Can a losing candidate’s withdrawal change the winner? What happens when a similar candidate enters?", example: "The plurality example isolates a split in support." },
          ].map((item) => <article key={item.title} className="min-w-0 space-y-3 rounded-[4px] border border-mi-rule bg-mi-surface p-4 sm:p-5"><h4 className="text-base font-semibold text-mi-ink">{item.title}</h4><p className="text-base leading-relaxed text-mi-ink-2">{item.text}</p><p className="border-t border-mi-rule pt-3 text-sm leading-relaxed text-mi-ink-2">{item.example}</p></article>)}
        </div>
        <details className="rounded-[4px] border border-mi-rule p-4 sm:p-5">
          <summary className="cursor-pointer text-base font-medium text-mi-ink focus-visible:outline-2 focus-visible:outline-mi-ink">Read the eight criteria used in this demo</summary>
          <div className="mt-4 min-w-0 space-y-4">
            <FairnessView />
            <p className="max-w-3xl text-sm leading-relaxed text-mi-ink-2">The gallery’s “IIA” is a losing-candidate-removal test. Arrow’s IIA instead concerns pairwise social rankings across profiles with fixed alternatives. <a href={SEP} className="underline underline-offset-4">SEP §3.2</a></p>
          </div>
        </details>
      </section>

      <section id="examples" className="min-w-0 scroll-mt-28 space-y-5" aria-labelledby="examples-title">
        <span id="experiment" className="block scroll-mt-28" />
        <div className="max-w-3xl space-y-2">
          <p className="text-sm font-medium text-mi-ink-2">Change one thing.</p>
          <h3 id="examples-title" className="text-xl font-semibold leading-snug text-mi-ink sm:text-2xl">Small examples expose surprising behavior.</h3>
          <p className="text-base leading-relaxed text-mi-ink-2">Each example changes one part of an electorate and reuses the same counting rule. Both outcomes are saved Python results.</p>
        </div>
        <div className="grid min-w-0 gap-2 rounded-[4px] bg-mi-wash p-1.5 sm:grid-cols-3" role="group" aria-label="Voting theory examples">
          {scenarios.map(({ step }) => <button key={step} type="button" aria-pressed={activeStory?.step === step} aria-controls={`example-${step}`} onClick={() => setSelectedStory(step)} className={cn(button, "justify-start border-transparent", activeStory?.step === step && "border-mi-ink bg-mi-surface shadow-sm")}>{scenarioLabels[step]}</button>)}
        </div>
        <div className="grid min-w-0">
          {/* Every scenario sizes the same grid cell, including when hidden. */}
          {scenarios.map((scenario) => {
            const copy = storyCopy(scenario);
            const active = activeStory?.step === scenario.step;
            return <div
              key={scenario.step}
              id={`example-${scenario.step}`}
              role="region"
              aria-labelledby={`example-${scenario.step}-title`}
              aria-hidden={!active}
              ref={(element) => { if (element) element.inert = !active; }}
              className={cn("col-start-1 row-start-1 flex min-w-0 flex-col justify-center space-y-5 rounded-[4px] border border-mi-rule bg-mi-surface p-4 sm:p-6", !active && "invisible pointer-events-none")}
            >
              <div className="max-w-3xl space-y-2">
                <p className="text-sm font-medium text-mi-ink-2">{copy.transition}</p>
                <h4 id={`example-${scenario.step}-title`} className="text-xl font-semibold leading-snug text-mi-ink">{scenario.step === "paradox-no-show" ? "What happens when two more voters turn out?" : copy.title}</h4>
                {scenario.step !== "paradox-no-show" && <p className="text-base leading-relaxed text-mi-ink-2">{copy.takeaway}</p>}
              </div>
              {scenario.step === "paradox-no-show" ? <ParticipationExperiment story={scenario} source={irvSource} onExplore={(role) => onSpecimen(scenario.specimen, role)} showInspector={false} /> : <>
                <StoryView story={scenario} onGallery={openGallery} />
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => onSpecimen(scenario.specimen, "before")} className={button}>Edit the before electorate <ArrowRight size={15} aria-hidden /></button>
                  <button type="button" onClick={() => onSpecimen(scenario.specimen, "after")} className={button}>Edit the after electorate <ArrowRight size={15} aria-hidden /></button>
                </div>
              </>}
            </div>;
          })}
        </div>
      </section>

      <section className="min-w-0 space-y-5 border-t border-mi-rule pt-8" aria-labelledby="literature-title">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h3 id="literature-title" className="text-xl font-semibold text-mi-ink sm:text-2xl">Where the theory fits</h3>
          <a href={SEP} className={button}>Social Choice Theory · Stanford <ExternalLink size={15} aria-hidden /></a>
        </div>
        <div className="grid min-w-0 gap-5 md:grid-cols-3">
          <article className="space-y-2"><h4 className="text-base font-semibold text-mi-ink">Majorities can cycle</h4><p className="text-base leading-relaxed text-mi-ink-2">Consistent individual rankings can produce a majority cycle. Here, a Condorcet winner must strictly beat every rival; some literature includes pairwise ties. <a href={SEP} className="underline underline-offset-4">§1.1</a></p></article>
          <article className="space-y-2"><h4 className="text-base font-semibold text-mi-ink">Arrow concerns collective rankings</h4><p className="text-base leading-relaxed text-mi-ink-2">With at least three alternatives, unrestricted rankings, a complete and transitive collective ranking, unanimity, independence, and non-dictatorship cannot all hold. The result does not make all rules equivalent. <a href={SEP} className="underline underline-offset-4">§3.2</a></p></article>
          <article className="space-y-2"><h4 className="text-base font-semibold text-mi-ink">Strategy has a separate theorem</h4><p className="text-base leading-relaxed text-mi-ink-2">Gibbard–Satterthwaite concerns deterministic single-winner rules with unrestricted strict rankings and at least three possible winners: strategy-proofness forces dictatorship. It does not predict how often voters manipulate. <a href={SEP} className="underline underline-offset-4">§3.5</a></p></article>
        </div>
        <p className="max-w-3xl text-sm leading-relaxed text-mi-ink-2">Ratings and approval ballots change the information collected; scale and comparability assumptions still matter. <a href={SEP} className="underline underline-offset-4">§§4.2–4.5</a></p>
      </section>

      <div className="min-w-0 space-y-4">
        <details id="ballots" className="min-w-0 scroll-mt-28 rounded-[4px] border border-mi-rule p-4 sm:p-5">
          <summary className="cursor-pointer text-base font-medium text-mi-ink focus-visible:outline-2 focus-visible:outline-mi-ink">Explore the ballot formats and preference model</summary>
          <div className="mt-4 min-w-0 space-y-5">
            <p className="max-w-3xl text-base leading-relaxed text-mi-ink-2">These are modeled sincere ballots from the same preference scales. Approval thresholds, score normalization, and quadratic allocations follow <code className="font-mi-mono">sincere-v1</code>; they are assumptions about how voters cast ballots, separate from the methods that count them.</p>
            <div role="group" aria-label="Ballot formats" className="grid grid-cols-2 gap-2 sm:grid-cols-5">{ballotKinds.map((kind) => <button key={kind} type="button" aria-pressed={ballotKind === kind} onClick={() => setBallotKind(kind)} className={cn(button, ballotKind === kind && "border-mi-ink bg-mi-wash")}>{BALLOT_RULES[kind].name}</button>)}</div>
            <BallotView kind={ballotKind} profile={reference.profile} resolution={reference.resolution} />
            <details id="voters" className="scroll-mt-28 border-t border-mi-rule pt-4"><summary className="cursor-pointer text-base font-medium text-mi-ink">See the underlying preference scales</summary><div className="mt-4"><VotersView profile={reference.profile} /></div></details>
            <details id="head-to-head" className="scroll-mt-28 border-t border-mi-rule pt-4"><summary className="cursor-pointer text-base font-medium text-mi-ink">Compare the head-to-head races</summary><div className="mt-4"><HeadToHeadView resolution={reference.resolution} /></div></details>
          </div>
        </details>

        <details ref={galleryDetails} id="gallery" className="min-w-0 scroll-mt-28 rounded-[4px] border border-mi-rule p-4 sm:p-5">
          <summary className="cursor-pointer text-base font-medium text-mi-ink focus-visible:outline-2 focus-visible:outline-mi-ink">Compare all methods against the criteria</summary>
          <div className="mt-4 min-w-0 space-y-4">
            <p className="max-w-3xl text-base leading-relaxed text-mi-ink-2">Open a numbered failure to edit its electorate in the playground. Proofs, cited failures, and searches with no settled result remain distinct.</p>
            <p className="max-w-3xl text-sm leading-relaxed text-mi-ink-2">“IIA” below tests removal of a losing candidate. Rated-method results use the stated ballot model; they do not establish behavior for every possible way of converting preferences into ballots.</p>
            <div className="min-w-0 [&_th]:text-sm [&_button]:min-h-11 [&_button]:min-w-11"><ParadoxGallery searches={searches} onOpen={onSpecimen} /></div>
          </div>
        </details>
      </div>

      <p className="flex items-center gap-2 border-t border-mi-rule pt-6 text-base text-mi-ink-2"><ArrowDown size={18} className="shrink-0" aria-hidden /> A counterexample shows what can happen. The simulations below ask how often it happens under one model.</p>
    </div>
  );
}
