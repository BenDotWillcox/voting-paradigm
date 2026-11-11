"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type {
  DelegationQuestion,
  QuestionResult,
  QuestionTally,
  VoteReceipt,
} from "@/types/delegation";
import { Chain } from "./delegation-editor";
import { percent, personHome, personName, type Directory } from "./people";

type Props = {
  directory: Directory;
  question: DelegationQuestion;
  result: QuestionResult;
  vote: string | undefined;
  onVote: (optionId: string | null) => void;
};

/** One question: the viewer's receipt, the votes they hold, and the outcome. */
export function QuestionPanel({ directory, question, result, vote, onVote }: Props) {
  const optionName = (id: string | null) =>
    id === null ? "Abstain" : (question.options.find((option) => option.id === id)?.name ?? id);
  const { receipt, inbox } = result;
  const decides = receipt ? receipt.resolver === directory.viewer : inbox.votes_for_others > 0;

  return (
    <article className="space-y-6 rounded-lg border bg-card p-5">
      <header className="space-y-1.5">
        <h3 className="text-lg font-semibold tracking-tight">{question.title}</h3>
        <p className="text-sm leading-relaxed text-muted-foreground">{question.summary}</p>
      </header>

      <section className="space-y-3">
        <h4 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          Your receipt
        </h4>
        {receipt ? (
          <Receipt directory={directory} receipt={receipt} optionName={optionName} />
        ) : (
          <p className="text-sm text-muted-foreground">
            You are not issued this ballot paper, so you have no vote of your own here.
          </p>
        )}
      </section>

      <section className="space-y-3">
        <h4 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          Your inbox
        </h4>
        {inbox.votes_for_others === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nobody else&apos;s vote ends with you on this question.
          </p>
        ) : (
          <div className="space-y-1.5 text-sm">
            <p>
              You answer for {inbox.votes_for_others} other{" "}
              {inbox.votes_for_others === 1 ? "person" : "people"}.{" "}
              {inbox.answered
                ? "Each of their ballots is a copy of yours."
                : "Until you vote, each of their ballots is an abstention."}
            </p>
            <p className="text-muted-foreground">
              {inbox.held.map((held) => personName(directory, held.voter)).join(", ")}
            </p>
          </div>
        )}
        {(receipt || decides) && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-sm text-muted-foreground">
              {decides ? "Your vote:" : "Vote yourself instead:"}
            </span>
            {question.options.map((option) => (
              <Button
                key={option.id}
                type="button"
                size="sm"
                variant={vote === option.id ? "default" : "outline"}
                aria-pressed={vote === option.id}
                onClick={() => onVote(vote === option.id ? null : option.id)}
              >
                {option.name}
              </Button>
            ))}
            {vote && (
              <Button type="button" size="sm" variant="ghost" onClick={() => onVote(null)}>
                Clear
              </Button>
            )}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h4 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          Outcome
        </h4>
        <div className="space-y-3">
          <TallyBar label="With delegation" tally={result.delegated} question={question} />
          <TallyBar label="Everyone votes directly" tally={result.direct} question={question} />
        </div>
        <p className="text-sm">
          {result.winner_changed ? (
            <span className="font-medium text-amber-700 dark:text-amber-400">
              Delegation changes the result:{" "}
              {result.direct.winners.map(optionName).join(" / ")} directly,{" "}
              {result.delegated.winners.map(optionName).join(" / ")} with delegation.
            </span>
          ) : (
            <span className="text-muted-foreground">
              Same result either way: {result.delegated.winners.map(optionName).join(" / ")}.
            </span>
          )}
          {(result.delegated.tiebreak_applied || result.direct.tiebreak_applied) && (
            <span className="text-muted-foreground"> A tie was settled by the seeded tiebreak.</span>
          )}
        </p>
        <Concentration directory={directory} result={result} />
      </section>
    </article>
  );
}

