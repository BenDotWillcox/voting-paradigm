"use client";

import { useState } from "react";
import { ArrowDown, ArrowUp, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type {
  DelegationQuestion,
  QuestionResult,
  QuestionTally,
  VoteReceipt,
} from "@/types/delegation";
import { choiceLabel, optionName, type Choice } from "./ballots";
import { percent, personHome, personName, type Directory } from "./people";
import { Chain } from "./person-bits";

type VoteProps = {
  question: DelegationQuestion;
  vote: Choice | undefined;
  onVote: (choice: Choice | null) => void;
};

/** The viewer's own vote on a question, in the shape its ballot takes. */
export function VoteInput(props: VoteProps) {
  if (props.question.ballot_type === "ranked") {
    // Keyed by the saved vote, so the draft starts over when it is cleared.
    return <RankedVote key={(props.vote ?? []).join("|")} {...props} />;
  }
  if (props.question.ballot_type === "approval") return <ApprovalVote {...props} />;
  return <SingleVote {...props} />;
}

/** One option of several. Selecting the chosen one again clears it. */
function SingleVote({ question, vote, onVote }: VoteProps) {
  const chosen = vote?.[0];
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {question.options.map((option) => (
        <Button
          key={option.id}
          type="button"
          size="sm"
          variant={chosen === option.id ? "default" : "outline"}
          aria-pressed={chosen === option.id}
          onClick={() => onVote(chosen === option.id ? null : [option.id])}
        >
          {option.name}
        </Button>
      ))}
      {chosen && (
        <Button type="button" size="sm" variant="ghost" onClick={() => onVote(null)}>
          Clear
        </Button>
      )}
    </span>
  );
}

