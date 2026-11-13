"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { traceMeasureAction } from "@/actions/delegation-actions";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  MAX_SUMMARY_LENGTH,
  MAX_TITLE_LENGTH,
} from "@/lib/validations/delegation-schemas";
import type { MeasureTrace } from "@/types/delegation";
import { useAccount } from "./account-provider";
import { percent, personName, profileHref } from "./people";

type Draft = { title: string; summary: string; jurisdiction: string };

/** Measures that each show one thing the routing rule does. */
const CASES = [
  { id: "q10", label: "A narrow category beats a broad one" },
  { id: "q25", label: "Two subjects at once" },
  { id: "q60", label: "A site choice reads as land use" },
  { id: "q66", label: "About nothing anyone delegated" },
];

const KEPT: Record<MeasureTrace["routing"]["kept"][number]["reason"], string> = {
  direct_vote: "voted themselves",
  no_delegations: "have handed nothing over",
  none_available: "hold no category that covers it",
  router_unavailable: "hold a category with no judgment for it",
  loop: "are on a loop, where everyone keeps their own decision",
};

const SOURCE: Record<MeasureTrace["source"], string> = {
  recorded: "Recorded judgments",
  fetched: "Judged just now",
  unavailable: "Not judged",
  limited: "Not judged: today's allowance is used up",
};

const BAR = "bg-indigo-600 dark:bg-indigo-400";
const BAR_SOFT = "bg-indigo-600/35 dark:bg-indigo-400/35";

/**
 * The routing rule, shown working. Pick a measure from the ballot papers or
 * draft one, and see the decision model's score for every category, where
 * each voter's vote goes as a result, and what moving the threshold does.
 * It reads the same network the account above is using, the viewer's own
 * delegations included.
 */
