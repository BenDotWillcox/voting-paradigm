"use client";

import { ArrowDown, ArrowRight } from "lucide-react";
import { useState } from "react";

import { candidateColor } from "@/lib/methods/candidates";
import { channelTally } from "@/lib/methods/instrument";
import { inspectIRVRound } from "@/lib/methods/inspector-state";
import { cn } from "@/lib/utils";
import type { ProfileMethodResult, ProfileResolveResponse } from "@/types/methods";

import { CandidateMark } from "./glyph";

const control = "min-h-11 rounded-md border border-mi-rule px-3 py-2 text-sm text-mi-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink";
const signed = (value: number) => value > 0 ? `+${value}` : String(value);

/** Shows supplied ballot entries beside returned totals; never recomputes the tally. */
export function BallotTallyVisual({ result, resolution, phase }: {
  result: ProfileMethodResult;
  resolution: ProfileResolveResponse;
  phase: string;
}) {
  const [selected, setSelected] = useState(0);
  const candidates = resolution.rankings.candidates;
  const rated = resolution.voter_ballots;
  const rows = rated.length ? rated : resolution.rankings.rows;
  const rowIndex = Math.min(selected, rows.length - 1);
  const row = rows[rowIndex];
  const ballot = rated[rowIndex];
  const ranking = ballot?.ranking ?? resolution.rankings.rows[rowIndex]?.ranking ?? [];
  const values = channelTally(result) ?? {};
  const entries = Object.fromEntries(candidates.map((candidate) => {
    if (result.trace.kind === "plurality") return [candidate, (ballot ? ballot.choice : ranking[0]) === candidate ? 1 : 0];
    if (result.trace.kind === "borda") return [candidate, ranking.includes(candidate) ? result.trace.max_points_per_ballot - ranking.indexOf(candidate) : 0];
    if (result.trace.kind === "approval") return [candidate, ballot?.approvals.includes(candidate) ? 1 : 0];
    if (result.trace.kind === "score") return [candidate, ballot?.scores[candidate] ?? 0];
    return [candidate, ballot?.allocations[candidate] ?? 0];
  }));
  const unit = result.trace.kind === "borda" || result.trace.kind === "score" ? "points" : result.trace.kind === "approval" ? "approvals" : "votes";
  const showInputs = phase !== "winner";
  const credits = phase === "credits" && result.trace.kind === "quadratic";

  return <div className="space-y-5">
    {showInputs && row && <div className="space-y-3 rounded-lg border border-mi-rule bg-mi-surface p-3 sm:p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2"><p className="text-sm font-medium text-mi-ink">Choose a ballot group</p><span className="text-sm text-mi-ink-2">{row.count} voters share this ballot</span></div>
      <div role="group" aria-label="Example ballot group" className="flex flex-wrap gap-2">{rows.map((item, index) => <button type="button" key={index} onClick={() => setSelected(index)} aria-pressed={rowIndex === index} className={cn(control, rowIndex === index ? "border-mi-ink bg-mi-ink text-mi-surface" : "hover:bg-mi-wash")}>Group {index + 1}<span className="ml-1.5 font-mi-mono opacity-75">· {item.count}</span></button>)}</div>
      <p className="text-sm text-mi-ink-2">{credits ? "Signed votes and their cost on one ballot" : result.trace.kind === "borda" ? "One ranking → points for each position" : "Entries on one ballot"}</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{(result.trace.kind === "borda" ? ranking : candidates).map((candidate) => <div key={candidate} className={cn("min-w-0 rounded-md border px-3 py-2", entries[candidate] ? "border-mi-ink/30 bg-mi-wash" : "border-mi-rule")}>
        <div className="flex flex-wrap items-center justify-between gap-2 text-mi-ink"><CandidateMark id={candidate} size={17} className="min-w-0 [&>span]:break-all" /><span className="font-mi-mono text-xl">{result.trace.kind === "plurality" || result.trace.kind === "approval" ? entries[candidate] ? "✓" : "—" : result.trace.kind === "quadratic" ? signed(entries[candidate]) : entries[candidate]}</span></div>
        <p className="mt-1 text-sm text-mi-ink-2">{credits ? `${entries[candidate] < 0 ? `(${entries[candidate]})` : entries[candidate]}² = ${entries[candidate] ** 2} credits` : result.trace.kind === "borda" ? `Rank ${ranking.indexOf(candidate) + 1}` : entries[candidate] === 0 ? result.trace.kind === "score" ? "Valid zero rating" : "No contribution" : `${signed(entries[candidate])} ${unit}`}</p>
      </div>)}</div>
      {credits && ballot && <div className="space-y-2 border-t border-mi-rule pt-3"><p className="text-sm text-mi-ink"><strong className="font-mi-mono">{ballot.credits_used} / {ballot.credit_budget}</strong> credits spent per ballot</p><div className="h-2 overflow-hidden rounded-full bg-mi-rule" aria-hidden><div className="h-full bg-mi-ink motion-safe:transition-[width] motion-safe:duration-500" style={{ width: `${ballot.credit_budget > 0 ? 100 * ballot.credits_used / ballot.credit_budget : 0}%` }} /></div></div>}
      {rated.length > 0 && <p className="text-sm leading-relaxed text-mi-ink-2">Ballot choices supplied by <span className="font-mi-mono">{resolution.ballot_model}</span>.</p>}
    </div>}

    {showInputs && <div className="flex items-center gap-2 text-sm text-mi-ink-2"><ArrowDown size={16} aria-hidden /><span>{credits ? "Python records the aggregate credit use" : "Python adds every ballot’s entries"}</span></div>}
    {credits && result.trace.kind === "quadratic" ? <div className="grid grid-cols-2 gap-3 rounded-lg bg-mi-wash p-4"><Metric label="Credits spent" value={result.trace.credits_spent} /><Metric label="Credits available" value={result.trace.credits_available} /></div> : <RecordedBars candidates={candidates} values={values} label={`Returned ${unit}`} winner={phase === "winner" ? result.winner : undefined} entries={showInputs ? entries : undefined} signedValues={result.trace.kind === "quadratic"} />}
    {phase === "winner" && <WinnerNote result={result} />}
  </div>;
}