/** Any number of options. Each tick is saved at once; none ticked is no vote. */
function ApprovalVote({ question, vote, onVote }: VoteProps) {
  const approved = new Set(vote ?? []);
  const toggle = (id: string) => {
    const next = question.options
      .map((option) => option.id)
      .filter((option) => (option === id ? !approved.has(option) : approved.has(option)));
    onVote(next.length > 0 ? next : null);
  };
  return (
    <ul className="space-y-2">
      {question.options.map((option) => {
        const on = approved.has(option.id);
        return (
          <li key={option.id}>
            <button
              type="button"
              role="checkbox"
              aria-checked={on}
              onClick={() => toggle(option.id)}
              className={cn(
                "flex w-full items-start gap-3 rounded-lg border p-3 text-left text-sm transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
                on && "border-primary bg-primary/10"
              )}
            >
              <span
                className={cn(
                  "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border",
                  on && "border-primary bg-primary text-primary-foreground"
                )}
                aria-hidden="true"
              >
                {on && <Check className="h-3.5 w-3.5" />}
              </span>
              <span>
                <span className="block font-medium">{option.name}</span>
                {option.note && (
                  <span className="block text-muted-foreground">{option.note}</span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Every option in order. Options are picked one at a time, most wanted
 * first, and can be moved or taken back; the ranking is cast once it is
 * complete, because the count needs every option placed.
 */
function RankedVote({ question, vote, onVote }: VoteProps) {
  const [draft, setDraft] = useState<Choice>(vote ?? []);
  const unranked = question.options.filter((option) => !draft.includes(option.id));
  const complete = unranked.length === 0;
  const saved = vote !== undefined && vote.join("|") === draft.join("|");

  const move = (index: number, by: number) => {
    const next = [...draft];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    setDraft(next);
  };
  const note = (id: string) => question.options.find((option) => option.id === id)?.note;

  return (
    <div className="space-y-3">
      {draft.length > 0 && (
        <ol className="space-y-2">
          {draft.map((id, index) => (
            <li
              key={id}
              className="flex items-start gap-3 rounded-lg border border-primary bg-primary/10 p-3 text-sm"
            >
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary font-mono text-xs font-semibold text-primary-foreground">
                {index + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-medium">{optionName(question, id)}</span>
                {note(id) && <span className="block text-muted-foreground">{note(id)}</span>}
              </span>
              <span className="flex shrink-0 gap-1">
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  disabled={index === 0}
                  aria-label={`Move ${optionName(question, id)} up`}
                  onClick={() => move(index, -1)}
                >
                  <ArrowUp className="h-4 w-4" aria-hidden="true" />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  disabled={index === draft.length - 1}
                  aria-label={`Move ${optionName(question, id)} down`}
                  onClick={() => move(index, 1)}
                >
                  <ArrowDown className="h-4 w-4" aria-hidden="true" />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={`Take ${optionName(question, id)} out of the ranking`}
                  onClick={() => setDraft(draft.filter((other) => other !== id))}
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </Button>
              </span>
            </li>
          ))}
        </ol>
      )}

      {unranked.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            {draft.length === 0
              ? "Pick your first choice, then the next, until every option is placed."
              : "Pick your next choice."}
          </p>
          <ul className="space-y-2">
            {unranked.map((option) => (
              <li key={option.id}>
                <button
                  type="button"
                  onClick={() => setDraft([...draft, option.id])}
                  className="flex w-full items-start gap-3 rounded-lg border p-3 text-left text-sm transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                >
                  <span
                    className="mt-0.5 h-5 w-5 shrink-0 rounded-full border border-dashed"
                    aria-hidden="true"
                  />
                  <span>
                    <span className="block font-medium">{option.name}</span>
                    {option.note && (
                      <span className="block text-muted-foreground">{option.note}</span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <span className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" disabled={!complete || saved} onClick={() => onVote(draft)}>
          {saved ? "Ranking cast" : vote ? "Cast the new ranking" : "Cast this ranking"}
        </Button>
        {(vote || draft.length > 0) && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              setDraft([]);
              if (vote) onVote(null);
            }}
          >
            Clear
          </Button>
        )}
      </span>
    </div>
  );
}

/** How the routing rule handled the viewer's vote on one question. */
export function Receipt({
  directory,
  receipt,
  question,
  closed,
}: {
  directory: Directory;
  receipt: VoteReceipt;
  question: DelegationQuestion;
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
          {receipt.choice === null
            ? closed
              ? "an abstention"
              : "nothing yet"
            : choiceLabel(question, receipt.choice)}
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
                ? `. ${personName(directory, receipt.resolver)} held the decision and did not vote.`
                : receipt.resolver_votes_in_days === null
                  ? `. ${personName(directory, receipt.resolver)} has not voted.`
                  : `. ${personName(directory, receipt.resolver)} has not voted yet.`
              : `, a copy of ${personName(directory, receipt.resolver)}'s.`}
        </span>
      </p>
    </div>
  );
}

const OPTION_FILL = ["bg-primary", "bg-amber-400"];

/**
 * One count of a question. A yes/no question is a single split bar; a choice
 * among several options is a row per option, most votes first, with the
 * rounds of an instant-runoff count listed under it.
 */
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
  const cast = tally.total_ballots - tally.abstentions;

  if (question.ballot_type === "single_choice") {
    return (
      <div className="space-y-1 text-sm">
        <div className="flex flex-wrap justify-between gap-x-4">
          <span>{label}</span>
          <span className="tabular-nums text-muted-foreground">
            {question.options
              .map((option) => `${option.name} ${tally.counts[option.id] ?? 0}`)
              .join(" · ")}
            {tally.abstentions > 0 && ` · Not voted ${tally.abstentions}`}
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

  const ranked = tally.method === "irv";
  const final = ranked ? tally.rounds[tally.rounds.length - 1]?.counts : undefined;
  const rows = [...question.options].sort(
    (a, b) =>
      (final?.[b.id] ?? -1) - (final?.[a.id] ?? -1) ||
      (tally.counts[b.id] ?? 0) - (tally.counts[a.id] ?? 0)
  );
  const most = Math.max(1, ...rows.map((option) => tally.counts[option.id] ?? 0));
  return (
    <div className="space-y-2 text-sm">
      <div className="flex flex-wrap justify-between gap-x-4">
        <span>{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {cast} ballots cast{tally.abstentions > 0 && ` · Not voted ${tally.abstentions}`}
        </span>
      </div>
      <ul className="space-y-1.5">
        {rows.map((option) => {
          const votes = tally.counts[option.id] ?? 0;
          const won = tally.winners.includes(option.id);
          return (
            <li key={option.id} className="grid grid-cols-[minmax(0,11rem)_minmax(0,1fr)_2.5rem] items-center gap-3">
              <span className={cn("truncate", won && "font-medium")}>{option.name}</span>
              <span className="h-3 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                <span
                  className={cn("block h-full rounded-full", won ? "bg-primary" : "bg-primary/40")}
                  style={{ width: `${(votes / most) * 100}%` }}
                />
              </span>
              <span className="text-right font-mono tabular-nums">{votes}</span>
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-muted-foreground">
        {ranked ? "First choices." : "Approvals; a ballot can approve several."}
        {ranked &&
          tally.rounds.slice(0, -1).map((round) => {
            const next = tally.rounds[round.round]?.counts ?? {};
            const standing = Object.entries(next)
              .map(([id, votes]) => `${optionName(question, id)} ${votes}`)
              .join(", ");
            return ` Round ${round.round}: ${round.eliminated
              .map((id) => optionName(question, id))
              .join(" and ")} dropped, leaving ${standing}.`;
          })}
      </p>
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
