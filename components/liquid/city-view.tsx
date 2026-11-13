"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import type { CityQuestion, CityResults } from "@/types/delegation";
import { useAccount } from "./account-provider";
import { AppLink as Link } from "./app-link";
import { findQuestion, outcomeLabel } from "./ballots";
import { CityMap } from "./city-map";
import { ago, percent, personName, profileHref } from "./people";
import { PersonAvatar } from "./person-bits";
import { StatCard, StatStrip } from "./stat-card";
import { TrendChart, type TrendPoint } from "./trend-chart";

type StatKey = "turnout" | "direct" | "delegated" | "largest" | "changed";

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/**
 * The whole city's closed votes: how many people's ballots counted with
 * delegation and without it, how much of the vote was handed on and to how
 * few, which results delegation changed, and who decided the most.
 */
export function CityView({ city }: { city: CityResults }) {
  const { scenario, directory } = useAccount();
  const [stat, setStat] = useState<StatKey>("turnout");
  const [filter, setFilter] = useState<string>("all");
  const { totals, papers } = city;

  const series = useMemo(() => {
    const points = (value: (paper: CityResults["papers"][number]) => number): TrendPoint[] =>
      papers.map((paper) => ({
        daysAgo: paper.closed_days_ago,
        value: value(paper),
        label: `${paper.title}, ${ago(paper.closed_days_ago)}`,
      }));
    const share = (value: number) => percent(value);
    return {
      turnout: {
        title: "Ballots that counted, with delegation",
        points: points((paper) => paper.turnout_delegated),
        format: share,
      },
      direct: {
        title: "People who voted themselves",
        points: points((paper) => paper.turnout_direct),
        format: share,
      },
      delegated: {
        title: "Votes decided by someone else",
        points: points((paper) => paper.delegated_share),
        format: share,
      },
      largest: {
        title: "Largest share of one question held by one person",
        points: points((paper) => paper.largest_share),
        format: (value: number) => percent(value, 1),
      },
      changed: {
        title: "Results delegation changed",
        points: points((paper) => paper.changed),
        format: (value: number) => String(Math.round(value)),
      },
    } satisfies Record<StatKey, { title: string; points: TrendPoint[]; format: (v: number) => string }>;
  }, [papers]);

  const cards: { key: StatKey; label: string; hint: string; value: string; badge?: string }[] = [
    {
      key: "turnout",
      label: "Turnout",
      hint: "Share of issued ballots that counted with delegation: the voter, or whoever held their vote, voted",
      value: percent(totals.turnout_delegated),
      badge: `+${Math.round((totals.turnout_delegated - totals.turnout_direct) * 100)} pts`,
    },
    {
      key: "direct",
      label: "Voted Directly",
      hint: "Share of issued ballots their own voter filled in; the turnout there would be without delegation",
      value: percent(totals.turnout_direct),
    },
    {
      key: "delegated",
      label: "Delegated",
      hint: "Share of votes decided by someone other than the voter",
      value: percent(totals.delegated_share),
    },
    {
      key: "largest",
      label: "Largest Share",
      hint: totals.largest_resolver
        ? `The most of one question's votes one person decided: ${personName(directory, totals.largest_resolver)}`
        : "The most of one question's votes one person decided",
      value: percent(totals.largest_share, 1),
    },
    {
      key: "changed",
      label: "Results Changed",
      hint: `Of ${totals.questions} closed questions, the ones where delegation gave a different result than the people who voted themselves`,
      value: String(totals.changed),
    },
  ];

  const places = useMemo(
    () => [...new Set(city.questions.map((row) => row.jurisdiction))],
    [city.questions]
  );
  const filters = [
    { id: "all", label: "All", count: city.questions.length },
    { id: "changed", label: "Changed by delegation", count: totals.changed },
    ...places.map((place) => ({
      id: place,
      label: directory.jurisdictions.get(place) ?? place,
      count: city.questions.filter((row) => row.jurisdiction === place).length,
    })),
  ];
  const rows = city.questions.filter((row) =>
    filter === "all" ? true : filter === "changed" ? row.winner_changed : row.jurisdiction === filter
  );
  const most = Math.max(1, ...city.deciders.map((entry) => entry.votes_decided));

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <p className="liquid-label">{scenario.city} · every closed vote</p>
        <h2 className="text-2xl font-semibold tracking-tight">City Results</h2>
        <p className="max-w-2xl text-sm text-muted-foreground">
          {totals.questions} questions have closed across {papers.length} ballot papers. Open
          votes are not counted here until they close.
        </p>
      </header>

      <section className="space-y-4">
        <StatStrip columns="grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
          {cards.map((card) => (
            <StatCard
              key={card.key}
              label={card.label}
              hint={card.hint}
              value={card.value}
              badge={card.badge}
              trend={series[card.key].points.map((point) => point.value)}
              selected={stat === card.key}
              onSelect={() => setStat(card.key)}
            />
          ))}
        </StatStrip>
        <div className="liquid-panel p-4">
          <TrendChart
            title={series[stat].title}
            points={series[stat].points}
            format={series[stat].format}
          />
        </div>
      </section>

      <CityMap city={city} />

      <section className="space-y-3">
        <h3 className="liquid-label">Who decided the most for others</h3>
        <ol className="liquid-panel divide-y">
          {city.deciders.map((entry) => (
            <li key={entry.person}>
              <Link
                href={profileHref(directory, entry.person)}
                className="grid grid-cols-[minmax(0,13rem)_minmax(0,1fr)_auto] items-center gap-3 px-3 py-2 text-sm transition-colors hover:bg-accent"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <PersonAvatar directory={directory} id={entry.person} size="sm" />
                  <span className="truncate font-medium">
                    {personName(directory, entry.person)}
                  </span>
                </span>
                <span className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                  <span
                    className="block h-full rounded-full bg-primary"
                    style={{ width: `${(entry.votes_decided / most) * 100}%` }}
                  />
                </span>
                <span className="text-right font-mono text-xs tabular-nums text-muted-foreground">
                  <span className="text-sm text-foreground">{entry.votes_decided}</span> votes ·{" "}
                  {entry.questions} questions · up to {percent(entry.largest_share, 1)}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <section className="space-y-3">
        <h3 className="liquid-label">Closed questions</h3>
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
              <span className="tabular-nums text-muted-foreground">{entry.count}</span>
            </button>
          ))}
        </div>
        <ol className="space-y-2">
          {rows.map((row) => (
            <QuestionRow key={row.question_id} row={row} />
          ))}
        </ol>
      </section>
    </div>
  );
}