/** Animation interpolates between two recorded counts, not a simulated transfer. */
export function IRVRoundVisual({ result, resolution, phase, roundIndex }: {
  result: ProfileMethodResult;
  resolution: ProfileResolveResponse;
  phase: string;
  roundIndex: number;
}) {
  const [after, setAfter] = useState(false);
  if (result.trace.kind !== "irv") return null;
  const { round, next } = inspectIRVRound(result.trace, roundIndex);
  if (!round) return null;
  const transfer = phase === "transfer" && next;
  const shown = transfer && after ? next : round;
  const candidates = resolution.rankings.candidates.filter((candidate) => round.counts[candidate] !== undefined);
  const absent = candidates.filter((candidate) => shown.counts[candidate] === undefined);
  const active = Object.values(shown.counts).reduce((sum, count) => sum + count, 0);
  return <div className="space-y-4">
    {transfer && <div className="space-y-3"><div className="flex flex-wrap gap-2" role="group" aria-label="Recorded transfer comparison"><button type="button" className={cn(control, !after && "border-mi-ink bg-mi-ink text-mi-surface")} aria-pressed={!after} onClick={() => setAfter(false)}>Before · round {round.round_number}</button><button type="button" className={cn(control, after && "border-mi-ink bg-mi-ink text-mi-surface")} aria-pressed={after} onClick={() => setAfter(true)}>After · round {next.round_number}</button></div><p className="text-sm leading-relaxed text-mi-ink-2">Toggle between consecutive counts returned by Python. The change in each bar is recorded, not estimated.</p></div>}
    <div className="grid grid-cols-2 gap-3 rounded-lg bg-mi-wash p-4"><Metric label="Active ballots" value={active} /><Metric label="Exhausted ballots" value={shown.exhausted_ballots} /></div>
    <RecordedBars candidates={candidates} values={shown.counts} scaleValues={transfer ? { ...round.counts, ...next.counts } : undefined} label={`Recorded round ${shown.round_number}`} winner={phase === "winner" ? result.winner : undefined} eliminated={phase === "eliminate" ? round.eliminated : absent} absent={absent} />
    {phase === "eliminate" && round.eliminated.length > 0 && <p className="flex flex-wrap items-center gap-2 rounded-md border border-mi-rule p-3 text-sm text-mi-ink"><span>{round.elimination_was_tiebreak ? "After the tiebreak, remove" : "Remove"}</span>{round.eliminated.map((id) => <CandidateMark key={id} id={id} className="min-w-0 [&>span]:break-all" />)}<ArrowRight size={16} aria-hidden /><span>Next recorded round</span></p>}
    {phase === "winner" && <WinnerNote result={result} />}
  </div>;
}

