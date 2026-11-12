"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type {
  DelegationQuestion,
  QuestionResult,
  QuestionTally,
  VoteReceipt,
} from "@/types/delegation";
import { percent, personHome, personName, type Directory } from "./people";
import { Chain } from "./person-bits";

/** Buttons for the viewer's own vote on a question. Selecting the chosen one again clears it. */
export function VoteButtons({
  question,
  vote,
  onVote,
}: {
  question: DelegationQuestion;
  vote: string | undefined;
  onVote: (optionId: string | null) => void;
}) {
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
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
    </span>
  );
}

/** How the routing rule handled the viewer's vote on one question. */
export function Receipt({
  directory,
  receipt,
  optionName,
  closed,
}: {
  directory: Directory;
  receipt: VoteReceipt;
  optionName: (id: string | null) => string;
  closed: boolean;
}) {
  const viewerResolves = receipt.resolver === directory.viewer;
  const setAside = new Set(receipt.set_aside);
  const decides = closed ? "decided" : "decides";

  let headline: string;
  if (receipt.outcome === "delegated") {
    headline = viewerResolves
      ? `Sent under “${receipt.category}”, and the chain came back to you, so the decision ${closed ? "was" : "is"} yours.`
      : `Sent under “${receipt.category}”. ${personName(directory, receipt.resolver)} ${decides}.`;
  } else if (receipt.outcome === "direct_vote") {
    headline = "You voted yourself, which overrides your delegations.";
  } else if (receipt.outcome === "no_delegations") {
    headline = "You have handed nothing over, so this decision stays with you.";
  } else if (receipt.outcome === "none_available") {
    headline = "None of your categories covers this question, so the decision stays with you.";
  } else {
    headline =
      "One of your categories has no judgment for this question, so the decision stays with you.";
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
            Is this question about the category? The decision model&apos;s yes-probability for
            each of yours, against the {percent(receipt.threshold)} threshold:
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
                <li
                  key={score.category}
                  className="grid gap-1 sm:grid-cols-[minmax(0,1fr)_10rem] sm:items-center sm:gap-3"
                >
                  <div className="space-y-1">
                    <div className="flex justify-between gap-3">
                      <span className={cn(won && "font-medium")}>{score.text}</span>
                      <span className="font-mono tabular-nums">{score.probability.toFixed(2)}</span>
                    </div>
                    <div className="relative h-2 rounded-full bg-muted">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          won
                            ? "bg-primary"
                            : cleared
                              ? "bg-primary/40"
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
              ? closed
                ? ". The decision was yours and you did not vote before it closed."
                : ". The decision is yours and you have not voted yet."
              : ""
            : receipt.choice === null
              ? closed
                ? ""
                : `. ${personName(directory, receipt.resolver)} has not voted yet.`
              : `, a copy of ${personName(directory, receipt.resolver)}'s.`}
        </span>
      </p>
    </div>
  );
}

const OPTION_FILL = ["bg-primary", "bg-amber-400"];

export function TallyBar({
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

/** How much of one question's vote ended up in few hands. */
export function Concentration({
  directory,
  result,
}: {
  directory: Directory;
  result: QuestionResult;
}) {
  const { metrics } = result;
  const longest = metrics.chain_lengths.reduce((most, entry) => Math.max(most, entry.hops), 0);
  const stats = [
    { label: "Votes decided by someone else", value: percent(metrics.delegated_share) },
    {
      label: metrics.largest_resolver
        ? `Largest share, held by ${personName(directory, metrics.largest_resolver)}`
        : "Largest share held by one person",
      value: percent(metrics.largest_share, 1),
    },
    { label: "Gini of voting weight", value: metrics.gini.toFixed(2) },
    {
      label:
        metrics.loops.length > 0
          ? `Longest chain · ${metrics.loops.length} ${metrics.loops.length === 1 ? "loop" : "loops"}`
          : "Longest chain",
      value: `${longest} hop${longest === 1 ? "" : "s"}`,
    },
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 pt-1 sm:grid-cols-4">
      {stats.map((stat) => (
        <div key={stat.label} className="liquid-panel p-3">
          <dd className="font-mono text-lg font-semibold tabular-nums">{stat.value}</dd>
          <dt className="text-xs leading-snug text-muted-foreground">{stat.label}</dt>
        </div>
      ))}
    </dl>
  );
}
