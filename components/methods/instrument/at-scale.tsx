"use client";

import { useState } from "react";

import { METHOD_META } from "@/lib/methods/instrument";
import { SHORT_LABELS, disagreement, percent, withInterval } from "@/lib/methods/simulation";
import { cn } from "@/lib/utils";
import type { SimulationGroup, SimulationSummary, VotingMethod } from "@/types/methods";

// Ink coverage for 3, 4 and 5 candidates: an ordinal ramp validated against
// both surfaces (light end 2.9:1 on light, 4.0:1 on dark)
const COUNT_INK: Record<number, number> = { 3: 45, 4: 72, 5: 100 };
// The efficiency axis, in percent
const AXIS = { min: 50, max: 100, ticks: [50, 60, 70, 80, 90, 100] };
// Disagreement at which a matrix cell reaches full shade
const FULL_SHADE = 0.6;

function ink(percentage: number): string {
  return `color-mix(in srgb, var(--mi-ink) ${percentage}%, var(--mi-surface))`;
}

interface Tip {
  x: number;
  y: number;
  lines: string[];
}

/** The candidate counts the study ran, as buttons. */
function CandidateCounts({
  counts,
  selected,
  onSelect,
}: {
  counts: number[];
  selected: number;
  onSelect: (k: number) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-xs text-mi-muted">Candidates</span>
      <div className="flex gap-1" role="group" aria-label="Candidates per election">
        {counts.map((k) => (
          <button
            key={k}
            type="button"
            aria-pressed={k === selected}
            onClick={() => onSelect(k)}
            className={cn(
              "min-h-11 min-w-11 rounded-[3px] border px-2.5 py-1 font-mi-mono text-sm sm:min-h-0 sm:min-w-9",
              k === selected
                ? "border-mi-ink bg-mi-ink text-mi-surface"
                : "border-mi-rule text-mi-ink hover:border-mi-ink"
            )}
          >
            {k}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Where the numbers come from, under each chart of the study. */
function StudyCaption({ summary }: { summary: SimulationSummary }) {
  const { config } = summary;
  return (
    <p className="break-words font-mi-mono text-xs leading-relaxed text-mi-muted">
      {summary.benchmark} · seed {config.seed} · {summary.interval} intervals · ties: seeded
      tiebreak (seed {config.tiebreak_seed}), or for instant runoff, candidates tied for last
      eliminated together · source {summary.source_sha256.slice(0, 12)}…
    </p>
  );
}

/**
 * How often two methods disagree, over the seeded spatial elections of
 * eval/benchmarks/methods_simulation_v1, with the most-disagreeing pair read
 * out as an example of how to read a cell.
 */
export function DisagreementStep({ summary }: { summary: SimulationSummary }) {
  const counts = summary.by_candidates.map((g) => g.candidates);
  const [selected, setSelected] = useState(counts[counts.length - 1]);
  const group = summary.by_candidates.find((g) => g.candidates === selected) ?? summary.by_candidates[0];
  const most = group.disagreement.reduce((a, b) => ((b.rate ?? 0) > (a.rate ?? 0) ? b : a));

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <DisagreementMatrix group={group} methods={summary.methods} highlight={[most.a, most.b]} />
      <div className="min-w-0 space-y-3 text-sm leading-relaxed text-mi-ink-2">
        <CandidateCounts counts={counts} selected={selected} onSelect={setSelected} />
        <p>
          <span className="font-medium text-mi-ink">Reading a cell.</span> The outlined cell says{" "}
          {METHOD_META[most.a].label.toLowerCase()} and {METHOD_META[most.b].label.toLowerCase()}{" "}
          elect different winners in{" "}
          <span className="font-mi-mono text-mi-ink">{percent(most, 0)}</span> of these{" "}
          {group.elections.toLocaleString("en-US")} elections ({withInterval(most)} with its 95%
          interval). The darker the cell, the more often the pair splits: every pair splits
          sometimes, and more candidates mean more splits.
        </p>
        <StudyCaption summary={summary} />
      </div>
    </div>
  );
}

/**
 * How often each method elects the Condorcet winner, with how often there is
 * one, and every number behind a table toggle.
 */
export function EfficiencyStep({ summary }: { summary: SimulationSummary }) {
  const counts = summary.by_candidates.map((g) => g.candidates);
  const [showTable, setShowTable] = useState(false);
  const group = summary.by_candidates[summary.by_candidates.length - 1];

  return (
    <div className="space-y-3">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <EfficiencyPlot summary={summary} selected={counts[counts.length - 1]} />
        <div className="min-w-0 space-y-3 text-sm leading-relaxed text-mi-ink-2">
          <p>
            A Condorcet winner exists in{" "}
            {summary.by_candidates.map((g, i) => (
              <span key={g.candidates}>
                {i > 0 ? (i === counts.length - 1 ? " and " : ", ") : null}
                <span className="font-mi-mono text-mi-ink">{percent(g.condorcet_winner)}</span>
              </span>
            ))}{" "}
            of elections with {counts.join(", ").replace(/, (\d+)$/, " and $1")} candidates. Cycles
            are rare in this model, so a method that misses the Condorcet winner here is passing over a
            candidate a majority prefers to every rival, not escaping a cycle.
          </p>
          <button
            type="button"
            aria-pressed={showTable}
            onClick={() => setShowTable((shown) => !shown)}
            className="min-h-11 rounded-[3px] border border-mi-rule px-2.5 py-1 text-sm text-mi-ink hover:border-mi-ink sm:min-h-0"
          >
            {showTable ? "Hide the numbers" : "Show the numbers"}
          </button>
          <StudyCaption summary={summary} />
        </div>
      </div>
      {showTable ? <NumbersTable summary={summary} group={group} /> : null}
    </div>
  );
}

function EfficiencyPlot({ summary, selected }: { summary: SimulationSummary; selected: number }) {
  const [tip, setTip] = useState<Tip | null>(null);
  const position = (rate: number | null) =>
    `${(((rate ?? 0) * 100 - AXIS.min) / (AXIS.max - AXIS.min)) * 100}%`;

  function showTip(method: VotingMethod, target: HTMLElement, container: HTMLElement | null) {
    if (!container) return;
    const box = container.getBoundingClientRect();
    const row = target.getBoundingClientRect();
    setTip({
      x: row.left - box.left + row.width / 2,
      y: row.bottom - box.top + 4,
      lines: [
        METHOD_META[method].label,
        ...summary.by_candidates.map(
          (g) =>
            `${g.candidates} candidates: ${withInterval(g.condorcet_efficiency[method])} of ${g.condorcet_winner.count.toLocaleString("en-US")}`
        ),
      ],
    });
  }

  return (
    <figure className="relative min-w-0" onPointerLeave={() => setTip(null)}>
      <figcaption>
        <p className="text-sm font-medium text-mi-ink">Condorcet efficiency</p>
        <p className="text-xs text-mi-muted">
          How often each method elects the Condorcet winner, when there is one.
        </p>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-mi-ink-2">
          {summary.by_candidates.map((g) => (
            <span key={g.candidates} className="inline-flex items-center gap-1.5">
              <span
                aria-hidden
                className="size-2.5 rounded-full"
                style={{ background: ink(COUNT_INK[g.candidates] ?? 100) }}
              />
              <span className={cn(g.candidates === selected && "font-semibold text-mi-ink")}>
                {g.candidates} candidates
              </span>
            </span>
          ))}
        </div>
      </figcaption>

      <div className="mt-3">
        {summary.methods.map((method) => {
          const rates = summary.by_candidates.map((g) => g.condorcet_efficiency[method].rate ?? 0);
          const low = Math.min(...rates);
          const high = Math.max(...rates);
          const chosen = summary.by_candidates.find((g) => g.candidates === selected);
          return (
            <div
              key={method}
              tabIndex={0}
              aria-label={`${METHOD_META[method].label}: ${summary.by_candidates
                .map((g) => `${percent(g.condorcet_efficiency[method])} with ${g.candidates} candidates`)
                .join(", ")}`}
              className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 gap-y-1 rounded-[3px] py-2 outline-none focus-visible:bg-mi-wash sm:flex sm:gap-2 sm:py-0.5"
              onPointerEnter={(event) =>
                showTip(method, event.currentTarget, event.currentTarget.closest("figure"))
              }
              onFocus={(event) => showTip(method, event.currentTarget, event.currentTarget.closest("figure"))}
              onBlur={() => setTip(null)}
            >
              <span className="min-w-0 text-sm text-mi-ink sm:w-28 sm:shrink-0">{METHOD_META[method].label}</span>
              <span className="relative col-span-2 row-start-2 h-7 min-w-0 sm:flex-1">
                {AXIS.ticks.map((t) => (
                  <span
                    key={t}
                    aria-hidden
                    className="absolute inset-y-0 w-px bg-mi-rule"
                    style={{ left: position(t / 100) }}
                  />
                ))}
                <span
                  aria-hidden
                  className="absolute top-1/2 h-0.5 -translate-y-1/2 rounded-full"
                  style={{
                    left: position(low),
                    width: `calc(${position(high)} - ${position(low)})`,
                    background: ink(25),
                  }}
                />
                {summary.by_candidates.map((g) => {
                  const isSelected = g.candidates === selected;
                  return (
                    <span
                      key={g.candidates}
                      aria-hidden
                      className={cn(
                        "absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full shadow-[0_0_0_2px_var(--mi-surface)]",
                        isSelected ? "size-3" : "size-2.5"
                      )}
                      style={{
                        left: position(g.condorcet_efficiency[method].rate),
                        background: ink(COUNT_INK[g.candidates] ?? 100),
                      }}
                    />
                  );
                })}
              </span>
              <span className="col-start-2 row-start-1 shrink-0 text-right font-mi-mono text-sm tabular-nums text-mi-ink sm:w-14 sm:text-xs">
                {chosen ? percent(chosen.condorcet_efficiency[method]) : null}
              </span>
            </div>
          );
        })}
        <div aria-hidden className="flex gap-2">
          <span className="hidden w-28 shrink-0 sm:block" />
          <span className="relative h-5 flex-1 font-mi-mono text-xs text-mi-muted sm:text-[0.68rem]">
            {AXIS.ticks.map((t) => (
              <span
                key={t}
                className="absolute top-0.5 -translate-x-1/2 tabular-nums"
                style={{ left: position(t / 100) }}
              >
                {t}%
              </span>
            ))}
          </span>
          <span className="hidden w-14 shrink-0 sm:block" />
        </div>
      </div>
      {tip ? <Tooltip tip={tip} /> : null}
    </figure>
  );
}

function DisagreementMatrix({
  group,
  methods,
  highlight,
}: {
  group: SimulationGroup;
  methods: VotingMethod[];
  /** A pair to outline, read out beside the matrix. */
  highlight?: [VotingMethod, VotingMethod];
}) {
  const [tip, setTip] = useState<Tip | null>(null);
  const rows = methods.slice(1);
  const columns = methods.slice(0, -1);

  return (
    <figure className="relative min-w-0" onPointerLeave={() => setTip(null)}>
      <figcaption>
        <p className="text-sm font-medium text-mi-ink">Disagreement</p>
        <p className="text-xs text-mi-muted">
          How often two methods elect different winners, {group.candidates} candidates (
          {group.elections.toLocaleString("en-US")} elections).
        </p>
      </figcaption>

      <p className="mt-2 text-sm text-mi-muted min-[360px]:hidden">Swipe across the matrix to see every method.</p>
      <div
        className="mt-3 overflow-x-auto pb-2"
        tabIndex={0}
        role="region"
        aria-label="Disagreement matrix"
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") event.stopPropagation();
        }}
      >
      <div
        className="grid min-w-[18rem] gap-0.5 sm:min-w-[24rem]"
        style={{ gridTemplateColumns: `minmax(3rem, auto) repeat(${columns.length}, minmax(0, 1fr))` }}
      >
        {rows.map((row, i) => (
          <div key={row} className="contents">
            {/* Short labels on a phone, matching the columns, so the matrix fits without a swipe. */}
            <span className="flex items-center pr-2 text-sm text-mi-ink" title={METHOD_META[row].label}><span className="font-mi-mono text-xs text-mi-ink-2 sm:hidden">{SHORT_LABELS[row]}</span><span className="hidden sm:inline">{METHOD_META[row].label}</span></span>
            {columns.map((column, j) => {
              if (j > i) return <span key={column} aria-hidden />;
              const rate = disagreement(group, row, column);
              const value = rate?.rate ?? 0;
              const shade = Math.min(1, value / FULL_SHADE) * 85;
              return (
                <span
                  key={column}
                  role="img"
                  aria-label={`${METHOD_META[row].label} and ${METHOD_META[column].label} disagree in ${rate ? percent(rate) : "no"} of elections`}
                  className={cn(
                    "flex h-10 items-center justify-center rounded-[2px] font-mi-mono text-sm tabular-nums",
                    shade > 45 ? "text-mi-surface" : "text-mi-ink",
                    highlight?.includes(row) &&
                      highlight.includes(column) &&
                      "ring-2 ring-mi-ink ring-offset-2 ring-offset-mi-surface"
                  )}
                  style={{ background: ink(shade) }}
                  onPointerEnter={(event) => {
                    const box = event.currentTarget.closest("figure")?.getBoundingClientRect();
                    const cell = event.currentTarget.getBoundingClientRect();
                    if (!box || !rate) return;
                    setTip({
                      x: cell.left - box.left + cell.width / 2,
                      y: cell.bottom - box.top + 4,
                      lines: [
                        `${METHOD_META[row].label} vs ${METHOD_META[column].label}`,
                        `${withInterval(rate)} of ${rate.of.toLocaleString("en-US")} elections`,
                      ],
                    });
                  }}
                >
                  {rate ? Math.round(value * 100) : ""}
                </span>
              );
            })}
          </div>
        ))}
        <span />
        {columns.map((column) => (
          <span
            key={column}
            title={METHOD_META[column].label}
            className="pt-1 text-center font-mi-mono text-xs text-mi-muted"
          >
            {SHORT_LABELS[column]}
          </span>
        ))}
      </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-mi-muted">
        <span className="font-mi-mono">0%</span>
        <span
          aria-hidden
          className="h-2 w-32 rounded-[2px]"
          style={{ background: `linear-gradient(to right, ${ink(0)}, ${ink(85)})` }}
        />
        <span className="font-mi-mono">{Math.round(FULL_SHADE * 100)}%+</span>
        <span>of elections, numbers in percent</span>
      </div>
      {tip ? <Tooltip tip={tip} /> : null}
    </figure>
  );
}

function NumbersTable({ summary, group }: { summary: SimulationSummary; group: SimulationGroup }) {
  return (
    <div
      className="min-w-0 space-y-4 overflow-x-auto"
      tabIndex={0}
      role="region"
      aria-label="Simulation numbers"
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") event.stopPropagation();
      }}
    >
      <table className="w-full min-w-[40rem] border-collapse text-xs">
        <caption className="pb-2 text-left text-sm font-medium text-mi-ink">
          Condorcet efficiency and tie rate, with 95% intervals
        </caption>
        <thead>
          <tr className="border-b border-mi-rule text-mi-muted">
            <th scope="col" className="py-1.5 pr-3 text-left font-normal">Method</th>
            {summary.by_candidates.map((g) => (
              <th key={g.candidates} scope="col" className="px-2 py-1.5 text-right font-normal">
                Efficiency, {g.candidates}
              </th>
            ))}
            {summary.by_candidates.map((g) => (
              <th key={g.candidates} scope="col" className="px-2 py-1.5 text-right font-normal">
                Ties, {g.candidates}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="font-mi-mono tabular-nums text-mi-ink">
          {summary.methods.map((method) => (
            <tr key={method} className="border-b border-mi-rule">
              <th scope="row" className="py-1.5 pr-3 text-left font-sans font-normal">
                {METHOD_META[method].label}
              </th>
              {summary.by_candidates.map((g) => (
                <td key={g.candidates} className="px-2 py-1.5 text-right">
                  {withInterval(g.condorcet_efficiency[method])}
                </td>
              ))}
              {summary.by_candidates.map((g) => (
                <td key={g.candidates} className="px-2 py-1.5 text-right">
                  {withInterval(g.tie_rate[method], 2)}
                </td>
              ))}
            </tr>
          ))}
          <tr>
            <th scope="row" className="py-1.5 pr-3 text-left font-sans font-normal">
              Condorcet winner exists
            </th>
            {summary.by_candidates.map((g) => (
              <td key={g.candidates} className="px-2 py-1.5 text-right">
                {withInterval(g.condorcet_winner, 2)}
              </td>
            ))}
          </tr>
        </tbody>
      </table>

      <table className="w-full min-w-[24rem] border-collapse text-xs">
        <caption className="pb-2 text-left text-sm font-medium text-mi-ink">
          Disagreement, {group.candidates} candidates, with 95% intervals
        </caption>
        <tbody className="font-mi-mono tabular-nums text-mi-ink">
          {group.disagreement.map((d) => (
            <tr key={`${d.a}-${d.b}`} className="border-b border-mi-rule">
              <th scope="row" className="py-1.5 pr-3 text-left font-sans font-normal">
                {METHOD_META[d.a].label} vs {METHOD_META[d.b].label}
              </th>
              <td className="px-2 py-1.5 text-right">{withInterval(d)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Tooltip({ tip }: { tip: Tip }) {
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute inset-x-0 z-10 max-w-full rounded-[3px] border border-mi-rule bg-mi-surface px-2.5 py-1.5 text-sm shadow-sm"
      style={{ top: tip.y }}
    >
      {tip.lines.map((line, i) => (
        <p key={i} className={cn("break-words", i === 0 ? "font-medium text-mi-ink" : "font-mi-mono text-mi-ink-2")}>
          {line}
        </p>
      ))}
    </div>
  );
}
