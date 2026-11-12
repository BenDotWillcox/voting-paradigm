"use client";

import { useState } from "react";
import { AppLink as Link } from "./app-link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Check, Clock, CornerUpRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAccount, type OpenVote } from "./account-provider";
import { choiceShort } from "./ballots";
import { closing, personName, profileHref, type Directory } from "./people";
import { needsViewer } from "./votes";

type Box = "mine" | "sent";

/** Why an open question is the viewer's to decide. */
function reason(entry: OpenVote, viewer: string): string {
  const { receipt, inbox } = entry.result;
  const others =
    inbox.votes_for_others > 0
      ? `${inbox.votes_for_others} other ${inbox.votes_for_others === 1 ? "person" : "people"}`
      : null;
  if (!receipt) return `Not issued to you. You answer for ${others}.`;
  const own =
    receipt.outcome === "direct_vote"
      ? "You chose to vote yourself"
      : receipt.kept_because === "loop"
        ? "A delegation looped back to you"
        : receipt.outcome === "router_unavailable"
          ? "A category of yours has no judgment"
          : "None of your categories covers it";
  return others && receipt.resolver === viewer ? `${own}. You also answer for ${others}.` : `${own}.`;
}

function Deadline({ days }: { days: number }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[0.7rem]",
        days <= 3 ? "border-amber-400/60 bg-amber-400/10 text-amber-300" : "text-muted-foreground"
      )}
    >
      <Clock className="h-3 w-3" aria-hidden="true" />
      {closing(days)}
    </span>
  );
}

/** The way into a vote's own page, where it is read in full and voted on. */
function Open({ id, label }: { id: string; label: string }) {
  return (
    <Link
      href={`/liquid/votes/${id}`}
      className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors hover:border-primary hover:bg-accent"
    >
      {label}
      <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
    </Link>
  );
}

function Row({
  entry,
  directory,
  tone,
  children,
}: {
  entry: OpenVote;
  directory: Directory;
  tone: "waiting" | "answered" | "sent";
  children: React.ReactNode;
}) {
  return (
    <li
      className={cn(
        "liquid-panel border-l-2 p-4",
        tone === "waiting" && "border-l-amber-400",
        tone === "answered" && "border-l-emerald-400",
        tone === "sent" && "border-l-[var(--lq-violet)]"
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 space-y-1">
          <Link
            href={`/liquid/votes/${entry.question.id}`}
            className="font-medium underline-offset-4 hover:text-primary hover:underline"
          >
            {entry.question.title}
          </Link>
          <p className="text-sm leading-relaxed text-muted-foreground">{entry.question.summary}</p>
          <p className="liquid-label">
            {entry.question.label} · {entry.question.kind} · {entry.paper.title} ·{" "}
            {directory.jurisdictions.get(entry.paper.jurisdiction) ?? entry.paper.jurisdiction}
          </p>
        </div>
        <Deadline days={entry.paper.closes_in_days} />
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-sm">
        {children}
      </div>
    </li>
  );
}

/**
 * Incoming votes: every open vote, soonest to close first. One box holds
 * the votes that wait on the viewer, the other the votes their delegates
 * hold. This is an overview: a vote is cast from its own page, where the
 * proposal can be read in full.
 */
export function VotesList() {
  const { directory, openVotes, votes, error, resolving } = useAccount();
  const [box, setBox] = useState<Box>(useSearchParams().get("show") === "sent" ? "sent" : "mine");

  if (!openVotes) {
    return (
      <p className="text-sm text-muted-foreground">
        {error ?? "Working out where each open vote goes…"}
      </p>
    );
  }

  const mine = openVotes.filter((entry) => needsViewer(entry, directory.viewer));
  const sent = openVotes.filter(
    (entry) => !needsViewer(entry, directory.viewer) && entry.result.receipt
  );
  const unvoted = mine.filter((entry) => !votes[entry.question.id]).length;

  const boxes: { id: Box; label: string; count: number }[] = [
    { id: "mine", label: "Needs you", count: mine.length },
    { id: "sent", label: "With your delegates", count: sent.length },
  ];

  return (
    <div className={cn("space-y-6 transition-opacity", resolving && "opacity-60")}>
      <div className="space-y-1">
        <p className="liquid-label">Incoming votes</p>
        <h2 className="text-2xl font-semibold tracking-tight">
          {unvoted === 0
            ? "Nothing is waiting on you"
            : `${unvoted} ${unvoted === 1 ? "vote is" : "votes are"} waiting on you`}
        </h2>
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Open votes, soonest deadline first. A vote you hold and have not cast when its ballot
          closes counts as an abstention, for you and for everyone whose vote reached you.
        </p>
      </div>

      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
          {error} What is shown may not match your latest change.
        </p>
      )}

      <div role="tablist" aria-label="Open votes" className="liquid-panel inline-flex gap-1 p-1">
        {boxes.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={box === entry.id}
            onClick={() => setBox(entry.id)}
            className={cn(
              "flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-colors",
              box === entry.id
                ? "bg-primary font-medium text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            {entry.label}
            <span className="font-mono text-xs tabular-nums opacity-80">{entry.count}</span>
          </button>
        ))}
      </div>

      {box === "mine" && (
        <ol className="space-y-3">
          {mine.map((entry) => {
            const cast = votes[entry.question.id];
            return (
              <Row
                key={entry.question.id}
                entry={entry}
                directory={directory}
                tone={cast ? "answered" : "waiting"}
              >
                <span className="text-muted-foreground">{reason(entry, directory.viewer)}</span>
                <span className="flex items-center gap-3">
                  {cast ? (
                    <span className="inline-flex items-center gap-1 text-xs text-emerald-300">
                      <Check className="h-3.5 w-3.5" aria-hidden="true" />
                      Voted {choiceShort(entry.question, cast)}
                    </span>
                  ) : (
                    <span className="text-xs text-amber-300">Not voted</span>
                  )}
                  <Open id={entry.question.id} label={cast ? "Review" : "Read and vote"} />
                </span>
              </Row>
            );
          })}
        </ol>
      )}

      {box === "sent" &&
        (sent.length === 0 ? (
          <p className="text-sm text-muted-foreground">No open vote is with a delegate.</p>
        ) : (
          <>
            <ol className="space-y-3">
              {sent.map((entry) => {
                const receipt = entry.result.receipt;
                return (
                  <Row key={entry.question.id} entry={entry} directory={directory} tone="sent">
                    {receipt && (
                      <span className="inline-flex flex-wrap items-center gap-1.5 text-muted-foreground">
                        <CornerUpRight className="h-3.5 w-3.5" aria-hidden="true" />
                        <Link
                          href={profileHref(directory, receipt.resolver)}
                          className="font-medium text-foreground underline-offset-4 hover:underline"
                        >
                          {personName(directory, receipt.resolver)}
                        </Link>
                        decides, under “{receipt.category}”
                        <span
                          className={cn(
                            "rounded-full border px-2 py-0.5 text-xs",
                            receipt.choice
                              ? "border-emerald-400/50 text-emerald-300"
                              : "border-amber-400/50 text-amber-300"
                          )}
                        >
                          {receipt.choice ? "has voted" : "has not voted yet"}
                        </span>
                      </span>
                    )}
                    <Open id={entry.question.id} label="Read the proposal" />
                  </Row>
                );
              })}
            </ol>
          </>
        ))}

      <p className="text-sm text-muted-foreground">
        Votes that have closed are in{" "}
        <Link href={profileHref(directory, directory.viewer)} className="text-primary underline-offset-4 hover:underline">
          your voting history
        </Link>
        .
      </p>
    </div>
  );
}