function Receipt({
  directory,
  receipt,
  optionName,
}: {
  directory: Directory;
  receipt: VoteReceipt;
  optionName: (id: string | null) => string;
}) {
  const viewerResolves = receipt.resolver === directory.viewer;
  const setAside = new Set(receipt.set_aside);

  let headline: string;
  if (receipt.outcome === "delegated") {
    headline = viewerResolves
      ? `Sent under “${receipt.category}”, and the chain came back to you. You keep this decision.`
      : `Sent under “${receipt.category}”. ${personName(directory, receipt.resolver)} decides.`;
  } else if (receipt.outcome === "direct_vote") {
    headline = "You voted yourself, which overrides your delegations.";
  } else if (receipt.outcome === "no_delegations") {
    headline = "You have handed nothing over, so you keep this decision.";
  } else if (receipt.outcome === "none_available") {
    headline = "None of your categories covers this question, so you keep this decision.";
  } else {
    headline = "One of your categories has no judgment for this question, so you keep this decision.";
  }

  const holds: Record<VoteReceipt["kept_because"], string> = {
    direct_vote: "voted on it themself",
    no_delegations: "has handed nothing over",
    none_available: "has no category that covers this question",
    router_unavailable: "has a category with no judgment for this question",
    loop: "is on a loop, where everyone keeps their own decision",
  };

  return (
    <div className="space-y-4 text-sm">
      <p className="font-medium">{headline}</p>

      {receipt.scores.length > 0 && (
        <div className="space-y-2">
          <p className="text-muted-foreground">
            Is this question about the category? The model&apos;s yes-probability for each of
            yours, against the {percent(receipt.threshold)} threshold:
          </p>
          <ul className="space-y-1.5">
            {receipt.scores.map((score) => {
              const cleared = score.probability >= receipt.threshold;
              const won = receipt.outcome === "delegated" && score.text === receipt.category;
              const status = won
                ? "sent here"
                : setAside.has(score.text)
                  ? "gave way to a narrower category"
                  : cleared
                    ? "cleared, scored lower"
                    : "below the threshold";
              return (
                <li key={score.category} className="grid gap-1 sm:grid-cols-[minmax(0,1fr)_9rem] sm:items-center sm:gap-3">
                  <div className="space-y-1">
                    <div className="flex justify-between gap-3">
                      <span className={cn(won && "font-medium")}>{score.text}</span>
                      <span className="tabular-nums">{score.probability.toFixed(2)}</span>
                    </div>
                    <div className="relative h-2 rounded-full bg-muted">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          won
                            ? "bg-indigo-600 dark:bg-indigo-400"
                            : cleared
                              ? "bg-indigo-300 dark:bg-indigo-700"
                              : "bg-muted-foreground/40"
                        )}
                        style={{ width: percent(score.probability, 1) }}
                      />
                      <div
                        className="absolute -top-1 h-4 w-px bg-foreground"
                        style={{ left: percent(receipt.threshold, 1) }}
                        aria-hidden="true"
                      />
                    </div>
                  </div>
                  <span className="text-xs text-muted-foreground">{status}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {receipt.chain.length > 1 && (
        <div className="space-y-1.5">
          <Chain directory={directory} chain={receipt.chain} />
          {!viewerResolves && (
            <p className="text-muted-foreground">
              {personName(directory, receipt.resolver)} ({personHome(directory, receipt.resolver)}){" "}
              {holds[receipt.kept_because]}.
            </p>
          )}
        </div>
      )}
      {receipt.loop && (
        <p className="text-muted-foreground">
          Loop found: {receipt.loop.map((id) => personName(directory, id)).join(" → ")}. Everyone
          on it keeps their own decision.
        </p>
      )}

      <p>
        Your ballot:{" "}
        <span className="font-medium">
          {receipt.choice === null ? "an abstention" : optionName(receipt.choice)}
        </span>
        <span className="text-muted-foreground">
          {viewerResolves
            ? receipt.choice === null
              ? " — you hold this decision and have not voted."
              : ""
            : `, a copy of ${personName(directory, receipt.resolver)}'s.`}
        </span>
      </p>
    </div>
  );
}

const OPTION_FILL = ["bg-indigo-600 dark:bg-indigo-400", "bg-amber-500 dark:bg-amber-400"];

function TallyBar({
  label,
  tally,
  question,
}: {
  label: string;
  tally: QuestionTally;
  question: DelegationQuestion;
}) {
  const total = Math.max(tally.total_ballots, 1);
  return (
    <div className="space-y-1 text-sm">
      <div className="flex flex-wrap justify-between gap-x-4">
        <span>{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {question.options
            .map((option) => `${option.name} ${tally.counts[option.id] ?? 0}`)
            .join(" · ")}
          {tally.abstentions > 0 && ` · Abstain ${tally.abstentions}`}
        </span>
      </div>
      <div className="flex h-3 gap-0.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
        {question.options.map((option, index) => (
          <div
            key={option.id}
            className={OPTION_FILL[index % OPTION_FILL.length]}
            style={{ width: `${((tally.counts[option.id] ?? 0) / total) * 100}%` }}
          />
        ))}
      </div>
    </div>
  );
}

function Concentration({ directory, result }: { directory: Directory; result: QuestionResult }) {
  const { metrics } = result;
  const longest = metrics.chain_lengths.reduce((most, entry) => Math.max(most, entry.hops), 0);
  const stats = [
    {
      label: "Votes decided by someone else",
      value: percent(metrics.delegated_share),
    },
    {
      label: metrics.largest_resolver
        ? `Largest share, held by ${personName(directory, metrics.largest_resolver)}`
        : "Largest share held by one person",
      value: percent(metrics.largest_share, 1),
    },
    { label: "Gini of voting weight", value: metrics.gini.toFixed(2) },
    {
      label: metrics.loops.length > 0 ? `Longest chain · ${metrics.loops.length} loop(s)` : "Longest chain",
      value: `${longest} hop${longest === 1 ? "" : "s"}`,
    },
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 pt-1 sm:grid-cols-4">
      {stats.map((stat) => (
        <div key={stat.label} className="rounded-md border p-3">
          <dd className="text-lg font-semibold tabular-nums">{stat.value}</dd>
          <dt className="text-xs leading-snug text-muted-foreground">{stat.label}</dt>
        </div>
      ))}
    </dl>
  );
}
