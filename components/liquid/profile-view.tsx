"use client";

import { useEffect, useMemo, useState } from "react";
import { AppLink as Link } from "./app-link";
import { ArrowLeft, Maximize2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { HistoryEntry, PersonProfile } from "@/types/delegation";
import { useAccount } from "./account-provider";
import { WindowOverlay } from "./app-window";
import { choiceLabel, findQuestion, outcomeLabel } from "./ballots";

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);
import { trustedWith } from "./categories";
import { ChangesList } from "./changes-list";
import { HubGraph } from "./hub-graph";
import {
  ago,
  percent,
  personHandle,
  personHome,
  personName,
  profileHref,
} from "./people";
import { PersonAvatar } from "./person-bits";
import { StatCard, StatStrip } from "./stat-card";
import { TrendChart, type TrendPoint } from "./trend-chart";

type Tab = "stats" | "graph" | "history" | "changes";
const TABS: { id: Tab; label: string }[] = [
  { id: "stats", label: "Stats" },
  { id: "graph", label: "Graph" },
  { id: "history", label: "Voting history" },
  { id: "changes", label: "Changes" },
];

type Filter = "all" | HistoryEntry["how"];

const HOW: Record<HistoryEntry["how"], { tag: string; tone: string }> = {
  voted: {
    tag: "Voted",
    tone: "border-primary/50 bg-primary/15 text-violet-200",
  },
  delegated: {
    tag: "Delegated",
    tone: "border-amber-400/60 bg-amber-400/10 text-amber-200",
  },
  abstained: {
    tag: "Did not vote",
    tone: "border-border bg-muted text-muted-foreground",
  },
};

/**
 * Anyone's profile: who they are, then stats, their delegation graph and
 * their voting history in a panel whose tabs can each be opened full screen.
 */
export function ProfileView({ profile }: { profile: PersonProfile }) {
  const { directory, delegations } = useAccount();
  const [tab, setTab] = useState<Tab>("stats");
  const [full, setFull] = useState(false);
  const { person } = profile;
  const isViewer = person.id === directory.viewer;

  useEffect(() => {
    if (!full) return;
    const close = (event: KeyboardEvent) =>
      event.key === "Escape" && setFull(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [full]);

  // The viewer's graph is the one in their browser, which they may have edited.
  const edges = isViewer
    ? delegations.map(({ category, delegate }) => ({ category, delegate }))
    : profile.delegations;
  const known = person.well_known_for
    .map((id) => directory.categoryText.get(id))
    .filter((text): text is string => text !== undefined);

  const tabs = (
    <div
      role="tablist"
      aria-label="Profile sections"
      className="flex flex-wrap gap-1"
    >
      {TABS.map((entry) => (
        <button
          key={entry.id}
          type="button"
          role="tab"
          aria-selected={tab === entry.id}
          onClick={() => setTab(entry.id)}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm transition-colors",
            tab === entry.id
              ? "bg-primary font-medium text-primary-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-foreground",
          )}
        >
          {entry.label}
        </button>
      ))}
    </div>
  );

  const content = (
    <div role="tabpanel">
      {tab === "stats" && (
        <StatsTab
          profile={profile}
          handedOver={edges.length}
          isViewer={isViewer}
        />
      )}
      {tab === "graph" && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {isViewer
              ? "Who hands you a category, and what you hand over now. Edit it from the Hub."
              : `Who hands ${person.name} a category, and what they hand over. Select a node to open that person's profile.`}
          </p>
          <HubGraph
            directory={directory}
            owner={person.id}
            incoming={profile.received.map((entry) => ({
              person: entry.delegator,
              category: entry.category,
            }))}
            outgoing={edges}
          />
        </div>
      )}
      {tab === "history" && (
        <HistoryTab profile={profile} isViewer={isViewer} />
      )}
      {tab === "changes" && (
        <ChangesList profile={profile} isViewer={isViewer} />
      )}
    </div>
  );

  if (full) {
    return (
      <WindowOverlay>
        <div className="space-y-6 p-4 sm:p-6 lg:p-7">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button
              variant="ghost"
              size="sm"
              className="-ml-2"
              onClick={() => setFull(false)}
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              Back to profile
            </Button>
            <p className="flex items-center gap-2 text-sm">
              <PersonAvatar directory={directory} id={person.id} size="sm" />
              <span className="font-medium">{person.name}</span>
              <span className="text-muted-foreground">@{person.username}</span>
            </p>
          </div>
          {tabs}
          {content}
        </div>
      </WindowOverlay>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center gap-5">
        <PersonAvatar directory={directory} id={person.id} size="lg" />
        <div className="min-w-0 space-y-1">
          <h2 className="text-2xl font-semibold tracking-tight">
            {person.name}
          </h2>
          <p className="font-mono text-sm text-muted-foreground">
            @{person.username} · {personHome(directory, person.id)}
          </p>
          {known.length > 0 && (
            <p className="flex flex-wrap items-center gap-1.5 pt-1 text-xs">
              <span className="text-muted-foreground">Well known for</span>
              {known.map((text) => (
                <span key={text} className="rounded-full border px-2 py-0.5">
                  {text}
                </span>
              ))}
            </p>
          )}
        </div>
      </header>

      <section className="liquid-panel">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b p-3">
          {tabs}
          <Button variant="outline" size="sm" onClick={() => setFull(true)}>
            <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
            Full screen
          </Button>
        </div>
        <div
          className={cn(
            "p-4",
            tab !== "graph" && "max-h-[34rem] overflow-y-auto",
          )}
        >
          {content}
        </div>
      </section>

      <TrustedWith profile={profile} isViewer={isViewer} />
    </div>
  );
}