/** Inspect one actual matrix comparison at a time. */
export function PairwiseVisual({ resolution }: { resolution: ProfileResolveResponse }) {
  const [selected, setSelected] = useState(0);
  const candidates = resolution.rankings.candidates;
  const pairs = candidates.flatMap((a, index) => candidates.slice(index + 1).map((b) => [a, b] as const));
  const pair = pairs[Math.min(selected, pairs.length - 1)];
  if (!pair) return null;
  const [a, b] = pair;
  const av = resolution.pairwise[a][b];
  const bv = resolution.pairwise[b][a];
  return <div className="space-y-4">
    <label className="block space-y-2 text-sm font-medium text-mi-ink"><span>Inspect a head-to-head race</span><select aria-label="Head-to-head comparison" value={selected} onChange={(event) => setSelected(Number(event.target.value))} className="min-h-11 w-full min-w-0 rounded-md border border-mi-rule bg-mi-surface px-3 text-base">{pairs.map(([left, right], index) => <option key={`${left}-${right}`} value={index}>{left} vs {right}</option>)}</select></label>
    <div className="rounded-lg border border-mi-rule bg-mi-surface p-4">
      <div className="mb-5 flex items-center justify-between gap-3 text-mi-ink"><div className="space-y-2"><CandidateMark id={a} size={24} className="min-w-0 [&>span]:break-all" /><p className="font-mi-mono text-3xl">{av}</p></div><span className="text-sm text-mi-ink-2">voters prefer</span><div className="space-y-2 text-right"><CandidateMark id={b} size={24} className="min-w-0 [&>span]:break-all" /><p className="font-mi-mono text-3xl">{bv}</p></div></div>
      <div aria-hidden className="flex h-6 overflow-hidden rounded-full border border-mi-ink/20">{[a, b].map((candidate, index) => <div key={candidate} className="motion-safe:transition-[width] motion-safe:duration-500" style={{ width: `${av + bv ? 100 * (index ? bv : av) / (av + bv) : 50}%`, background: candidateColor(candidate) }} />)}</div>
      <p className="mt-4 text-base text-mi-ink" aria-live="polite">{av === bv ? "This race is tied." : <><strong>{av > bv ? a : b}</strong> wins this comparison by <strong className="font-mi-mono">{Math.abs(av - bv)}</strong> votes.</>}</p>
    </div>
    <p className="text-sm leading-relaxed text-mi-ink-2">These two values come directly from Python’s pairwise matrix. Each ranked ballot contributes to every applicable comparison.</p>
  </div>;
}

function RecordedBars({ candidates, values, scaleValues, label, winner, entries, eliminated = [], absent = [], signedValues = false }: {
  candidates: string[];
  values: Record<string, number>;
  scaleValues?: Record<string, number>;
  label: string;
  winner?: string;
  entries?: Record<string, number>;
  eliminated?: string[];
  absent?: string[];
  signedValues?: boolean;
}) {
  const max = Math.max(1, ...Object.values(scaleValues ?? values).map(Math.abs));
  const negative = signedValues && Object.values(values).some((value) => value < 0);
  return <div className="space-y-3"><p className="text-sm font-medium text-mi-ink">{label}</p><ul className="space-y-4" aria-label={label}>{candidates.map((candidate) => {
    const value = values[candidate] ?? 0;
    const out = eliminated.includes(candidate);
    const width = Math.abs(value) / max * (negative ? 50 : 100);
    return <li key={candidate} className={cn("min-w-0 space-y-2 rounded-md p-2 motion-safe:transition-colors", candidate === winner && "bg-mi-surface ring-1 ring-mi-ink", out && "opacity-55")}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-mi-ink"><CandidateMark id={candidate} size={17} className="min-w-0 [&>span]:break-all" /><span className="flex flex-wrap items-baseline justify-end gap-2"><span className="font-mi-mono text-xl">{absent.includes(candidate) ? "—" : signedValues ? signed(value) : value}</span>{candidate === winner ? <span className="text-sm">Winner</span> : out ? <span className="text-sm">Out</span> : entries && entries[candidate] !== 0 ? <span className="rounded bg-mi-surface px-1.5 py-0.5 text-sm">{signed(entries[candidate])} per selected ballot</span> : null}</span></div>
      <div className="relative h-4 overflow-hidden rounded-sm bg-mi-rule/55" aria-hidden>{negative && <span className="absolute inset-y-0 left-1/2 z-10 border-l border-mi-ink/50" />}<span className="absolute inset-y-0 motion-safe:transition-[width,left,opacity] motion-safe:duration-500" style={{ left: negative ? `${value < 0 ? 50 - width : 50}%` : 0, width: `${width}%`, background: candidateColor(candidate), opacity: entries && !entries[candidate] ? 0.3 : 0.9 }} /></div>
    </li>;
  })}</ul>{negative && <p className="text-sm text-mi-ink-2">Negative votes extend left of zero; positive votes extend right.</p>}</div>;
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="min-w-0"><p className="break-words font-mi-mono text-2xl text-mi-ink">{value.toLocaleString("en-US")}</p><p className="mt-1 text-sm text-mi-ink-2">{label}</p></div>;
}

function WinnerNote({ result }: { result: ProfileMethodResult }) {
  return <p className="flex flex-wrap items-center gap-2 rounded-md border border-mi-ink/25 bg-mi-surface p-3 text-sm text-mi-ink"><CandidateMark id={result.winner} size={18} className="min-w-0 [&>span]:break-all" /><span>is the winner returned by Python.</span></p>;
}