export function RoutingTracer() {
  const { scenario, directory, delegations, ready } = useAccount();
  const [mode, setMode] = useState<"ballot" | "draft">("ballot");
  const [questionId, setQuestionId] = useState("q10");
  const [draft, setDraft] = useState<Draft>({
    title: "",
    summary: "",
    jurisdiction: scenario.jurisdictions[0]?.id ?? "city",
  });
  const [submitted, setSubmitted] = useState<Draft | null>(null);
  const [threshold, setThreshold] = useState(scenario.threshold);
  const [trace, setTrace] = useState<MeasureTrace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [allScores, setAllScores] = useState(false);

  const sent = useMemo(
    () => delegations.map(({ category, delegate }) => ({ category, delegate })),
    [delegations]
  );
  const subject = mode === "ballot" ? { question_id: questionId } : submitted;
  const requestKey = JSON.stringify({ subject, threshold, sent });

  useEffect(() => {
    if (!ready || subject === null) return;
    let stale = false;
    setLoading(true);
    // A short wait, so dragging the threshold does not ask for every step.
    const timer = window.setTimeout(() => {
      void traceMeasureAction({ ...subject, viewer_delegations: sent, threshold }).then(
        (result) => {
          if (stale) return;
          setLoading(false);
          if (result.isSuccess && result.data) {
            setTrace(result.data);
            setError(null);
          } else {
            setError(result.message);
          }
        }
      );
    }, 180);
    return () => {
      stale = true;
      window.clearTimeout(timer);
    };
    // requestKey stands in for subject, threshold and sent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, requestKey]);

  const draftReady = draft.title.trim().length >= 3 && draft.summary.trim().length >= 10;
  const place = (id: string) => directory.jurisdictions.get(id) ?? id;

  return (
    <section className="mt-16 border-t pt-10" aria-labelledby="tracer-heading">
      <header className="max-w-3xl space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-700 dark:text-indigo-300">
          Under the hood
        </p>
        <h2 id="tracer-heading" className="text-2xl font-semibold tracking-tight">
          Trace a measure through the network
        </h2>
        <p className="leading-relaxed text-muted-foreground">
          Nobody sorts measures into topics. For each measure, a decision model ({scenario.model})
          answers one yes/no question per category people have written: is this measure
          primarily about it? Code does the rest. Each voter&apos;s vote follows their own
          best-matching category above a threshold, a narrower category overrules the broader
          one it sits inside, and a vote nobody&apos;s category covers stays where it is. This
          panel uses the same network as the account above, your delegations included.
        </p>
      </header>

      <div className="mt-8 grid gap-8 lg:grid-cols-[19rem_minmax(0,1fr)]">
        <div className="space-y-5">
          <div role="tablist" aria-label="What to trace" className="inline-flex rounded-lg border p-1">
            {(
              [
                ["ballot", "On the ballot"],
                ["draft", "Write your own"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={mode === id}
                onClick={() => setMode(id)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm transition-colors",
                  mode === id
                    ? "bg-foreground font-medium text-background"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {label}
              </button>
            ))}
          </div>

          {mode === "ballot" ? (
            <div className="space-y-4">
              <label className="block space-y-1.5 text-sm">
                <span className="font-medium">Measure</span>
                <select
                  value={questionId}
                  onChange={(event) => setQuestionId(event.target.value)}
                  className="w-full rounded-md border bg-background px-2 py-2 text-sm"
                >
                  {[...scenario.ballot_papers].reverse().map((paper) => (
                    <optgroup
                      key={paper.id}
                      label={`${paper.title} (${paper.status === "open" ? "open" : "closed"})`}
                    >
                      {paper.questions.map((question) => (
                        <option key={question.id} value={question.id}>
                          {question.title}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>
              <div className="space-y-1.5">
                <p className="text-sm font-medium">Cases worth a look</p>
                <ul className="space-y-1">
                  {CASES.map((entry) => (
                    <li key={entry.id}>
                      <button
                        type="button"
                        aria-pressed={questionId === entry.id}
                        onClick={() => setQuestionId(entry.id)}
                        className={cn(
                          "w-full rounded-md border px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-accent",
                          questionId === entry.id && "border-foreground font-medium"
                        )}
                      >
                        {entry.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (draftReady) {
                  setSubmitted({
                    title: draft.title.trim(),
                    summary: draft.summary.trim(),
                    jurisdiction: draft.jurisdiction,
                  });
                }
              }}
            >
              <label className="block space-y-1.5 text-sm">
                <span className="font-medium">Title</span>
                <input
                  value={draft.title}
                  maxLength={MAX_TITLE_LENGTH}
                  onChange={(event) => setDraft({ ...draft, title: event.target.value })}
                  placeholder="Dog park at Cannery Yard"
                  className="w-full rounded-md border bg-background px-2.5 py-2 text-sm"
                />
              </label>
              <label className="block space-y-1.5 text-sm">
                <span className="font-medium">What it would do, in a sentence</span>
                <textarea
                  value={draft.summary}
                  maxLength={MAX_SUMMARY_LENGTH}
                  rows={3}
                  onChange={(event) => setDraft({ ...draft, summary: event.target.value })}
                  placeholder="Turns two acres of the Cannery Yard into a fenced off-leash dog park."
                  className="w-full rounded-md border bg-background px-2.5 py-2 text-sm"
                />
              </label>
              <label className="block space-y-1.5 text-sm">
                <span className="font-medium">Issued to</span>
                <select
                  value={draft.jurisdiction}
                  onChange={(event) => setDraft({ ...draft, jurisdiction: event.target.value })}
                  className="w-full rounded-md border bg-background px-2 py-2 text-sm"
                >
                  {scenario.jurisdictions.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {entry.name}
                    </option>
                  ))}
                </select>
              </label>
              <Button type="submit" size="sm" disabled={!draftReady}>
                Trace this measure
              </Button>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {scenario.live_judgments
                  ? "A new wording is sent to the decision model once and recorded; a draft is a yes/no measure and never goes on a ballot."
                  : "This server is not asking the decision model about new wording, so a draft comes back unjudged and nobody delegates it. Measures on the ballot are recorded and always trace."}
              </p>
            </form>
          )}

          <label className="block space-y-1.5 border-t pt-4 text-sm">
            <span className="flex items-baseline justify-between">
              <span className="font-medium">Threshold</span>
              <span className="font-mono tabular-nums">{threshold.toFixed(2)}</span>
            </span>
            <input
              type="range"
              min={0.5}
              max={0.95}
              step={0.05}
              value={threshold}
              onChange={(event) => setThreshold(Number(event.target.value))}
              className="w-full accent-indigo-600"
            />
            <span className="block text-xs leading-relaxed text-muted-foreground">
              A category must score at least this for a vote to follow it. The demo runs at{" "}
              {scenario.threshold.toFixed(2)}.{" "}
              {threshold !== scenario.threshold && (
                <button
                  type="button"
                  className="underline underline-offset-2"
                  onClick={() => setThreshold(scenario.threshold)}
                >
                  Put it back
                </button>
              )}
            </span>
          </label>
        </div>

        <div className={cn("min-w-0 space-y-8", loading && "opacity-60 transition-opacity")}>
          {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
          {!trace && !error && (
            <p className="text-sm text-muted-foreground">
              {mode === "draft" && submitted === null
                ? "Write a measure and trace it."
                : "Tracing…"}
            </p>
          )}
          {trace && (
            <>
              <div className="space-y-1">
                <p className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="rounded-full border px-2 py-0.5 text-muted-foreground">
                    {SOURCE[trace.source]}
                  </span>
                  <span className="text-muted-foreground">
                    Issued to {trace.voters} residents of {place(trace.question.jurisdiction)}
                  </span>
                </p>
                <h3 className="text-lg font-semibold">{trace.question.title}</h3>
                <p className="text-sm text-muted-foreground">{trace.question.summary}</p>
                {trace.failures.length > 0 && (
                  <p className="text-sm text-red-700 dark:text-red-400">
                    The decision model could not be reached.
                  </p>
                )}
              </div>

              <Scores trace={trace} all={allScores} onToggle={() => setAllScores((v) => !v)} />
              <Routing trace={trace} />
              <Sweep trace={trace} />
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function Step({ number, title, children }: { number: number; title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h4 className="flex items-baseline gap-2 text-sm font-semibold">
        <span className="font-mono text-xs text-muted-foreground">{number}</span>
        {title}
      </h4>
      {children}
    </section>
  );
}

/** Every category's score against the threshold, highest first. */
function Scores({ trace, all, onToggle }: { trace: MeasureTrace; all: boolean; onToggle: () => void }) {
  const threshold = trace.routing.threshold;
  const cleared = trace.scores.filter(
    (score) => score.probability !== null && score.probability >= threshold
  ).length;
  const shown = all ? trace.scores : trace.scores.slice(0, Math.max(6, cleared + 2));
  return (
    <Step number={1} title="The decision model scores every category">
      {!trace.judged ? (
        <p className="text-sm text-muted-foreground">
          There are no judgments for this wording, so the rule has nothing to route on. It
          fails closed: every vote stays with its voter.
        </p>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            {cleared === 0
              ? `No category reaches ${threshold.toFixed(2)}.`
              : `${cleared} of ${trace.scores.length} ${cleared === 1 ? "category reaches" : "categories reach"} ${threshold.toFixed(2)}.`}{" "}
            A score only matters to the people who hold that category.
          </p>
          <ul className="space-y-1.5">
            {shown.map((score) => {
              const value = score.probability ?? 0;
              const over = score.probability !== null && value >= threshold;
              return (
                <li
                  key={score.category}
                  className="grid grid-cols-[minmax(0,1fr)_2.75rem] items-center gap-x-3 gap-y-0.5 text-sm sm:grid-cols-[minmax(0,15rem)_minmax(0,1fr)_2.75rem]"
                >
                  <span className="min-w-0">
                    <span className={cn("block truncate", over && "font-medium")}>
                      {score.text}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {score.holders} {score.holders === 1 ? "person holds" : "people hold"} it
                      {score.held_by_viewer && " · you do"}
                      {score.inside.length > 0 && " · narrow"}
                    </span>
                  </span>
                  <span className="relative order-last col-span-2 h-2 rounded-full bg-muted sm:order-none sm:col-span-1">
                    <span
                      className={cn("block h-full rounded-full", over ? BAR : BAR_SOFT)}
                      style={{ width: percent(value, 1) }}
                    />
                    <span
                      className="absolute -top-1 h-4 w-px bg-foreground"
                      style={{ left: percent(threshold, 1) }}
                      aria-hidden="true"
                    />
                  </span>
                  <span className="text-right font-mono tabular-nums">
                    {score.probability === null ? "–" : value.toFixed(2)}
                  </span>
                </li>
              );
            })}
          </ul>
          {trace.scores.length > shown.length || all ? (
            <button type="button" className="text-sm underline underline-offset-4" onClick={onToggle}>
              {all ? "Show fewer" : `Show all ${trace.scores.length} categories`}
            </button>
          ) : null}
        </>
      )}
    </Step>
  );
}

/** Where the votes left, who ends up deciding them, and why the rest stayed. */
function Routing({ trace }: { trace: MeasureTrace }) {
  const { directory } = useAccount();
  const { routing, voters } = trace;
  const sent = routing.by_category.reduce((sum, entry) => sum + entry.votes, 0);
  const mostSent = Math.max(1, ...routing.by_category.map((entry) => entry.votes));
  const mostHeld = Math.max(1, ...routing.resolvers.map((entry) => entry.votes));
  const longest = routing.metrics.chain_lengths.reduce((most, entry) => Math.max(most, entry.hops), 0);
  const viewer = routing.viewer;

  return (
    <Step number={2} title="Each voter's own categories decide where their vote goes">
      <p className="text-sm text-muted-foreground">
        Of {voters} votes, {sent} leave their voter and {voters - sent} stay.
        {sent > 0 &&
          ` The longest chain is ${longest} ${longest === 1 ? "hop" : "hops"}, and the most any one person decides is ${percent(routing.metrics.largest_share, 1)}.`}
        {routing.metrics.loops.length > 0 &&
          ` ${routing.metrics.loops.length} ${routing.metrics.loops.length === 1 ? "loop was" : "loops were"} found and broken.`}
      </p>

      {sent > 0 && (
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Votes leave under
            </p>
            <ul className="space-y-1.5">
              {routing.by_category.map((entry) => (
                <BarRow
                  key={entry.category}
                  label={entry.category}
                  value={entry.votes}
                  share={entry.votes / mostSent}
                />
              ))}
            </ul>
          </div>
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              And are decided by
            </p>
            <ul className="space-y-1.5">
              {routing.resolvers.map((entry) => (
                <BarRow
                  key={entry.person}
                  label={personName(directory, entry.person)}
                  href={profileHref(directory, entry.person)}
                  value={entry.votes}
                  share={entry.votes / mostHeld}
                />
              ))}
            </ul>
          </div>
        </div>
      )}

      {routing.flows.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">
            The largest flows, category to decider
          </summary>
          <table className="mt-2 w-full text-left text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th className="py-1 pr-3 font-medium">Left under</th>
                <th className="py-1 pr-3 font-medium">Decided by</th>
                <th className="py-1 text-right font-medium">Votes</th>
              </tr>
            </thead>
            <tbody>
              {routing.flows.map((flow) => (
                <tr key={`${flow.category}-${flow.resolver}`} className="border-t">
                  <td className="py-1 pr-3">{flow.category}</td>
                  <td className="py-1 pr-3">{personName(directory, flow.resolver)}</td>
                  <td className="py-1 text-right font-mono tabular-nums">{flow.votes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {routing.kept.length > 0 && (
        <p className="text-sm text-muted-foreground">
          Votes that stay:{" "}
          {routing.kept.map((entry) => `${entry.votes} ${KEPT[entry.reason]}`).join("; ")}.
        </p>
      )}

      <p className="rounded-md border px-3 py-2 text-sm">
        <span className="font-medium">Your vote: </span>
        {viewer === null
          ? "this measure is not issued to your district."
          : viewer.outcome === "delegated"
            ? `leaves under “${viewer.category}”${
                viewer.set_aside.length > 0
                  ? `, which overrules “${viewer.set_aside.join("”, “")}”`
                  : ""
              }, and ${
                viewer.resolver === directory.viewer
                  ? "the chain comes back to you"
                  : `${personName(directory, viewer.resolver)} decides it${
                      viewer.chain.length > 2
                        ? ` after ${viewer.chain.length - 2} more ${viewer.chain.length === 3 ? "hop" : "hops"}`
                        : ""
                    }`
              }.`
            : viewer.outcome === "no_delegations"
              ? "you have handed nothing over, so it stays with you."
              : viewer.outcome === "none_available"
                ? "none of your categories covers this, so it stays with you."
                : "one of your categories has no judgment for this, so it stays with you."}
      </p>
    </Step>
  );
}

function BarRow({
  label,
  value,
  share,
  href,
}: {
  label: string;
  value: number;
  share: number;
  href?: string;
}) {
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_2rem] items-center gap-x-3 gap-y-0.5 text-sm">
      {href ? (
        <Link href={href} className="truncate underline-offset-4 hover:underline">
          {label}
        </Link>
      ) : (
        <span className="truncate">{label}</span>
      )}
      <span className="text-right font-mono tabular-nums">{value}</span>
      <span className="col-span-2 h-1.5 rounded-full bg-muted" aria-hidden="true">
        <span className={cn("block h-full rounded-full", BAR)} style={{ width: `${share * 100}%` }} />
      </span>
    </li>
  );
}

const CHART = { width: 520, height: 170, left: 40, right: 12, top: 12, bottom: 28 };

/** The share of votes delegated at each threshold, with the current one marked. */
function Sweep({ trace }: { trace: MeasureTrace }) {
  const { directory } = useAccount();
  const { sweep, routing } = trace;
  const plotWidth = CHART.width - CHART.left - CHART.right;
  const plotHeight = CHART.height - CHART.top - CHART.bottom;
  const top = Math.max(0.1, Math.ceil(Math.max(...sweep.map((row) => row.delegated_share)) * 10) / 10);
  const first = sweep[0].threshold;
  const last = sweep[sweep.length - 1].threshold;
  const x = (threshold: number) =>
    CHART.left + ((threshold - first) / (last - first)) * plotWidth;
  const y = (share: number) => CHART.top + plotHeight - (share / top) * plotHeight;
  const current = sweep.reduce((best, row) =>
    Math.abs(row.threshold - routing.threshold) < Math.abs(best.threshold - routing.threshold)
      ? row
      : best
  );
  const low = sweep[0];
  const high = sweep[sweep.length - 1];

  return (
    <Step number={3} title="Moving the threshold trades coverage for caution">
      <p className="text-sm text-muted-foreground">
        At {low.threshold.toFixed(2)}, {percent(low.delegated_share)} of votes are decided by
        someone else; at {high.threshold.toFixed(2)}, {percent(high.delegated_share)}. A lower
        threshold sends more votes on, including some to a category the measure is only partly
        about.
      </p>
      <svg
        viewBox={`0 0 ${CHART.width} ${CHART.height}`}
        className="w-full max-w-xl"
        role="img"
        aria-label={`Share of votes decided by someone else at each threshold from ${first.toFixed(2)} to ${last.toFixed(2)}; ${percent(current.delegated_share)} at ${current.threshold.toFixed(2)}`}
      >
        {[0, top / 2, top].map((tick) => (
          <g key={tick}>
            <line
              x1={CHART.left}
              x2={CHART.width - CHART.right}
              y1={y(tick)}
              y2={y(tick)}
              className="stroke-border"
              strokeWidth="1"
            />
            <text
              x={CHART.left - 6}
              y={y(tick) + 4}
              textAnchor="end"
              className="fill-muted-foreground text-[11px]"
            >
              {percent(tick)}
            </text>
          </g>
        ))}
        {sweep
          .filter((_, index) => index % 2 === 0 || index === sweep.length - 1)
          .map((row) => (
            <text
              key={row.threshold}
              x={x(row.threshold)}
              y={CHART.height - 8}
              textAnchor="middle"
              className="fill-muted-foreground text-[11px]"
            >
              {row.threshold.toFixed(2)}
            </text>
          ))}
        <line
          x1={x(current.threshold)}
          x2={x(current.threshold)}
          y1={CHART.top}
          y2={CHART.top + plotHeight}
          className="stroke-foreground"
          strokeWidth="1"
          strokeDasharray="3 3"
        />
        <polyline
          points={sweep.map((row) => `${x(row.threshold)},${y(row.delegated_share)}`).join(" ")}
          fill="none"
          className="stroke-indigo-600 dark:stroke-indigo-400"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        {sweep.map((row) => (
          <circle
            key={row.threshold}
            cx={x(row.threshold)}
            cy={y(row.delegated_share)}
            r={row.threshold === current.threshold ? 5 : 3}
            className="fill-indigo-600 stroke-background dark:fill-indigo-400"
            strokeWidth="2"
          >
            <title>
              {`${row.threshold.toFixed(2)}: ${percent(row.delegated_share)} decided by someone else`}
            </title>
          </circle>
        ))}
      </svg>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">View as a table</summary>
        <table className="mt-2 w-full max-w-xl text-left text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th className="py-1 pr-3 font-medium">Threshold</th>
              <th className="py-1 pr-3 text-right font-medium">Decided by someone else</th>
              <th className="py-1 pr-3 text-right font-medium">Largest share</th>
              <th className="py-1 font-medium">Held by</th>
            </tr>
          </thead>
          <tbody>
            {sweep.map((row) => (
              <tr
                key={row.threshold}
                className={cn("border-t", row.threshold === current.threshold && "font-medium")}
              >
                <td className="py-1 pr-3 font-mono tabular-nums">{row.threshold.toFixed(2)}</td>
                <td className="py-1 pr-3 text-right font-mono tabular-nums">
                  {percent(row.delegated_share)}
                </td>
                <td className="py-1 pr-3 text-right font-mono tabular-nums">
                  {percent(row.largest_share, 1)}
                </td>
                <td className="py-1">
                  {row.largest_resolver && row.largest_share > 1 / trace.voters
                    ? personName(directory, row.largest_resolver)
                    : "–"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </Step>
  );
}