function QuestionRow({ row }: { row: CityQuestion }) {
  const { scenario, directory } = useAccount();
  const question = findQuestion(scenario, row.question_id);
  const figures = [
    { label: "Turnout", value: percent(row.cast_delegated / row.voters) },
    { label: "Voted directly", value: percent(row.cast_direct / row.voters) },
    { label: "Delegated", value: percent(row.delegated_share) },
    {
      label: row.largest_resolver
        ? `Most held: ${personName(directory, row.largest_resolver)}`
        : "Most held by one person",
      value: percent(row.largest_share, 1),
    },
  ];
  return (
    <li>
      <Link
        href={`/liquid/votes/${row.question_id}`}
        className={cn(
          "liquid-panel block border-l-2 p-3 transition-colors hover:border-primary hover:bg-accent",
          row.winner_changed ? "border-l-amber-400" : "border-l-transparent"
        )}
      >
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
          <p className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{row.title}</span>
            <span className="font-mono text-xs text-muted-foreground">
              {row.label} · {row.kind}
            </span>
          </p>
          <span className="font-mono text-xs text-muted-foreground">
            {ago(row.closed_days_ago)}
          </span>
        </div>
        <p className="mt-1 text-sm">
          {capitalize(outcomeLabel(question, row.winners))}
          {row.support !== null && ` with ${percent(row.support)} yes`}
          {row.winner_changed && (
            <span className="text-amber-300">
              {" "}
              · without delegation: {outcomeLabel(question, row.direct_winners)}
            </span>
          )}
          <span className="text-muted-foreground">
            {" "}
            · {row.paper_title} · {directory.jurisdictions.get(row.jurisdiction) ?? row.jurisdiction}
          </span>
        </p>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
          {figures.map((figure) => (
            <div key={figure.label} className="flex items-baseline justify-between gap-2 sm:block">
              <dt className="truncate text-muted-foreground">{figure.label}</dt>
              <dd className="font-mono text-sm tabular-nums">{figure.value}</dd>
            </div>
          ))}
        </dl>
      </Link>
    </li>
  );
}
