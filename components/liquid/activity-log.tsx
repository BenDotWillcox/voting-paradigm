"use client";

import { useMemo, useState } from "react";
import { ArrowRightLeft, Check, CircleSlash, CornerUpRight, Minus, Plus, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PersonProfile } from "@/types/delegation";
import { useAccount, type LocalEvent } from "./account-provider";
import { AppLink as Link } from "./app-link";
import { choiceLabel, findQuestion } from "./ballots";
import { ago, personName, profileHref, type Directory } from "./people";

type Kind = "delegation" | "vote";

type Item = {
  key: string;
  kind: Kind;
  /** Larger is more recent; today's own actions sort above everything dated. */
  order: number;
  when: string;
  Icon: typeof Plus;
  tone: string;
  body: React.ReactNode;
  href?: string;
};

const VIOLET = "border-primary/50 bg-primary/15 text-violet-200";
const BLUE = "border-sky-400/50 bg-sky-400/10 text-sky-200";
const AMBER = "border-amber-400/60 bg-amber-400/10 text-amber-200";
const GREY = "border-border bg-muted text-muted-foreground";

function Person({ directory, id }: { directory: Directory; id: string }) {
  return (
    <Link
      href={profileHref(directory, id)}
      className="font-medium underline-offset-4 hover:underline"
    >
      {personName(directory, id)}
    </Link>
  );
}

function clock(at: string): string {
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return "Today";
  const today = new Date().toDateString() === date.toDateString();
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return today ? `Today, ${time}` : `${date.toLocaleDateString()}, ${time}`;
}

/**
 * Everything that has happened to the viewer's account, newest first: what
 * they did in this browser, the dated changes to their delegations and to
 * the delegations other people made to them, and how each closed vote went.
 */
