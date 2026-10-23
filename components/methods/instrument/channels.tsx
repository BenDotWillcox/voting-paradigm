"use client";

import { Check, Minus, X } from "lucide-react";

import { candidateColor } from "@/lib/methods/candidates";
import {
  BALLOT_GROUPS,
  METHOD_META,
  channelTally,
  criteriaChecks,
  type CriterionCheck,
} from "@/lib/methods/instrument";
import { cn } from "@/lib/utils";
import type {
  ProfileMethodResult,
  ProfileResolveResponse,
  VotingMethod,
} from "@/types/methods";

import { CandidateGlyph } from "./glyph";

/**
 * One row per method, grouped by the ballot it reads and always in the same
 * order: what the method counted, whom it elected, and how that winner fares
 * against the single-profile criteria. Selecting a row opens its count.
 */
export function Channels({
  resolution,
  selected,
  onSelect,
}: {
  resolution: ProfileResolveResponse;
  selected: VotingMethod;
  onSelect: (method: VotingMethod) => void;
}) {
  const byMethod = new Map(resolution.results.map((result) => [result.method, result]));
  return (
    <div>
      <div
        className="hidden grid-cols-[minmax(0,11rem)_minmax(0,1fr)_4.5rem_8.5rem] gap-4 px-3 pb-2 text-xs text-mi-muted xl:grid"
        aria-hidden
      >
        <span>Method</span>
        <span>Count</span>
        <span>Winner</span>
        <span className="flex justify-between">
          <span title="Majority winner elected">Maj.</span>
          <span title="Condorcet winner elected">Cond.</span>
          <span title="Condorcet loser avoided">Loser</span>
        </span>
      </div>
      {BALLOT_GROUPS.map((group) => {
        const results = group.methods.flatMap((method) => byMethod.get(method) ?? []);
        if (results.length === 0) return null;
        return (
          <section key={group.label} aria-label={group.label}>
            <h3 className="border-t border-mi-rule px-3 pt-2.5 pb-1 font-mi-mono text-[0.6875rem] tracking-wide text-mi-muted">
              {group.label}
            </h3>
            <ul role="list">
              {results.map((result) => (
                <li key={result.method}>
                  <ChannelRow
                    result={result}
                    resolution={resolution}
                    selected={selected === result.method}
                    onSelect={() => onSelect(result.method)}
                  />
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function ChannelRow({
  result,
  resolution,
  selected,
  onSelect,
}: {
  result: ProfileMethodResult;
  resolution: ProfileResolveResponse;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={cn(
        "grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-3 py-2.5 text-left",
        "xl:grid-cols-[minmax(0,11rem)_minmax(0,1fr)_4.5rem_8.5rem]",
        "hover:bg-mi-wash focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-mi-ink",
        selected && "bg-mi-wash"
      )}
    >
      <span>
        <span className="block font-medium text-mi-ink">{METHOD_META[result.method].label}</span>
        <span className="block text-xs text-mi-muted">{METHOD_META[result.method].rule}</span>
      </span>
      <span className="col-span-2 row-start-2 xl:col-span-1 xl:row-start-auto">
        <ChannelCount result={result} candidates={resolution.rankings.candidates} />
      </span>
      <span className="col-start-2 row-start-1 flex items-center justify-end gap-1.5 xl:col-start-auto xl:row-start-auto xl:justify-start">
        <CandidateGlyph id={result.winner} size={20} />
        <span className="font-mi-mono text-lg font-semibold">{result.winner}</span>
      </span>
      <CriteriaCells result={result} criteria={resolution.criteria} />
    </button>
  );
}

function ChannelCount({
  result,
  candidates,
}: {
  result: ProfileMethodResult;
  candidates: string[];
}) {
  const tally = channelTally(result);
  if (result.trace.kind === "ranked_pairs") {
    const trace = result.trace;
    return (
      <span className="font-mi-mono text-xs leading-relaxed text-mi-ink-2">
        {trace.had_condorcet_winner ? (
          <>beats every rival head to head</>
        ) : (
          <>
            {trace.locked.map((v) => `${v.winner}›${v.loser} ${v.margin}`).join("  ")}
            {trace.skipped.length ? (
              <span className="text-mi-muted line-through decoration-mi-muted">
                {"  "}
                {trace.skipped.map((v) => `${v.winner}›${v.loser} ${v.margin}`).join("  ")}
              </span>
            ) : null}
          </>
        )}
        {!result.decisive ? <TieNote /> : null}
      </span>
    );
  }
  if (!tally) return null;
  const total = candidates.reduce((sum, id) => sum + Math.max(0, tally[id] ?? 0), 0);
  const shown = candidates.filter((id) => (tally[id] ?? 0) > 0);
  // Net quadratic votes can be negative, which a share bar cannot show
  const hasNegative = candidates.some((id) => (tally[id] ?? 0) < 0);
  // IRV's final round only lists the candidates still in the count
  const listed = result.trace.kind === "irv" ? shown : candidates;
  return (
    <span className="block space-y-1">
      <span className={cn("flex h-2.5 w-full gap-[2px]", hasNegative && "hidden")} aria-hidden>
        {shown.map((id) => (
          <span
            key={id}
            className="h-full first:rounded-l-[4px] last:rounded-r-[4px]"
            style={{
              width: `${(100 * (tally[id] ?? 0)) / Math.max(total, 1)}%`,
              background: candidateColor(id),
            }}
          />
        ))}
      </span>
      <span className="flex flex-wrap gap-x-3 font-mi-mono text-xs text-mi-ink-2">
        {listed.map((id) => (
          <span
            key={id}
            className={cn(
              "inline-flex items-center gap-1",
              id === result.winner && "font-semibold text-mi-ink"
            )}
          >
            <CandidateGlyph id={id} size={10} />
            {id} {tally[id] ?? 0}
          </span>
        ))}
        {result.trace.kind === "irv" ? <span className="text-mi-muted">final round</span> : null}
        {result.trace.kind === "quadratic" ? <span className="text-mi-muted">net votes</span> : null}
        {!result.decisive ? <TieNote /> : null}
      </span>
    </span>
  );
}

function TieNote() {
  return (
    <span className="ml-2 rounded-[3px] border border-mi-ink px-1 font-mi-sans text-[0.6875rem] text-mi-ink">
      tie broken
    </span>
  );
}

function CriteriaCells({
  result,
  criteria,
}: {
  result: ProfileMethodResult;
  criteria: ProfileResolveResponse["criteria"];
}) {
  const checks = criteriaChecks(result, criteria);
  return (
    <span className="col-span-2 flex justify-between gap-3 text-xs xl:col-span-1">
      <CriterionCell name="Majority winner elected" short="Maj." check={checks.majority} />
      <CriterionCell name="Condorcet winner elected" short="Cond." check={checks.condorcetWinner} />
      <CriterionCell name="Condorcet loser avoided" short="Loser" check={checks.condorcetLoser} />
    </span>
  );
}

function CriterionCell({
  name,
  short,
  check,
}: {
  name: string;
  short: string;
  check: CriterionCheck;
}) {
  const label =
    check === "none"
      ? `${name}: does not apply`
      : `${name}: ${check === "pass" ? "yes" : "no"}`;
  return (
    <span className="inline-flex items-center gap-1" title={label}>
      <span className="text-mi-muted xl:hidden">{short}</span>
      <span
        className={cn(
          "grid size-5 place-items-center rounded-[3px]",
          check === "fail" && "bg-mi-ink text-mi-surface",
          check === "pass" && "border border-mi-ink text-mi-ink",
          check === "none" && "text-mi-muted"
        )}
      >
        {check === "pass" ? (
          <Check className="size-3.5" aria-hidden />
        ) : check === "fail" ? (
          <X className="size-3.5" aria-hidden />
        ) : (
          <Minus className="size-3" aria-hidden />
        )}
        <span className="sr-only">{label}</span>
      </span>
    </span>
  );
}
