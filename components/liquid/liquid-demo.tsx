"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { resolveBallotPaperAction } from "@/actions/delegation-actions";
import { Slider } from "@/components/ui/slider";
import { cn } from "@/lib/utils";
import type {
  DelegationBallotPaper,
  DelegationScenario,
  QuestionResult,
  ResolveBallotPaperRequest,
  ResolveBallotPaperResponse,
} from "@/types/delegation";
import { DelegationEditor, type HeldDelegation } from "./delegation-editor";
import { buildDirectory, percent, personName, type Directory } from "./people";
import { QuestionPanel } from "./question-panel";

type Props = {
  scenario: DelegationScenario;
  /** The first ballot paper resolved with no delegations and no votes. */
  initial: ResolveBallotPaperResponse;
};

function requestFor(
  paper: DelegationBallotPaper,
  delegations: HeldDelegation[],
  votes: Record<string, string>,
  threshold: number
): ResolveBallotPaperRequest {
  const onPaper = new Set(paper.questions.map((question) => question.id));
  return {
    ballot_paper: paper.id,
    viewer_delegations: delegations.map(({ category, delegate }) => ({ category, delegate })),
    viewer_votes: Object.fromEntries(Object.entries(votes).filter(([id]) => onPaper.has(id))),
    threshold,
    tiebreak_seed: 0,
  };
}

/**
 * The interactive part of the liquid democracy page. The viewer's
 * delegations and votes live here, in the browser; every change is sent to
 * the Python service, which resolves the whole ballot paper again.
 */