export function ActivityLog({ profile }: { profile: PersonProfile }) {
  const { scenario, directory, log } = useAccount();
  const [filter, setFilter] = useState<"all" | Kind>("all");
  const viewer = directory.viewer;

  const items = useMemo(() => {
    const found: Item[] = [];

    log.forEach((event, index) => {
      found.push(localItem(event, index, log.length));
    });

    function localItem(event: LocalEvent, index: number, total: number): Item {
      const base = {
        key: `local-${event.at}-${index}`,
        order: 1_000_000 + (total - index),
        when: clock(event.at),
      };
      const category = <>“{event.category}”</>;
      if (event.kind === "voted" || event.kind === "withdrew") {
        const question = findQuestion(scenario, event.question ?? "");
        return {
          ...base,
          kind: "vote",
          Icon: event.kind === "voted" ? Check : CircleSlash,
          tone: event.kind === "voted" ? VIOLET : GREY,
          href: `/liquid/votes/${event.question}`,
          body:
            event.kind === "voted" ? (
              <>
                You voted{" "}
                <span className="font-medium">{choiceLabel(question, event.choice ?? [])}</span>{" "}
                on {question?.title ?? event.question}.
              </>
            ) : (
              <>You withdrew your vote on {question?.title ?? event.question}.</>
            ),
        };
      }
      if (event.kind === "added") {
        return {
          ...base,
          kind: "delegation",
          Icon: Plus,
          tone: VIOLET,
          body: (
            <>
              You handed {category} to <Person directory={directory} id={event.delegate ?? ""} />.
            </>
          ),
        };
      }
      if (event.kind === "moved") {
        return {
          ...base,
          kind: "delegation",
          Icon: ArrowRightLeft,
          tone: VIOLET,
          body: (
            <>
              You moved {category} from <Person directory={directory} id={event.before ?? ""} /> to{" "}
              <Person directory={directory} id={event.delegate ?? ""} />.
            </>
          ),
        };
      }
      if (event.kind === "renamed") {
        return {
          ...base,
          kind: "delegation",
          Icon: ArrowRightLeft,
          tone: VIOLET,
          body: (
            <>
              You reworded “{event.was}” as {category}.
            </>
          ),
        };
      }
      return {
        ...base,
        kind: "delegation",
        Icon: Minus,
        tone: GREY,
        body: (
          <>
            You took {category} back from <Person directory={directory} id={event.before ?? ""} />.
          </>
        ),
      };
    }

    profile.changes.forEach((change, index) => {
      const category = <>“{change.category}”</>;
      const base = {
        key: `change-${index}`,
        kind: "delegation" as const,
        // A change is made during the day; a ballot closes at its end.
        order: change.day * 2,
        when: ago(-change.day),
      };
      if (change.delegator === viewer) {
        found.push({
          ...base,
          Icon: change.before === null ? Plus : change.after === null ? Minus : ArrowRightLeft,
          tone: change.after === null ? GREY : VIOLET,
          body:
            change.before === null ? (
              <>
                You handed {category} to <Person directory={directory} id={change.after ?? ""} />.
              </>
            ) : change.after === null ? (
              <>
                You took {category} back from <Person directory={directory} id={change.before} />.
              </>
            ) : (
              <>
                You moved {category} from <Person directory={directory} id={change.before} /> to{" "}
                <Person directory={directory} id={change.after} />.
              </>
            ),
        });
      } else if (change.after === viewer) {
        found.push({
          ...base,
          Icon: Users,
          tone: BLUE,
          body: (
            <>
              <Person directory={directory} id={change.delegator} /> handed you {category}
              {change.before !== null && (
                <>
                  , moving it from <Person directory={directory} id={change.before} />
                </>
              )}
              .
            </>
          ),
        });
      } else {
        found.push({
          ...base,
          Icon: Minus,
          tone: GREY,
          body: (
            <>
              <Person directory={directory} id={change.delegator} /> moved {category} away from
              you.
            </>
          ),
        });
      }
    });

    profile.history.forEach((entry) => {
      const question = findQuestion(scenario, entry.question_id);
      const cast = entry.choice === null ? null : choiceLabel(question, entry.choice);
      const others =
        entry.votes_for_others > 0
          ? ` You also decided ${entry.votes_for_others} other ${entry.votes_for_others === 1 ? "vote" : "votes"}.`
          : "";
      const base = {
        key: `vote-${entry.question_id}`,
        kind: "vote" as const,
        order: -entry.closed_days_ago * 2 + 1,
        when: ago(entry.closed_days_ago),
        href: `/liquid/votes/${entry.question_id}`,
      };
      if (entry.how === "delegated") {
        found.push({
          ...base,
          Icon: CornerUpRight,
          tone: cast === null ? GREY : AMBER,
          body:
            cast === null ? (
              <>
                {personName(directory, entry.resolver)} held your vote on {entry.title} under “
                {entry.category}” and did not vote.
              </>
            ) : (
              <>
                {personName(directory, entry.resolver)} voted{" "}
                <span className="font-medium">{cast}</span> for you on {entry.title}, under “
                {entry.category}”.
              </>
            ),
        });
      } else if (entry.how === "voted") {
        found.push({
          ...base,
          Icon: Check,
          tone: VIOLET,
          body: entry.issued ? (
            <>
              You voted <span className="font-medium">{cast}</span> on {entry.title}.{others}
            </>
          ) : (
            <>
              You voted <span className="font-medium">{cast}</span> on {entry.title} for{" "}
              {entry.votes_for_others} other {entry.votes_for_others === 1 ? "person" : "people"};
              it was not issued to you.
            </>
          ),
        });
      } else {
        found.push({
          ...base,
          Icon: CircleSlash,
          tone: GREY,
          body: (
            <>
              You did not vote on {entry.title}
              {entry.votes_for_others > 0 &&
                `, so ${entry.votes_for_others} other ${entry.votes_for_others === 1 ? "vote was" : "votes were"} not cast either`}
              .
            </>
          ),
        });
      }
    });

    return found.sort((a, b) => b.order - a.order);
  }, [log, profile, scenario, directory, viewer]);

  const counts = {
    all: items.length,
    delegation: items.filter((item) => item.kind === "delegation").length,
    vote: items.filter((item) => item.kind === "vote").length,
  };
  const filters: { id: "all" | Kind; label: string }[] = [
    { id: "all", label: "All" },
    { id: "delegation", label: "Delegations" },
    { id: "vote", label: "Votes" },
  ];
  const shown = items.filter((item) => filter === "all" || item.kind === filter);

  return (
    <div className="max-w-3xl space-y-6">
      <header className="space-y-1">
        <p className="liquid-label">Your account · newest first</p>
        <h2 className="text-2xl font-semibold tracking-tight">Activity</h2>
        <p className="text-sm text-muted-foreground">
          Every change to your delegations, every category someone handed you, and every vote
          cast by you or for you.
        </p>
      </header>

      <div className="flex flex-wrap gap-1.5">
        {filters.map((entry) => (
          <button
            key={entry.id}
            type="button"
            aria-pressed={filter === entry.id}
            onClick={() => setFilter(entry.id)}
            className={cn(
              "rounded-full border px-2.5 py-1 text-xs transition-colors",
              filter === entry.id ? "border-foreground font-medium" : "hover:bg-accent"
            )}
          >
            {entry.label}{" "}
            <span className="tabular-nums text-muted-foreground">{counts[entry.id]}</span>
          </button>
        ))}
      </div>

      <ol className="relative space-y-1 before:absolute before:bottom-3 before:left-[0.9rem] before:top-3 before:w-px before:bg-border">
        {shown.map((item) => (
          <li key={item.key} className="relative flex gap-3 py-1.5">
            <span
              className={cn(
                "relative z-[1] mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border bg-background",
                item.tone
              )}
              aria-hidden="true"
            >
              <item.Icon className="h-3.5 w-3.5" />
            </span>
            <div className="min-w-0 flex-1 text-sm leading-relaxed">
              <p>{item.body}</p>
              <p className="font-mono text-xs text-muted-foreground">
                {item.when}
                {item.href && (
                  <>
                    {" · "}
                    <Link href={item.href} className="underline-offset-4 hover:underline">
                      Open the vote
                    </Link>
                  </>
                )}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
