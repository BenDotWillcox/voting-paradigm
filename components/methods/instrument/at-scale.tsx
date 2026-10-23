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

/**
 * The methods at scale: Condorcet efficiency and pairwise disagreement over
 * the seeded spatial elections of eval/benchmarks/methods_simulation_v1.
 */
export function AtScale({ summary }: { summary: SimulationSummary }) {
  const counts = summary.by_candidates.map((g) => g.candidates);
  const [selected, setSelected] = useState(counts[counts.length - 1]);
  const [showTable, setShowTable] = useState(false);
  const group = summary.by_candidates.find((g) => g.candidates === selected) ?? summary.by_candidates[0];
  const { config } = summary;
  const total = config.elections * counts.length;

  return (
    <div className="space-y-5">
      <p className="max-w-3xl text-sm leading-relaxed text-mi-ink-2">
        {total.toLocaleString("en-US")} seeded elections, {config.elections.toLocaleString("en-US")}{" "}
        each with {counts.join(", ").replace(/, (\d+)$/, " and $1")} candidates. Every election
        draws its candidates and {config.voters} voters from the same Gaussian in the plane;
        utility falls with distance, {summary.ballot_model} casts the ballots, and the seven
        methods count them exactly as on the earlier slides.
      </p>

      <p className="text-sm text-mi-ink">
        A Condorcet winner exists in{" "}
        {summary.by_candidates.map((g, i) => (
          <span key={g.candidates}>
            {i > 0 ? (i === counts.length - 1 ? " and " : ", ") : null}
            <span className="font-mi-mono">{percent(g.condorcet_winner)}</span>
          </span>
        ))}{" "}
        of elections with {counts.join(", ").replace(/, (\d+)$/, " and $1")} candidates, so
        Condorcet efficiency is measured over nearly every election.
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs text-mi-muted">Candidates</span>
        <div className="flex gap-1" role="group" aria-label="Candidates per election">
          {counts.map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={k === selected}
              onClick={() => setSelected(k)}
              className={cn(
                "min-w-9 rounded-[3px] border px-2.5 py-1 font-mi-mono text-sm",
                k === selected
                  ? "border-mi-ink bg-mi-ink text-mi-surface"
                  : "border-mi-rule text-mi-ink hover:border-mi-ink"
              )}
            >
              {k}
            </button>
          ))}
        </div>
        <button
          type="button"
          aria-pressed={showTable}
          onClick={() => setShowTable((shown) => !shown)}
          className="ml-auto rounded-[3px] border border-mi-rule px-2.5 py-1 text-sm text-mi-ink hover:border-mi-ink"
        >
          {showTable ? "Hide the numbers" : "Show the numbers"}
        </button>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <EfficiencyPlot summary={summary} selected={selected} />
        <DisagreementMatrix group={group} methods={summary.methods} />
      </div>

      {showTable ? <NumbersTable summary={summary} group={group} /> : null}

      <p className="font-mi-mono text-xs leading-relaxed text-mi-muted">
        {summary.benchmark} · seed {config.seed} · {summary.interval} intervals · ties: seeded
        tiebreak (seed {config.tiebreak_seed}), or for instant runoff, candidates tied for last
        eliminated together · source {summary.source_sha256.slice(0, 12)}…
      </p>
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
    <figure className="relative" onPointerLeave={() => setTip(null)}>
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
              className="group flex items-center gap-2 rounded-[3px] py-0.5 outline-none focus-visible:bg-mi-wash"
              onPointerEnter={(event) =>
                showTip(method, event.currentTarget, event.currentTarget.closest("figure"))
              }
              onFocus={(event) => showTip(method, event.currentTarget, event.currentTarget.closest("figure"))}
              onBlur={() => setTip(null)}
            >
              <span className="w-28 shrink-0 truncate text-sm text-mi-ink">{METHOD_META[method].label}</span>
              <span className="relative h-7 flex-1">
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
              <span className="w-14 shrink-0 text-right font-mi-mono text-xs tabular-nums text-mi-ink">
                {chosen ? percent(chosen.condorcet_efficiency[method]) : null}
              </span>
            </div>
          );
        })}
        <div aria-hidden className="flex gap-2">
          <span className="w-28 shrink-0" />
          <span className="relative h-5 flex-1 font-mi-mono text-[0.68rem] text-mi-muted">
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
          <span className="w-14 shrink-0" />
        </div>
      </div>
      {tip ? <Tooltip tip={tip} /> : null}
    </figure>
  );
}

function DisagreementMatrix({ group, methods }: { group: SimulationGroup; methods: VotingMethod[] }) {
  const [tip, setTip] = useState<Tip | null>(null);
  const rows = methods.slice(1);
  const columns = methods.slice(0, -1);

  return (
    <figure className="relative" onPointerLeave={() => setTip(null)}>
      <figcaption>
        <p className="text-sm font-medium text-mi-ink">Disagreement</p>
        <p className="text-xs text-mi-muted">
          How often two methods elect different winners, {group.candidates} candidates (
          {group.elections.toLocaleString("en-US")} elections).
        </p>
      </figcaption>

      <div
        className="mt-3 grid gap-0.5"
        style={{ gridTemplateColumns: `minmax(5.5rem, auto) repeat(${columns.length}, minmax(0, 1fr))` }}
      >
        {rows.map((row, i) => (
          <div key={row} className="contents">
            <span className="flex items-center pr-2 text-xs text-mi-ink">{METHOD_META[row].label}</span>
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
                    "flex h-9 items-center justify-center rounded-[2px] font-mi-mono text-xs tabular-nums",
                    shade > 45 ? "text-mi-surface" : "text-mi-ink"
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
            className="pt-1 text-center font-mi-mono text-[0.68rem] text-mi-muted"
          >
            {SHORT_LABELS[column]}
          </span>
        ))}
      </div>

      <div className="mt-3 flex items-center gap-2 text-[0.68rem] text-mi-muted">
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
    <div className="space-y-4 overflow-x-auto">
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
      className="pointer-events-none absolute z-10 -translate-x-1/2 rounded-[3px] border border-mi-rule bg-mi-surface px-2.5 py-1.5 text-xs shadow-sm"
      style={{ left: tip.x, top: tip.y }}
    >
      {tip.lines.map((line, i) => (
        <p key={i} className={cn("whitespace-nowrap", i === 0 ? "font-medium text-mi-ink" : "font-mi-mono text-mi-ink-2")}>
          {line}
        </p>
      ))}
    </div>
  );
}