/** One stat's value at each closed ballot, oldest first. */
type Series = {
  title: string;
  format: (value: number) => string;
  points: TrendPoint[];
};

/**
 * A person's record ballot by ballot. Each closed ballot paper is one point
 * in time; a stat with no history behind it (who delegates to them, what
 * they hand over) has no series, because delegations are not dated yet.
 */
function seriesFrom(
  history: HistoryEntry[],
): Record<"rate" | "voted" | "others" | "share", Series> {
  const ballots = new Map<
    string,
    { label: string; daysAgo: number; entries: HistoryEntry[] }
  >();
  for (const entry of history) {
    const ballot = ballots.get(entry.ballot_paper) ?? {
      label: entry.paper_title,
      daysAgo: entry.closed_days_ago,
      entries: [],
    };
    ballot.entries.push(entry);
    ballots.set(entry.ballot_paper, ballot);
  }
  const ordered = [...ballots.values()].sort((a, b) => b.daysAgo - a.daysAgo);
  const points = (
    value: (entries: HistoryEntry[]) => number | null,
  ): TrendPoint[] =>
    ordered.flatMap(({ label, daysAgo, entries }) => {
      const result = value(entries);
      return result === null ? [] : [{ label, daysAgo, value: result }];
    });
  const whole = (value: number) => String(Math.round(value));
  return {
    rate: {
      title: "Delegation rate",
      format: (value) => percent(value),
      points: points((entries) => {
        const issued = entries.filter((entry) => entry.issued);
        if (issued.length === 0) return null;
        return (
          issued.filter((entry) => entry.how === "delegated").length /
          issued.length
        );
      }),
    },
    voted: {
      title: "Votes cast",
      format: whole,
      points: points(
        (entries) => entries.filter((entry) => entry.how === "voted").length,
      ),
    },
    others: {
      title: "Votes decided",
      format: whole,
      points: points((entries) =>
        entries.reduce((sum, entry) => sum + entry.votes_for_others, 0),
      ),
    },
    share: {
      title: "Peak share",
      format: (value) => percent(value, 1),
      points: points((entries) =>
        Math.max(...entries.map((entry) => entry.share)),
      ),
    },
  };
}

