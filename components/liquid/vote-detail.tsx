"use client";

import { useEffect, useState } from "react";
import { AppLink as Link } from "./app-link";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { QuestionResult } from "@/types/delegation";
import { useAccount } from "./account-provider";
import { BALLOT_TEXT, METHOD_TEXT, optionName as nameOf } from "./ballots";
import { closing, personName, profileHref } from "./people";
import { Concentration, Receipt, TallyBar, VoteInput } from "./vote-parts";

/**
 * One vote in full: what is proposed, who it was issued to, how the viewer's
 * vote was routed, whose votes reached the viewer, and, once it has closed,
 * the result with delegation beside the result without it.
 */
export function VoteDetail({ questionId }: { questionId: string }) {
  const router = useRouter();
  const { scenario, directory, openVotes, votes, vote, closedPaper, error } = useAccount();

  const paper = scenario.ballot_papers.find((entry) =>
    entry.questions.some((question) => question.id === questionId)
  );
  const question = paper?.questions.find((entry) => entry.id === questionId);
  const closed = paper?.status === "closed";

  const [past, setPast] = useState<QuestionResult | null | undefined>(undefined);
  useEffect(() => {
    if (!paper || !closed) return;
    let stale = false;
    void closedPaper(paper.id).then((response) => {
      if (stale) return;
      setPast(response?.questions.find((entry) => entry.question_id === questionId) ?? null);
    });
    return () => {
      stale = true;
    };
  }, [paper, closed, closedPaper, questionId]);

  if (!paper || !question) {
    return (
      <div className="space-y-3 text-sm">
        <p>There is no vote with that id.</p>
        <Link href="/liquid/votes" className="text-primary underline-offset-4 hover:underline">
          Back to Incoming Votes
        </Link>
      </div>
    );
  }

  const open = openVotes?.find((entry) => entry.question.id === questionId);
  const result = closed ? past : open?.result;
  const optionName = (id: string) => nameOf(question, id);
  const yesNo = question.ballot_type === "single_choice";
  const district = (directory.jurisdictions.get(paper.jurisdiction) ?? paper.jurisdiction).replace(
    /^The /,
    "the "
  );
  const decides =
    result &&
    (result.receipt
      ? result.receipt.resolver === directory.viewer
      : result.inbox.votes_for_others > 0);

  return (
    <article className="max-w-3xl space-y-8">
      <Button variant="ghost" size="sm" className="-ml-2" onClick={() => router.back()}>
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back
      </Button>

      <header className="space-y-3">
        <p className="liquid-label">
          {paper.title} · {closing(paper.closes_in_days)}
        </p>
        <p className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-full border border-primary/60 px-2 py-0.5 font-mono font-medium text-primary">
            {question.label}
          </span>
          <span className="rounded-full border px-2 py-0.5 text-muted-foreground">
            {question.kind}
          </span>
          {!yesNo && (
            <span className="rounded-full border px-2 py-0.5 text-muted-foreground">
              {BALLOT_TEXT[question.ballot_type]}
            </span>
          )}
        </p>
        <h2 className="text-2xl font-semibold tracking-tight">{question.title}</h2>
        <blockquote className="border-l-2 border-primary/60 pl-4 text-base leading-relaxed">
          {question.wording}
        </blockquote>
        <p className="text-sm leading-relaxed text-muted-foreground">{question.summary}</p>
        <dl className="grid gap-x-8 gap-y-3 pt-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted-foreground">Fiscal impact</dt>
            <dd>{question.fiscal}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Placed on the ballot by</dt>
            <dd>{question.placed_by}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Issued to</dt>
            <dd>
              {paper.eligible_voters} residents of {district}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Decided</dt>
            <dd>
              {yesNo ? "Yes or no, " : ""}
              {METHOD_TEXT[question.method]}
            </dd>
          </div>
        </dl>
        {yesNo ? (
          <div className="grid gap-3 pt-2 text-sm sm:grid-cols-2">
            <div className="liquid-panel p-3">
              <p className="liquid-label">Argument for</p>
              <p className="mt-1 leading-relaxed">{question.argument_for}</p>
            </div>
            <div className="liquid-panel p-3">
              <p className="liquid-label">Argument against</p>
              <p className="mt-1 leading-relaxed">{question.argument_against}</p>
            </div>
          </div>
        ) : (
          // The vote input lists the options itself, where the viewer has one.
          (closed || !result || !(result.receipt || decides)) && (
            <ul className="grid gap-3 pt-2 text-sm sm:grid-cols-2">
              {question.options.map((option) => (
                <li key={option.id} className="liquid-panel p-3">
                  <p className="font-medium">{option.name}</p>
                  {option.note && <p className="mt-1 text-muted-foreground">{option.note}</p>}
                </li>
              ))}
            </ul>
          )
        )}
      </header>

      {result === undefined && (
        <p className="text-sm text-muted-foreground">{error ?? "Loading this vote…"}</p>
      )}
      {result === null && (
        <p className="text-sm text-muted-foreground">This vote could not be loaded.</p>
      )}

      {result && (
        <>
          {!closed && (result.receipt || decides) && (
            <section className="liquid-panel liquid-glow space-y-3 p-4">
              <h3 className="text-sm font-semibold">
                {decides ? "Your vote" : "Vote yourself instead"}
              </h3>
              <VoteInput
                question={question}
                vote={votes[question.id]}
                onVote={(choice) => vote(question.id, choice)}
              />
              <p className="text-sm text-muted-foreground">
                {decides
                  ? votes[question.id]
                    ? "You can change this until the ballot closes."
                    : "If you have not voted when the ballot closes, your ballot is an abstention."
                  : "Your own vote overrides your delegation for this question only."}
              </p>
            </section>
          )}

          <section className="space-y-3">
            <h3 className="liquid-label">
              Your receipt
            </h3>
            {result.receipt ? (
              <Receipt
                directory={directory}
                receipt={result.receipt}
                question={question}
                closed={closed}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                This ballot {closed ? "was" : "is"} not issued to your district, so you{" "}
                {closed ? "had" : "have"} no vote of your own on it.
              </p>
            )}
          </section>

          <section className="space-y-3">
            <h3 className="liquid-label">
              Votes that reached you
            </h3>
            {result.inbox.votes_for_others === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nobody else&apos;s vote {closed ? "ended" : "ends"} with you on this question.
              </p>
            ) : (
              <div className="space-y-1.5 text-sm">
                <p>
                  You {closed ? "answered" : "answer"} for {result.inbox.votes_for_others} other{" "}
                  {result.inbox.votes_for_others === 1 ? "person" : "people"}.{" "}
                  {result.inbox.answered
                    ? `Each of their ballots ${closed ? "was" : "is"} a copy of yours.`
                    : closed
                      ? "You did not vote, so each of their ballots was an abstention."
                      : "Until you vote, each of their ballots is an abstention."}
                </p>
                <p className="flex flex-wrap gap-x-3 gap-y-1">
                  {result.inbox.held.map((held) => (
                    <Link
                      key={held.voter}
                      href={profileHref(directory, held.voter)}
                      className="underline-offset-4 hover:underline"
                    >
                      {personName(directory, held.voter)}
                    </Link>
                  ))}
                </p>
              </div>
            )}
          </section>

          <section className="space-y-3">
            <h3 className="liquid-label">
              {closed ? "Result" : "Result so far"}
            </h3>
            {closed ? (
              <>
                <div className="space-y-3">
                  <TallyBar label="With delegation" tally={result.delegated} question={question} />
                  <TallyBar
                    label="Without delegation, from the people who voted themselves"
                    tally={result.direct}
                    question={question}
                  />
                </div>
                <p className="text-sm">
                  {result.winner_changed ? (
                    <span className="font-medium text-amber-700 dark:text-amber-400">
                      Delegation changed the result:{" "}
                      {result.delegated.winners.map(optionName).join(" / ")} won, where direct
                      voting would have given {result.direct.winners.map(optionName).join(" / ")}.
                    </span>
                  ) : (
                    <span className="text-muted-foreground">
                      {result.delegated.winners.map(optionName).join(" / ")} won, as it would have
                      without delegation.
                    </span>
                  )}
                  {(result.delegated.tiebreak_applied || result.direct.tiebreak_applied) && (
                    <span className="text-muted-foreground">
                      {" "}
                      A tie was settled by the seeded tiebreak.
                    </span>
                  )}
                </p>
                <Concentration directory={directory} result={result} />
              </>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">
                  The count is published when the ballot closes. {result.cast_so_far} people have
                  filled in this question so far; this is where the votes stand now.
                </p>
                <Concentration directory={directory} result={result} />
              </>
            )}
          </section>
        </>
      )}
    </article>
  );
}