export function LiquidDemo({ scenario, initial }: Props) {
  const directory = useMemo(() => buildDirectory(scenario), [scenario]);
  const [delegations, setDelegations] = useState<HeldDelegation[]>([]);
  const [votes, setVotes] = useState<Record<string, string>>({});
  const [threshold, setThreshold] = useState(scenario.threshold);
  const [sliderValue, setSliderValue] = useState(scenario.threshold);
  const [paperId, setPaperId] = useState(initial.ballot_paper);
  const [selected, setSelected] = useState<string | null>(null);

  const paper =
    scenario.ballot_papers.find((entry) => entry.id === paperId) ?? scenario.ballot_papers[0];
  const request = useMemo(
    () => requestFor(paper, delegations, votes, threshold),
    [paper, delegations, votes, threshold]
  );
  const requestKey = JSON.stringify(request);

  const [loaded, setLoaded] = useState(() => ({
    key: JSON.stringify(requestFor(paper, [], {}, scenario.threshold)),
    data: initial,
  }));
  const [error, setError] = useState<string | null>(null);
  const pending = loaded.key !== requestKey && error === null;

  useEffect(() => {
    if (loaded.key === requestKey) return;
    let stale = false;
    setError(null);
    void resolveBallotPaperAction(JSON.parse(requestKey)).then((result) => {
      if (stale) return;
      if (result.isSuccess && result.data) {
        setLoaded({ key: requestKey, data: result.data });
      } else {
        setError(result.message);
      }
    });
    return () => {
      stale = true;
    };
    // `loaded.key` is left out on purpose: a finished request must not start another.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  // Results on screen always belong to the paper being shown.
  const results = loaded.data.ballot_paper === paper.id ? loaded.data : null;
  const byQuestion = useMemo(
    () => new Map(results?.questions.map((entry) => [entry.question_id, entry]) ?? []),
    [results]
  );
  const question = paper.questions.find((entry) => entry.id === selected) ?? paper.questions[0];
  const result = byQuestion.get(question.id);

  return (
    <div className="space-y-14">
      <section id="delegations" className="scroll-mt-20 space-y-5">
        <SectionHeading number="01" title="Hand over categories of decisions">
          A category is whatever you write: “all things taxes”, or “the well-being of tree
          frogs in the Amazon”. Each one goes to one person. You are a District 1 resident
          in a simulated city of 240 others, and six of them have already handed a category
          to you.
        </SectionHeading>
        <DelegationEditor
          scenario={scenario}
          directory={directory}
          delegations={delegations}
          threshold={threshold}
          onAdd={(held) => setDelegations((current) => [...current, held])}
          onRemove={(index) =>
            setDelegations((current) => current.filter((_, position) => position !== index))
          }
        />
      </section>

      <section id="ballot" className="scroll-mt-20 space-y-5">
        <SectionHeading number="02" title="Run a ballot paper">
          A ballot paper is issued to the residents of one jurisdiction. For every voter and
          every question, a decision model scores each of that voter&apos;s categories, and code
          applies the rule: drop categories under the threshold, let a narrower category
          overrule a broader one, send the vote to the highest score left, and otherwise
          leave it with the voter. Each person along the way applies their own delegations.
        </SectionHeading>

        <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
          <div role="tablist" aria-label="Ballot paper" className="flex flex-wrap gap-2">
            {scenario.ballot_papers.map((entry) => (
              <button
                key={entry.id}
                type="button"
                role="tab"
                aria-selected={entry.id === paper.id}
                onClick={() => {
                  setPaperId(entry.id);
                  setSelected(null);
                }}
                className={cn(
                  "rounded-md border px-3 py-2 text-left text-sm transition-colors",
                  entry.id === paper.id
                    ? "border-indigo-600 bg-indigo-600/5 dark:border-indigo-400"
                    : "hover:bg-accent"
                )}
              >
                <span className="block font-medium">{entry.title}</span>
                <span className="block text-xs text-muted-foreground">
                  {directory.jurisdictions.get(entry.jurisdiction) ?? entry.jurisdiction} ·{" "}
                  {entry.eligible_voters} voters · {entry.questions.length} questions
                </span>
              </button>
            ))}
          </div>
          <div className="w-full max-w-xs space-y-2">
            <div className="flex justify-between text-sm">
              <label htmlFor="liquid-threshold">Threshold</label>
              <span className="tabular-nums text-muted-foreground">{sliderValue.toFixed(2)}</span>
            </div>
            <Slider
              id="liquid-threshold"
              min={0.5}
              max={0.95}
              step={0.05}
              value={[sliderValue]}
              onValueChange={([value]) => setSliderValue(value)}
              onValueCommit={([value]) => setThreshold(value)}
              aria-label="Routing threshold"
            />
          </div>
        </div>

        {results && !results.viewer_eligible && (
          <p className="rounded-md border p-3 text-sm text-muted-foreground">
            You live in District 1, so this ballot paper is not issued to you. You can still
            end up deciding: a District 2 resident&apos;s vote follows their delegations
            wherever they lead, including out of the district.
          </p>
        )}
        {results && results.unjudged_categories.length > 0 && (
          <p className="rounded-md border border-amber-500/50 bg-amber-500/5 p-3 text-sm">
            No recorded judgment for “{results.unjudged_categories.join("”, “")}”. The rule
            fails closed, so you keep those questions.
          </p>
        )}
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
            {error} What is shown may not match your latest change.
          </p>
        )}

        {results && <Summary results={results} viewer={directory.viewer} />}

        <div
          className={cn(
            "grid gap-6 transition-opacity lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]",
            pending && "opacity-60"
          )}
          aria-busy={pending}
        >
          <ol className="space-y-1.5 self-start">
            {paper.questions.map((entry, index) => {
              const row = byQuestion.get(entry.id);
              return (
                <li key={entry.id}>
                  <button
                    type="button"
                    aria-current={entry.id === question.id}
                    onClick={() => setSelected(entry.id)}
                    className={cn(
                      "w-full rounded-md border px-3 py-2 text-left text-sm transition-colors",
                      entry.id === question.id
                        ? "border-indigo-600 bg-indigo-600/5 dark:border-indigo-400"
                        : "hover:bg-accent"
                    )}
                  >
                    <span className="flex gap-2">
                      <span className="tabular-nums text-muted-foreground">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <span className="font-medium">{entry.title}</span>
                    </span>
                    {row && <RowStatus directory={directory} row={row} />}
                  </button>
                </li>
              );
            })}
          </ol>

          <div className="relative">
            {pending && (
              <Loader2
                className="absolute right-4 top-4 h-4 w-4 animate-spin text-muted-foreground"
                aria-label="Resolving"
              />
            )}
            {result ? (
              <QuestionPanel
                directory={directory}
                question={question}
                result={result}
                vote={votes[question.id]}
                onVote={(optionId) =>
                  setVotes((current) => {
                    const next = { ...current };
                    if (optionId === null) delete next[question.id];
                    else next[question.id] = optionId;
                    return next;
                  })
                }
              />
            ) : (
              <div className="rounded-lg border p-5 text-sm text-muted-foreground">
                {error ? "This ballot paper could not be resolved." : "Resolving the ballot paper…"}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function SectionHeading({
  number,
  title,
  children,
}: {
  number: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="max-w-3xl space-y-2">
      <h2 className="text-2xl font-semibold tracking-tight">
        <span className="mr-3 text-base font-medium tabular-nums text-indigo-700 dark:text-indigo-300">
          {number}
        </span>
        {title}
      </h2>
      <p className="leading-relaxed text-muted-foreground">{children}</p>
    </div>
  );
}

function RowStatus({ directory, row }: { directory: Directory; row: QuestionResult }) {
  const parts: string[] = [];
  if (row.receipt) {
    parts.push(
      row.receipt.resolver === directory.viewer
        ? "You decide"
        : `${personName(directory, row.receipt.resolver)} decides`
    );
  }
  if (row.inbox.votes_for_others > 0) {
    parts.push(`${parts.length ? "you" : "You"} answer for ${row.inbox.votes_for_others}`);
  }
  return (
    <span className="mt-0.5 flex flex-wrap gap-x-2 pl-7 text-xs text-muted-foreground">
      <span>{parts.join(" · ") || "Not issued to you"}</span>
      {row.winner_changed && (
        <span className="font-medium text-amber-700 dark:text-amber-400">result changes</span>
      )}
    </span>
  );
}

function Summary({
  results,
  viewer,
}: {
  results: ResolveBallotPaperResponse;
  viewer: string;
}) {
  const viewerEligible = results.viewer_eligible;
  const questions = results.questions;
  const sent = questions.filter(
    (entry) => entry.receipt && entry.receipt.resolver !== viewer
  ).length;
  const held = questions.reduce((sum, entry) => sum + entry.inbox.votes_for_others, 0);
  const changed = questions.filter((entry) => entry.winner_changed).length;
  const shares = questions.map((entry) => entry.metrics.delegated_share);
  const largest = Math.max(...questions.map((entry) => entry.metrics.largest_share));
  const stats = [
    {
      label: viewerEligible ? "of your votes sent to someone else" : "votes of your own on this paper",
      value: viewerEligible ? `${sent} of ${questions.length}` : "0",
    },
    { label: "votes you answer for, across all questions", value: String(held) },
    {
      label: "of all votes decided by someone else, by question",
      value: `${percent(Math.min(...shares))}–${percent(Math.max(...shares))}`,
    },
    { label: "largest share one person holds on any question", value: percent(largest, 1) },
    { label: "questions where delegation changes the result", value: `${changed} of ${questions.length}` },
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {stats.map((stat) => (
        <div key={stat.label} className="rounded-md border bg-card p-3">
          <dd className="text-xl font-semibold tabular-nums">{stat.value}</dd>
          <dt className="text-xs leading-snug text-muted-foreground">{stat.label}</dt>
        </div>
      ))}
    </dl>
  );
}
