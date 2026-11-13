"use client";

import { useEffect, useState } from "react";
import { History, Loader2 } from "lucide-react";
import { backtestDelegationsAction } from "@/actions/delegation-actions";
import { cn } from "@/lib/utils";
import type { DelegationBacktest } from "@/types/delegation";
import { useAccount } from "./account-provider";
import { choiceShort, findQuestion } from "./ballots";
import { ago, personName } from "./people";

type Held = { category: string; delegate: string };
type Route = DelegationBacktest["changed"][number]["after"];

const SHOWN = 3;

/**
 * What a change to the viewer's delegations would have done on the votes
 * that have already closed: which would have gone somewhere else, and what
 * the person they end with actually chose.
 */
export function BacktestPanel({ before, after }: { before: Held[]; after: Held[] }) {
  const { scenario, directory } = useAccount();
  const [result, setResult] = useState<DelegationBacktest | null>(null);
  const [failed, setFailed] = useState(false);
  const [all, setAll] = useState(false);
  const request = JSON.stringify({
    before: before.map(({ category, delegate }) => ({ category, delegate })),
    after: after.map(({ category, delegate }) => ({ category, delegate })),
    threshold: scenario.threshold,
  });

  useEffect(() => {
    let current = true;
    setResult(null);
    setFailed(false);
    setAll(false);
    void backtestDelegationsAction(JSON.parse(request)).then((answer) => {
      if (!current) return;
      if (answer.isSuccess && answer.data) setResult(answer.data);
      else setFailed(true);
    });
    return () => {
      current = false;
    };
  }, [request]);

  const who = (id: string) => (id === directory.viewer ? "you" : personName(directory, id));

  let body: React.ReactNode;
  if (failed) {
    body = <p className="text-muted-foreground">The past votes could not be replayed just now.</p>;
  } else if (!result) {
    body = (
      <p className="flex items-center gap-2 text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
        Replaying the votes that have closed…
      </p>
    );
  } else if (result.unjudged_categories.length > 0) {
    body = (
      <p className="text-muted-foreground">
        “{result.unjudged_categories.join("”, “")}” was never checked against the votes that have
        closed, so there is nothing to replay. New wording is only checked against open votes.
      </p>
    );
  } else if (result.changed.length === 0) {
    body = (
      <p className="text-muted-foreground">
        None of the {result.questions} closed votes issued to you would have gone anywhere else.
      </p>
    );
  } else {
    const handed = result.changed.filter((item) => item.after.resolver !== directory.viewer);
    const agreed = handed.filter((item) => item.after.agrees === true).length;
    const differed = handed.filter((item) => item.after.agrees === false).length;
    const silent = handed.filter((item) => item.after.agrees === null).length;
    const kept = result.changed.length - handed.length;
    const shown = all ? result.changed : result.changed.slice(0, SHOWN);
    body = (
      <>
        <p>
          <span className="font-medium">
            {result.changed.length} of the {result.questions}
          </span>{" "}
          closed votes issued to you would have gone somewhere else.
        </p>
        {handed.length > 0 && (
          <p className="text-muted-foreground">
            {handed.length} would have been decided for you:{" "}
            {[
              agreed > 0 && `${agreed} the way this account leans`,
              differed > 0 && `${differed} the other way`,
              silent > 0 && `${silent} by someone who did not vote`,
            ]
              .filter(Boolean)
              .join(", ")}
            .
          </p>
        )}
        {kept > 0 && (
          <p className="text-muted-foreground">
            {kept} would have stayed with you to decide.
          </p>
        )}
        <ul className="space-y-2 pt-1">
          {shown.map((item) => {
            const question = findQuestion(scenario, item.question_id);
            const route = (side: Route) =>
              side.resolver === directory.viewer ? (
                "you decide"
              ) : (
                <>
                  {who(side.resolver)}
                  {side.choice
                    ? ` voted ${choiceShort(question, side.choice)}`
                    : " did not vote"}
                </>
              );
            return (
              <li key={item.question_id} className="border-l-2 border-border pl-3">
                <p className="font-medium">{item.title}</p>
                <p className="font-mono text-xs text-muted-foreground">
                  {item.label} · closed {ago(item.closed_days_ago)}
                </p>
                <p className="text-muted-foreground">
                  Was: {route(item.before)}. With this: {route(item.after)}
                  {item.after.category && <> under “{item.after.category}”</>}.
                </p>
                {item.after.agrees !== null && (
                  <p
                    className={cn(
                      "text-xs",
                      item.after.agrees ? "text-emerald-300" : "text-amber-300",
                    )}
                  >
                    {item.after.agrees ? "Matches" : "Differs from"} this account’s lean:{" "}
                    {choiceShort(question, item.own_choice)}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
        {result.changed.length > SHOWN && (
          <button
            type="button"
            className="text-xs underline underline-offset-4 hover:text-foreground"
            onClick={() => setAll(!all)}
          >
            {all ? "Show fewer" : `Show all ${result.changed.length}`}
          </button>
        )}
      </>
    );
  }

  return (
    <section className="liquid-panel space-y-2 p-3 text-sm" aria-live="polite">
      <h4 className="liquid-label flex items-center gap-1.5">
        <History className="h-3.5 w-3.5" aria-hidden="true" />
        Looking back
      </h4>
      {body}
      {result && result.unjudged_categories.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Each vote is replayed through the network of the day it closed. Votes you cast yourself
          are set aside, and “this account’s lean” is the position written for the demo account.
        </p>
      )}
    </section>
  );
}
