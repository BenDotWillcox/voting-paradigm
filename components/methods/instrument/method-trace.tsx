"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { candidateColor } from "@/lib/methods/candidates";
import { methodDescriptions } from "@/lib/methods/method-descriptions";
import { positionCounts } from "@/lib/methods/profile";
import type {
  ApprovalTrace,
  BordaTrace,
  IRVTrace,
  PluralityTrace,
  ProfileMethodResult,
  ProfileResolveResponse,
  QuadraticTrace,
  RankedPairsTrace,
  ScoreTrace,
} from "@/types/methods";

import { CandidateMark } from "./glyph";

/**
 * How the selected method reached its winner, step by step where it has
 * steps, followed by what the method is known for.
 */
export function MethodTrace({
  result,
  resolution,
}: {
  result: ProfileMethodResult;
  resolution: ProfileResolveResponse;
}) {
  const trace = result.trace;
  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-mi-ink-2">
        {methodDescriptions[result.method].howItWorks}
      </p>
      {trace.kind === "plurality" ? (
        <PluralityView trace={trace} resolution={resolution} winner={result.winner} />
      ) : trace.kind === "irv" ? (
        <IRVView
          key={JSON.stringify(resolution.rankings.rows)}
          trace={trace}
          winner={result.winner}
          candidates={resolution.rankings.candidates}
        />
      ) : trace.kind === "borda" ? (
        <BordaView trace={trace} resolution={resolution} winner={result.winner} />
      ) : trace.kind === "ranked_pairs" ? (
        <RankedPairsView trace={trace} resolution={resolution} winner={result.winner} />
      ) : trace.kind === "approval" ? (
        <ApprovalView trace={trace} resolution={resolution} winner={result.winner} />
      ) : trace.kind === "score" ? (
        <ScoreView trace={trace} resolution={resolution} winner={result.winner} />
      ) : (
        <QuadraticView trace={trace} resolution={resolution} winner={result.winner} />
      )}
      {result.tiebreaks.length > 0 ? (
        <div className="border-t border-mi-rule pt-3 text-xs text-mi-ink-2">
          <p className="font-medium text-mi-ink">Ties broken by the seeded tiebreak (seed {resolution.tiebreak_seed})</p>
          <ul className="mt-1 space-y-0.5 font-mi-mono">
            {result.tiebreaks.map((event, index) => (
              <li key={index}>
                {event.tied.join(", ")} tied → {event.chose}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <MethodProfile method={result.method} />
    </div>
  );
}

function MethodProfile({ method }: { method: ProfileMethodResult["method"] }) {
  const description = methodDescriptions[method];
  const lists: [string, string[]][] = [
    ["Strengths", description.strengths],
    ["Weaknesses", description.weaknesses],
    ["Where it's used", description.realWorldUsage],
  ];
  return (
    <div className="border-t border-mi-rule pt-3">
      <p className="text-xs text-mi-muted">
        Also called {description.aliases.join(", ")}. Ballot: {description.ballotType.toLowerCase()}.
      </p>
      <div className="mt-2 grid gap-4 text-sm sm:grid-cols-3">
        {lists.map(([title, items]) => (
          <div key={title}>
            <p className="text-xs font-medium text-mi-ink">{title}</p>
            <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-relaxed text-mi-ink-2 marker:text-mi-muted">
              {items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

function Bars({
  values,
  candidates,
  max,
  winner,
  struck = [],
  suffix,
}: {
  values: Record<string, number>;
  candidates: string[];
  max: number;
  winner?: string;
  struck?: string[];
  suffix?: (id: string) => React.ReactNode;
}) {
  return (
    <ul className="space-y-1.5">
      {candidates.map((id) => {
        const value = values[id] ?? 0;
        const out = struck.includes(id);
        return (
          <li key={id} className="grid grid-cols-[2.5rem_minmax(0,1fr)_auto] items-center gap-3">
            <CandidateMark id={id} className={out ? "text-mi-muted" : "text-mi-ink"} />
            <span className="h-3 w-full">
              <span
                className="block h-full rounded-r-[4px]"
                style={{
                  width: `${max > 0 ? (100 * value) / max : 0}%`,
                  background: candidateColor(id),
                  opacity: out ? 0.3 : 1,
                }}
              />
            </span>
            <span
              className={`min-w-[4.5rem] text-right font-mi-mono text-sm ${
                id === winner ? "font-semibold text-mi-ink" : "text-mi-ink-2"
              }`}
            >
              {value}
              {suffix ? suffix(id) : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function PluralityView({
  trace,
  resolution,
  winner,
}: {
  trace: PluralityTrace;
  resolution: ProfileResolveResponse;
  winner: string;
}) {
  const total = resolution.total_voters;
  const top = trace.first_choices[winner] ?? 0;
  return (
    <div className="space-y-2">
      <Bars
        values={trace.first_choices}
        candidates={resolution.rankings.candidates}
        max={total}
        winner={winner}
        suffix={(id) => (
          <span className="ml-2 text-mi-muted">
            {Math.round((100 * (trace.first_choices[id] ?? 0)) / Math.max(total, 1))}%
          </span>
        )}
      />
      <p className="text-xs text-mi-muted">
        {winner} wins with {top} of {total} first choices
        {2 * top > total ? ", a majority." : ", short of a majority."}
      </p>
    </div>
  );
}

function IRVView({
  trace,
  winner,
  candidates,
}: {
  trace: IRVTrace;
  winner: string;
  candidates: string[];
}) {
  const [step, setStep] = useState(0);
  const round = trace.rounds[step];
  const previous = step > 0 ? trace.rounds[step - 1] : null;
  const gone = trace.rounds.slice(0, step).flatMap((r) => r.eliminated);
  const active = candidates.filter((id) => !gone.includes(id));
  const max = Math.max(...trace.rounds.flatMap((r) => Object.values(r.counts)), 1);
  const roundTotal = active.reduce((sum, id) => sum + (round.counts[id] ?? 0), 0);
  const last = step === trace.rounds.length - 1;

  return (
    <div
      className="space-y-3"
      tabIndex={0}
      aria-label="IRV rounds. Left and right arrows step between rounds."
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft" && step > 0) setStep(step - 1);
        if (event.key === "ArrowRight" && !last) setStep(step + 1);
      }}
    >
      <Stepper
        label={`Round ${round.round_number} of ${trace.rounds.length}`}
        canBack={step > 0}
        canForward={!last}
        onBack={() => setStep(step - 1)}
        onForward={() => setStep(step + 1)}
      />
      <Bars
        values={round.counts}
        candidates={active}
        max={max}
        winner={last ? winner : undefined}
        struck={round.eliminated}
        suffix={(id) =>
          previous && (round.counts[id] ?? 0) > (previous.counts[id] ?? 0) ? (
            <span className="ml-2 text-mi-muted">
              +{(round.counts[id] ?? 0) - (previous.counts[id] ?? 0)}
            </span>
          ) : null
        }
      />
      <p className="text-xs text-mi-muted" aria-live="polite">
        {round.eliminated.length > 0
          ? `No majority of ${roundTotal} ballots. ${round.eliminated.join(" and ")} ${
              round.eliminated.length > 1 ? "tie for fewest and are" : "has the fewest and is"
            } eliminated${round.elimination_was_tiebreak ? " (by tiebreak)" : ""}; those ballots move to their next choice.`
          : `${winner} wins with ${round.counts[winner] ?? 0} of ${roundTotal} remaining ballots.`}
      </p>
    </div>
  );
}

function BordaView({
  trace,
  resolution,
  winner,
}: {
  trace: BordaTrace;
  resolution: ProfileResolveResponse;
  winner: string;
}) {
  const candidates = resolution.rankings.candidates;
  const positions = positionCounts(resolution.rankings);
  const weights = candidates.map((_, position) => trace.max_points_per_ballot - position);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse font-mi-mono text-sm">
        <caption className="sr-only">Borda: voters at each position and points</caption>
        <thead>
          <tr className="border-b border-mi-rule text-xs text-mi-muted">
            <th className="py-1.5 text-left font-normal">Ranked</th>
            {weights.map((weight, position) => (
              <th key={position} className="px-2 py-1.5 text-right font-normal">
                {ordinal(position + 1)} ×{weight}
              </th>
            ))}
            <th className="py-1.5 pl-3 text-right font-normal">Points</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((id) => (
            <tr key={id} className="border-b border-mi-rule last:border-0">
              <th scope="row" className="py-1.5 text-left font-normal">
                <CandidateMark id={id} />
              </th>
              {positions[id].map((count, position) => (
                <td key={position} className="px-2 py-1.5 text-right text-mi-ink-2">
                  {count}
                </td>
              ))}
              <td className={`py-1.5 pl-3 text-right ${id === winner ? "font-semibold text-mi-ink" : "text-mi-ink-2"}`}>
                {trace.points[id] ?? 0}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RankedPairsView({
  trace,
  resolution,
  winner,
}: {
  trace: RankedPairsTrace;
  resolution: ProfileResolveResponse;
  winner: string;
}) {
  const candidates = resolution.rankings.candidates;
  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <table className="border-collapse font-mi-mono text-sm">
          <caption className="mb-1 text-left font-mi-sans text-xs text-mi-muted">
            Voters ranking the row candidate above the column candidate
          </caption>
          <thead>
            <tr>
              <th className="p-1.5" />
              {candidates.map((id) => (
                <th key={id} className="p-1.5 font-normal">
                  <CandidateMark id={id} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {candidates.map((a) => (
              <tr key={a}>
                <th scope="row" className="p-1.5 text-left font-normal">
                  <CandidateMark id={a} />
                </th>
                {candidates.map((b) => {
                  const forA = resolution.pairwise[a]?.[b] ?? 0;
                  const forB = resolution.pairwise[b]?.[a] ?? 0;
                  return (
                    <td
                      key={b}
                      className={`border border-mi-rule px-3 py-1.5 text-center ${
                        a === b ? "bg-mi-wash" : forA > forB ? "font-semibold text-mi-ink" : "text-mi-muted"
                      }`}
                    >
                      {a === b ? "" : forA}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {trace.had_condorcet_winner ? (
        <p className="text-sm text-mi-ink-2">
          {winner} beats every other candidate head to head, so it wins without locking anything.
        </p>
      ) : (
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <p className="text-xs text-mi-muted">Locked, strongest first</p>
            <ol className="mt-1 space-y-0.5 font-mi-mono">
              {trace.locked.map((v) => (
                <li key={`${v.winner}${v.loser}`}>
                  {v.winner} › {v.loser} <span className="text-mi-muted">by {v.margin}</span>
                </li>
              ))}
            </ol>
          </div>
          <div>
            <p className="text-xs text-mi-muted">Skipped, would close a cycle</p>
            <ol className="mt-1 space-y-0.5 font-mi-mono text-mi-muted">
              {trace.skipped.length === 0 ? <li>none</li> : null}
              {trace.skipped.map((v) => (
                <li key={`${v.winner}${v.loser}`} className="line-through">
                  {v.winner} › {v.loser} by {v.margin}
                </li>
              ))}
            </ol>
          </div>
          <p className="text-xs text-mi-muted sm:col-span-2">
            No locked victory points to {winner}, so {winner} wins.
            {trace.tiebreak_priority.length > 0
              ? ` Equal-strength victories were ordered by the tiebreak priority ${trace.tiebreak_priority.join(" › ")}.`
              : ""}
          </p>
        </div>
      )}
    </div>
  );
}

function ApprovalView({
  trace,
  resolution,
  winner,
}: {
  trace: ApprovalTrace;
  resolution: ProfileResolveResponse;
  winner: string;
}) {
  const voters = resolution.total_voters;
  return (
    <div className="space-y-2">
      <Bars
        values={trace.approvals}
        candidates={resolution.rankings.candidates}
        max={voters}
        winner={winner}
        suffix={(id) => (
          <span className="ml-2 text-mi-muted">
            {Math.round((100 * (trace.approvals[id] ?? 0)) / Math.max(voters, 1))}%
          </span>
        )}
      />
      <p className="text-xs text-mi-muted">
        Approvals out of {voters} voters
        {trace.abstentions > 0
          ? `; ${trace.abstentions} indifferent ${trace.abstentions === 1 ? "voter" : "voters"} approved no one.`
          : "."}
      </p>
    </div>
  );
}

function ScoreView({
  trace,
  resolution,
  winner,
}: {
  trace: ScoreTrace;
  resolution: ProfileResolveResponse;
  winner: string;
}) {
  const voters = resolution.total_voters;
  const max = voters * trace.max_score;
  return (
    <div className="space-y-2">
      <Bars
        values={trace.totals}
        candidates={resolution.rankings.candidates}
        max={max}
        winner={winner}
        suffix={(id) => (
          <span className="ml-2 text-mi-muted">
            avg {((trace.totals[id] ?? 0) / Math.max(voters, 1)).toFixed(1)}
          </span>
        )}
      />
      <p className="text-xs text-mi-muted">
        Total score out of {max} possible ({voters} voters × {trace.max_score}).
      </p>
    </div>
  );
}

function QuadraticView({
  trace,
  resolution,
  winner,
}: {
  trace: QuadraticTrace;
  resolution: ProfileResolveResponse;
  winner: string;
}) {
  const candidates = resolution.rankings.candidates;
  const max = Math.max(1, ...candidates.map((id) => Math.abs(trace.net_votes[id] ?? 0)));
  return (
    <div className="space-y-2">
      <ul className="space-y-1.5">
        {candidates.map((id) => {
          const votes = trace.net_votes[id] ?? 0;
          return (
            <li key={id} className="grid grid-cols-[2.5rem_minmax(0,1fr)_4.5rem] items-center gap-3">
              <CandidateMark id={id} />
              <span className="relative h-3">
                <span aria-hidden className="absolute inset-y-[-3px] left-1/2 w-px bg-mi-rule" />
                <span
                  className={
                    votes >= 0
                      ? "absolute inset-y-0 left-1/2 rounded-r-[4px]"
                      : "absolute inset-y-0 rounded-l-[4px]"
                  }
                  style={{
                    width: `${(50 * Math.abs(votes)) / max}%`,
                    right: votes < 0 ? "50%" : undefined,
                    background: candidateColor(id),
                  }}
                />
              </span>
              <span
                className={`text-right font-mi-mono text-sm ${
                  id === winner ? "font-semibold text-mi-ink" : "text-mi-ink-2"
                }`}
              >
                {votes > 0 ? `+${votes}` : votes}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-mi-muted">
        Net votes: for minus against. Voters spent {trace.credits_spent} of{" "}
        {trace.credits_available} credits.
      </p>
    </div>
  );
}

function Stepper({
  label,
  canBack,
  canForward,
  onBack,
  onForward,
}: {
  label: string;
  canBack: boolean;
  canForward: boolean;
  onBack: () => void;
  onForward: () => void;
}) {
  const button =
    "grid size-7 place-items-center rounded-[3px] border border-mi-rule text-mi-ink hover:bg-mi-wash disabled:opacity-35 disabled:hover:bg-transparent";
  return (
    <div className="flex items-center gap-2">
      <button type="button" className={button} disabled={!canBack} onClick={onBack} aria-label="Previous round">
        <ChevronLeft className="size-4" />
      </button>
      <span className="min-w-[7.5rem] text-center font-mi-mono text-sm text-mi-ink">{label}</span>
      <button type="button" className={button} disabled={!canForward} onClick={onForward} aria-label="Next round">
        <ChevronRight className="size-4" />
      </button>
    </div>
  );
}

function ordinal(n: number): string {
  return n === 1 ? "1st" : n === 2 ? "2nd" : n === 3 ? "3rd" : `${n}th`;
}