function StatsTab({
  profile,
  handedOver,
  isViewer,
}: {
  profile: PersonProfile;
  handedOver: number;
  isViewer: boolean;
}) {
  const { stats } = profile;
  const who = isViewer ? "you" : "they";
  const whom = isViewer ? "you" : "them";
  const series = useMemo(() => seriesFrom(profile.history), [profile.history]);
  type Key = keyof typeof series;

  const tiles: {
    key?: Key;
    label: string;
    hint: string;
    value: string;
    badge?: string;
  }[] = [
    {
      key: "rate",
      label: "Delegation Rate",
      hint: `Share of the votes issued to ${whom} that a delegate decided`,
      value:
        stats.delegation_rate === null ? "–" : percent(stats.delegation_rate),
    },
    {
      key: "voted",
      label: "Votes Cast",
      hint: `Number of votes ${who} cast personally`,
      value: String(
        profile.history.filter((entry) => entry.how === "voted").length,
      ),
      badge: stats.abstained > 0 ? `${stats.abstained} missed` : undefined,
    },
    {
      key: "others",
      label: "Votes Decided",
      hint: `Number of other people's votes ${who} decided`,
      value: String(stats.votes_decided_for_others),
    },
    {
      key: "share",
      label: "Peak Share",
      hint: `Largest share of one vote's ballots ${who} decided`,
      value: percent(stats.largest_share, 1),
    },
    {
      label: "Delegators",
      hint: `Number of people who hand ${whom} a category`,
      value: String(stats.delegators),
    },
    {
      label: "Delegates",
      hint: `Number of categories ${who} hand${isViewer ? "" : "s"} to someone else`,
      value: String(handedOver),
    },
  ];

  // Delegation rate first; for someone with no votes of their own, the first stat that has a history.
  const drawable = (key: Key) => series[key].points.length > 1;
  const fallback =
    (["rate", "voted", "others", "share"] as Key[]).find(drawable) ?? "rate";
  const [picked, setPicked] = useState<Key>("rate");
  const selected = drawable(picked) ? picked : fallback;

  return (
    <div className="space-y-6">
      <StatStrip columns="grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
        {tiles.map((tile) => {
          const key = tile.key;
          const hasTrend = key !== undefined && drawable(key);
          return (
            <StatCard
              key={tile.label}
              label={tile.label}
              hint={tile.hint}
              value={tile.value}
              badge={tile.badge}
              trend={
                hasTrend
                  ? series[key].points.map((point) => point.value)
                  : undefined
              }
              selected={hasTrend && key === selected}
              onSelect={hasTrend ? () => setPicked(key) : undefined}
            />
          );
        })}
      </StatStrip>

      <div className="liquid-panel p-4">
        <TrendChart
          title={series[selected].title}
          points={series[selected].points}
          format={series[selected].format}
        />
      </div>

      <p className="text-xs text-muted-foreground">
        Counted over the ballots that have closed. In this demo&apos;s world
        every vote is public, which is what lets you judge a delegate by their
        record.
      </p>
    </div>
  );
}

