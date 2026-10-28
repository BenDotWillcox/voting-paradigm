"use client";

import { ArrowRight, Code2, RotateCcw } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { candidateColor } from "@/lib/methods/candidates";
import { METHOD_META } from "@/lib/methods/instrument";
import type { IRVSource } from "@/lib/methods/irv-inspector";
import { rankingOf } from "@/lib/methods/profile";
import type { Story } from "@/lib/methods/stories";
import { cn } from "@/lib/utils";
import type {
  ProfileMethodResult,
  ProfileResolveResponse,
  RankedRow,
  SpecimenRole,
  UtilityProfile,
  VotingMethod,
} from "@/types/methods";

import { CandidateMark } from "./glyph";
import { IRVInspector } from "./irv-inspector";
import { CompactCounts } from "./walkthrough";

const OPENING_METHODS: VotingMethod[] = ["plurality", "irv", "ranked_pairs"];

/** The opening compares stored Python counts; it does not tally ballots in the browser. */
export function OpeningComparison({
  profile,
  resolution,
  onMethod,
  showPackageIntro = true,
}: {
  profile: UtilityProfile;
  resolution: ProfileResolveResponse;
  onMethod: (method: VotingMethod) => void;
  showPackageIntro?: boolean;
}) {
  const irv = resolution.results.find((item) => item.method === "irv");
  const apiExcerpt = `from voting import resolve_irv\n\nresult = resolve_irv(candidates, ranked_ballots)\nresult.winners  # ${JSON.stringify(irv ? [irv.winner] : [])}`;
  return (
    <div className="space-y-6">
      <section aria-label="The voters" className="rounded-[4px] bg-mi-wash p-4 sm:p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-base font-medium text-mi-ink">{resolution.total_voters} voters. These preferences stay fixed.</h3>
          <span className="text-sm text-mi-ink-2">Favorite → least favorite</span>
        </div>
        <ul className="mt-4 grid gap-3 sm:grid-cols-3">
          {profile.rows.map((row, index) => (
            <li key={index} className="space-y-1.5">
              <p className="text-sm text-mi-ink-2">{row.count} voters</p>
              <Ranking ranking={rankingOf(profile.candidates, row)} />
            </li>
          ))}
        </ul>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        {OPENING_METHODS.map((method) => {
          const result = resolution.results.find((item) => item.method === method);
          if (!result) return null;
          return (
            <section
              key={method}
              className="flex flex-col rounded-[4px] border border-mi-rule border-t-[3px] p-5"
              style={{ borderTopColor: candidateColor(result.winner) }}
              aria-label={`${METHOD_META[method].label} elects ${result.winner}`}
            >
              <h3 className="text-base font-medium text-mi-ink">{METHOD_META[method].label}</h3>
              <p className="mt-4 flex items-center gap-3">
                <CandidateMark id={result.winner} size={36} className="gap-2 text-4xl font-semibold text-mi-ink" />
                <span className="text-sm text-mi-ink-2">wins</span>
              </p>
              <p className="mt-4 flex-1 text-base leading-relaxed text-mi-ink-2">
                {decisiveReason(result, resolution)}
              </p>
              <button
                type="button"
                onClick={() => onMethod(method)}
                aria-label={`Trace ${METHOD_META[method].label} in Python`}
                className="mt-5 inline-flex min-h-11 items-center gap-2 self-start rounded-[3px] border border-mi-rule px-3 py-2 text-sm font-medium text-mi-ink hover:bg-mi-wash focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-mi-ink"
              >
                <Code2 size={16} aria-hidden /> Trace Python <ArrowRight size={15} aria-hidden />
              </button>
            </section>
          );
        })}
      </div>

      {showPackageIntro && <section className="grid min-w-0 gap-4 rounded-[4px] border border-mi-rule p-4 sm:p-5 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]" aria-label="The Python package">
        <div className="space-y-2">
          <h3 className="text-base font-semibold text-mi-ink">A Python package behind every result</h3>
          <p className="text-sm leading-relaxed text-mi-ink-2">
            Construct the ballots, call a resolution method, inspect its result.
            These saved counts come from the same package you can run yourself.
          </p>
          <p className="text-sm leading-relaxed text-mi-ink-2">Trace a method to inspect its actual source and copy a runnable example.</p>
        </div>
        <div className="min-w-0">
          <p className="mb-2 text-sm text-mi-ink-2">Public API excerpt · candidates and ranked ballots prepared</p>
          <div role="region" aria-label="Public Python API example" tabIndex={0} onKeyDown={(event) => {
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") event.stopPropagation();
          }} className="min-w-0 overflow-x-auto rounded-[3px] bg-mi-wash p-3 focus-visible:outline-2 focus-visible:outline-mi-ink">
            <pre className="w-max min-w-full font-mi-mono text-sm leading-6 text-mi-ink"><code>{apiExcerpt}</code></pre>
          </div>
        </div>
      </section>}

      <p className="max-w-2xl text-base leading-relaxed text-mi-ink-2">
        Plurality reads each voter&apos;s first choice. Instant runoff and Ranked Pairs read the whole ranking.
        The counting rule changes what wins.
      </p>

      <details className="rounded-[4px] border border-mi-rule p-4">
        <summary className="cursor-pointer text-base font-medium text-mi-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-mi-ink">
          Compare all seven methods
        </summary>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-mi-ink-2">
          Approval, score and quadratic ballots also use the groups&apos; preference strengths.
          Their results depend on the demo&apos;s rules for turning those strengths into ballots.
        </p>
        <div className="mt-4 overflow-x-auto [&_table]:min-w-[36rem] [&_.text-xs]:text-sm">
          <CompactCounts resolution={resolution} onOpen={onMethod} />
        </div>
      </details>
    </div>
  );
}

function decisiveReason(result: ProfileMethodResult, resolution: ProfileResolveResponse): string {
  const { trace, winner } = result;
  if (trace.kind === "plurality") {
    const last = resolution.rankings.rows.reduce(
      (sum, row) => sum + (row.ranking[row.ranking.length - 1] === winner ? row.count : 0),
      0
    );
    return `${winner} has the most first choices: ${trace.first_choices[winner]} of ${resolution.total_voters}. ${last} voters rank ${winner} last.`;
  }
  if (trace.kind === "irv") {
    const eliminated = trace.rounds[0]?.eliminated.join(" and ");
    const final = trace.rounds[trace.rounds.length - 1];
    return `${eliminated ? `${eliminated} goes out first. ` : ""}${winner} finishes with ${final?.counts[winner] ?? 0} of ${resolution.total_voters} votes after transfers.`;
  }
  if (trace.kind === "ranked_pairs" && trace.had_condorcet_winner) {
    return `A majority prefers ${winner} to each rival in a head-to-head race. Ranked Pairs preserves those wins.`;
  }
  return METHOD_META[result.method].rule + ".";
}

/** One intervention, with both outcomes taken from the saved reference counts. */
export function ParticipationExperiment({
  story,
  source,
  onExplore,
  showInspector = true,
}: {
  story: Story;
  source: IRVSource;
  onExplore: (role: SpecimenRole) => void;
  showInspector?: boolean;
}) {
  const [added, setAdded] = useState(false);
  const outcomeId = useId();
  const addButton = useRef<HTMLButtonElement>(null);
  const resetButton = useRef<HTMLButtonElement>(null);
  const focusAfterToggle = useRef<"add" | "reset" | null>(null);
  useEffect(() => {
    const target = focusAfterToggle.current;
    if (!target) return;
    focusAfterToggle.current = null;
    (target === "add" ? addButton : resetButton).current?.focus({ preventScroll: true });
  }, [added]);
  const change = story.specimen.transformation;
  const before = story.before.results.find((result) => result.method === "irv");
  const after = story.after.results.find((result) => result.method === "irv");
  if (change?.kind !== "add_voters" || before?.trace.kind !== "irv" || after?.trace.kind !== "irv") return null;

  const eliminatedBefore = before.trace.rounds[0]?.eliminated.join(" and ");
  const eliminatedAfter = after.trace.rounds[0]?.eliminated.join(" and ");
  const worst = change.ranking[change.ranking.length - 1];
  const resultDescription = after.winner === worst
    ? `Their last choice, ${after.winner}, now wins.`
    : `${after.winner} now wins instead of ${before.winner}.`;
  const explanation = `Before, ${eliminatedBefore} was eliminated first and its ballots carried ${before.winner} to victory. The new votes keep ${eliminatedBefore} in the race: ${eliminatedAfter} is eliminated instead, and its ballots elect ${after.winner}.`;
  const introduction = <p className="max-w-3xl text-base leading-relaxed text-mi-ink-2">
    Start a different, smaller election: {story.before.total_voters} voters, counted by instant runoff.
    Another {change.voters} voters are ready to join. They prefer {change.ranking.join(" to ")}.
  </p>;
  const provenance = <p className="text-sm leading-relaxed text-mi-ink-2">
    A reproducible example found by the package&apos;s counterexample search.
    Both counts are saved outputs of the Python voting methods; open either electorate to inspect or edit it.
  </p>;
  function toggleVoters(revealed: boolean) {
    if (!showInspector) focusAfterToggle.current = revealed ? "reset" : "add";
    setAdded(revealed);
  }
  const controls = (revealed: boolean) => <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          ref={revealed ? undefined : addButton}
          onClick={() => toggleVoters(true)}
          disabled={revealed}
          aria-controls={outcomeId}
          className="inline-flex min-h-11 items-center gap-2 rounded-[4px] border border-mi-ink bg-mi-ink px-4 py-2.5 text-base font-medium text-mi-surface hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-mi-ink disabled:cursor-default disabled:opacity-60"
        >
          {revealed ? `${change.voters} voters added` : `Add ${change.voters} voters`}
          <ArrowRight size={18} aria-hidden />
        </button>
        {revealed ? (
          <button
            type="button"
            ref={resetButton}
            onClick={() => toggleVoters(false)}
            className="inline-flex min-h-11 items-center gap-2 rounded-[4px] border border-mi-rule px-4 py-2.5 text-base text-mi-ink hover:border-mi-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-mi-ink"
          >
            <RotateCcw size={16} aria-hidden /> Reset
          </button>
        ) : (
          <span className="text-sm text-mi-ink-2">The existing voters keep their ballots.</span>
        )}
      </div>;
  const beforeCounts = <div className="grid gap-4 md:grid-cols-2">
        <ExperimentCount
          label="Before"
          resolution={story.before}
          result={before}
          onExplore={() => onExplore("before")}
        />
        <div>
            <div className="flex h-full flex-col justify-center rounded-[4px] border border-dashed border-mi-rule bg-mi-wash p-5 sm:p-6 md:min-h-64">
              <p className="text-sm font-medium text-mi-ink-2">The new voters</p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <span className="font-mi-mono text-2xl text-mi-ink">+{change.voters}</span>
                <Ranking ranking={change.ranking} />
              </div>
              <p className="mt-4 max-w-sm text-base leading-relaxed text-mi-ink-2">
                They rank {before.winner} above {worst}. Add their ballots to see whether voting helps them.
              </p>
            </div>
        </div>
      </div>;
  const outcome = <section className="rounded-[4px] border-l-[3px] border-mi-ink bg-mi-wash p-4 sm:p-5" aria-label="Why the result changed">
          <h3 className="text-lg font-semibold text-mi-ink">{resultDescription}</h3>
          <p className="mt-2 max-w-3xl text-base leading-relaxed text-mi-ink-2">{explanation}</p>
        </section>;
  const comparison = <div className="grid gap-4 md:grid-cols-2">
        <ExperimentCount label="Before" resolution={story.before} result={before} onExplore={() => onExplore("before")} />
        <ExperimentCount label="After" resolution={story.after} result={after} changedRanking={change.ranking} added={change.voters} onExplore={() => onExplore("after")} />
      </div>;

  if (!showInspector) return <div className="space-y-5">
    {introduction}
    <div className="grid min-w-0">
      {/* From md, both states reserve their full height, including controls, so nothing
          moves. Stacked on a phone the after state is far taller, so only the shown one counts. */}
      <div aria-hidden={added} ref={(element) => { if (element) element.inert = added; }} className={cn("col-start-1 row-start-1 flex min-w-0 flex-col space-y-5", added && "invisible pointer-events-none max-md:hidden")}>
        {controls(false)}
        <div className="flex flex-1 flex-col md:justify-center">{beforeCounts}</div>
      </div>
      <div id={outcomeId} aria-hidden={!added} ref={(element) => { if (element) element.inert = !added; }} className={cn("col-start-1 row-start-1 flex min-w-0 flex-col space-y-5", !added && "invisible pointer-events-none max-md:hidden")}>
        {controls(true)}
        <div className="flex flex-1 flex-col space-y-5 md:justify-center">
          {outcome}
          {comparison}
        </div>
      </div>
    </div>
    <p className="sr-only" aria-live="polite" aria-atomic="true">{added ? `${resultDescription} ${explanation}` : ""}</p>
    {provenance}
  </div>;

  return (
    <div className="space-y-5">
      {introduction}
      {controls(added)}
      {!added ? beforeCounts : null}
      <div id={outcomeId} aria-live="polite" aria-atomic="true">{added ? outcome : null}</div>
      {added ? <IRVInspector story={story} source={source} /> : null}

      {added ? <details className="rounded-[4px] border border-mi-rule p-4 sm:p-5">
        <summary className="min-h-11 cursor-pointer text-base font-medium text-mi-ink focus-visible:outline-2 focus-visible:outline-mi-ink">Inspect the ballots and the participation failure</summary>
        <p className="mb-4 max-w-3xl text-sm leading-relaxed text-mi-ink-2">
          These voters get an outcome they like less by turning out: a failure of participation.
          The rule and every existing ballot stayed the same. Open either electorate to edit it.
        </p>
        {comparison}
      </details> : null}
      {provenance}
    </div>
  );
}