/** What people hand to this person, grouped by category. Always shown, whatever the tab. */
function TrustedWith({
  profile,
  isViewer,
}: {
  profile: PersonProfile;
  isViewer: boolean;
}) {
  const { directory } = useAccount();
  const { person } = profile;
  const subject = isViewer ? "you" : "them";
  // Wordings the decision model judged to be the same thing count together
  const received = useMemo(
    () => trustedWith(directory.groups, profile.received),
    [directory.groups, profile.received],
  );

  return (
    <section className="liquid-panel space-y-2 p-4">
      <h3 className="text-sm font-semibold">
        Trusted with{isViewer ? "" : ` · what people hand to ${person.name}`}
      </h3>
      {received.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nobody has handed {subject} a category.
        </p>
      ) : (
        <ul className="space-y-1.5 text-sm">
          {received.map(({ label, people, wordings }) => (
            <li key={label}>
              <span className="font-medium">{label}</span>
              <span className="text-muted-foreground">
                {" "}
                ·{" "}
                {people.length <= 3
                  ? people.map((id, index) => (
                      <span key={id}>
                        {index > 0 && ", "}
                        <Link
                          href={profileHref(directory, id)}
                          className="underline-offset-4 hover:underline"
                        >
                          {personName(directory, id)}
                        </Link>
                      </span>
                    ))
                  : `${people.length} people`}
              </span>
              {wordings.length > 1 && (
                <span className="block text-xs text-muted-foreground">
                  written as{" "}
                  {wordings.map((wording, index) => (
                    <span key={wording.text}>
                      {index > 0 && ", "}“{wording.text}” ({wording.count})
                    </span>
                  ))}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function HistoryTab({
  profile,
  isViewer,
}: {
  profile: PersonProfile;
  isViewer: boolean;
}) {
  const { scenario, directory } = useAccount();
  const [filter, setFilter] = useState<Filter>("all");
  const [newestFirst, setNewestFirst] = useState(true);
  const name = isViewer ? "You" : profile.person.name.split(" ")[0];

  const counts = useMemo(() => {
    const tally = {
      all: profile.history.length,
      voted: 0,
      delegated: 0,
      abstained: 0,
    };
    for (const entry of profile.history) tally[entry.how] += 1;
    return tally;
  }, [profile.history]);

  const rows = useMemo(() => {
    const kept = profile.history.filter(
      (entry) => filter === "all" || entry.how === filter,
    );
    return newestFirst ? kept : [...kept].reverse();
  }, [profile.history, filter, newestFirst]);

  const filters: { id: Filter; label: string }[] = [
    { id: "all", label: "All" },
    { id: "voted", label: "Voted" },
    { id: "delegated", label: "Delegated" },
    { id: "abstained", label: "Did not vote" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5">
          {filters
            .filter((entry) => entry.id === "all" || counts[entry.id] > 0)
            .map((entry) => (
              <button
                key={entry.id}
                type="button"
                aria-pressed={filter === entry.id}
                onClick={() => setFilter(entry.id)}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-xs transition-colors",
                  filter === entry.id
                    ? "border-foreground font-medium"
                    : "hover:bg-accent",
                )}
              >
                {entry.label}{" "}
                <span className="tabular-nums text-muted-foreground">
                  {counts[entry.id]}
                </span>
              </button>
            ))}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setNewestFirst((value) => !value)}
        >
          {newestFirst ? "Newest first" : "Oldest first"}
        </Button>
      </div>

      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No closed vote to show.</p>
      ) : (
        <ol className="space-y-2">
          {rows.map((entry) => {
            const how = HOW[entry.how];
            const choice =
              entry.choice === null
                ? null
                : choiceLabel(
                    findQuestion(scenario, entry.question_id),
                    entry.choice,
                  );
            return (
              <li key={entry.question_id}>
                <Link
                  href={`/liquid/votes/${entry.question_id}`}
                  className="liquid-panel block p-3 transition-colors hover:border-primary hover:bg-accent"
                >
                  <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
                    <p className="flex flex-wrap items-center gap-2">
                      <span
                        className={cn(
                          "rounded-full border px-2 py-0.5 text-xs font-medium",
                          how.tone,
                        )}
                      >
                        {how.tag}
                      </span>
                      <span className="font-medium">{entry.title}</span>
                      <span className="font-mono text-xs text-muted-foreground">
                        {entry.label}
                      </span>
                    </p>
                    <span className="font-mono text-xs text-muted-foreground">
                      {ago(entry.closed_days_ago)}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                    {entry.summary}
                  </p>
                  <p className="mt-2 text-sm">
                    {entry.how === "voted" && (
                      <>
                        {name} voted{" "}
                        <span className="font-medium">{choice}</span> personally
                        {entry.votes_for_others > 0 &&
                          `, and so decided ${entry.votes_for_others} other ${entry.votes_for_others === 1 ? "vote" : "votes"}`}
                        .
                      </>
                    )}
                    {entry.how === "delegated" && (
                      <>
                        Sent under “{entry.category}” to{" "}
                        <span className="font-medium">
                          {personName(directory, entry.resolver)}
                        </span>
                        {entry.chain.length > 2 &&
                          ` through ${entry.chain.length - 2} other${entry.chain.length === 3 ? "" : "s"}`}
                        , who voted{" "}
                        <span className="font-medium">
                          {choice ?? "nothing (abstained)"}
                        </span>
                        .
                      </>
                    )}
                    {entry.how === "abstained" && (
                      <>
                        The decision was {isViewer ? "yours" : "theirs"} and no
                        vote was cast before it closed
                        {entry.votes_for_others > 0 &&
                          `, so ${entry.votes_for_others} other ${entry.votes_for_others === 1 ? "vote" : "votes"} abstained too`}
                        .
                      </>
                    )}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {entry.paper_title} ·{" "}
                    {directory.jurisdictions.get(entry.jurisdiction) ??
                      entry.jurisdiction}
                    {!entry.issued &&
                      " · not issued to them; other people's votes reached them"}
                    {" · "}
                    {capitalize(
                      outcomeLabel(
                        findQuestion(scenario, entry.question_id),
                        entry.winners,
                      ),
                    )}
                  </p>
                </Link>
              </li>
            );
          })}
        </ol>
      )}
      <p className="text-xs text-muted-foreground">
        {personHandle(directory, profile.person.id)} · every closed vote issued
        to {isViewer ? "you" : "them"} or decided by {isViewer ? "you" : "them"}
        .
      </p>
    </div>
  );
}