function ExperimentCount({
  label,
  resolution,
  result,
  changedRanking,
  added,
  onExplore,
}: {
  label: string;
  resolution: ProfileResolveResponse;
  result: ProfileMethodResult;
  changedRanking?: string[];
  added?: number;
  onExplore: () => void;
}) {
  if (result.trace.kind !== "irv") return null;
  const first = result.trace.rounds[0];
  const final = result.trace.rounds[result.trace.rounds.length - 1];
  return (
    <section className="h-full rounded-[4px] border border-mi-rule p-5 sm:p-6" aria-label={`${label}: ${resolution.total_voters} voters, ${result.winner} wins`}>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <h3 className="font-medium text-mi-ink">{label}</h3>
        <span className="font-mi-mono text-mi-ink-2">{resolution.total_voters} voters</span>
      </div>
      <ul className="mt-4 space-y-2">
        {resolution.rankings.rows.map((row) => (
          <RankingRow
            key={row.ranking.join("|")}
            row={row}
            added={changedRanking?.join("|") === row.ranking.join("|") ? added : undefined}
          />
        ))}
      </ul>
      <div className="mt-5 border-t border-mi-rule pt-4">
        <p className="text-sm text-mi-ink-2">
          First round: {Object.entries(first?.counts ?? {}).map(([candidate, count]) => `${candidate} ${count}`).join(" · ")}
        </p>
        <p className="mt-1 text-sm text-mi-ink-2">{first?.eliminated.join(" and ")} is eliminated.</p>
        <p className="mt-4 flex flex-wrap items-center gap-3 text-base text-mi-ink">
          <CandidateMark id={result.winner} size={28} className="gap-2 text-3xl font-semibold" />
          <span>wins with <strong>{final?.counts[result.winner]} of {resolution.total_voters}</strong> votes</span>
        </p>
      </div>
      <button
        type="button"
        onClick={onExplore}
        className="mt-5 inline-flex min-h-11 items-center text-sm text-mi-ink underline decoration-mi-rule underline-offset-4 hover:decoration-mi-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-mi-ink"
      >
        Inspect this electorate <span aria-hidden>→</span>
      </button>
    </section>
  );
}

function RankingRow({ row, added }: { row: RankedRow; added?: number }) {
  return (
    <li className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[3px] px-2 py-1.5", added && "bg-mi-wash ring-1 ring-mi-rule")}>
      <span className="min-w-8 font-mi-mono text-base text-mi-ink">{row.count} ×</span>
      <Ranking ranking={row.ranking} />
      {added ? <span className="ml-auto text-sm font-medium text-mi-ink">+{added} new</span> : null}
    </li>
  );
}

function Ranking({ ranking }: { ranking: string[] }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-2 text-base text-mi-ink" role="img" aria-label={ranking.join(" preferred to ")}>
      {ranking.map((candidate, index) => (
        <span key={candidate} className="inline-flex items-center gap-2" aria-hidden>
          {index > 0 ? <span className="text-mi-ink-2">›</span> : null}
          <CandidateMark id={candidate} size={16} />
        </span>
      ))}
    </span>
  );
}
