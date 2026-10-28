"use client";

import { Check, Copy } from "lucide-react";
import { useId, useMemo, useState, type ReactNode } from "react";

import { excerptListing, placeNotes, STAGE_EMPHASIS, stageListing, stageNotes, stageRowStates } from "@/lib/methods/code-listing";
import { buildCountExample, type CountSource, type InspectableMethod } from "@/lib/methods/count-inspector";
import { METHOD_META } from "@/lib/methods/instrument";
import { inspectIRVRound, irvSourcePhase, recordedGraphSources, recordedVictoryGroups } from "@/lib/methods/inspector-state";
import { cn } from "@/lib/utils";
import type { ProfileResolveResponse, RankedPairsTrace, Victory } from "@/types/methods";

import { CandidateMark, GlyphShapeSvg } from "./glyph";
import { additionalMethodSteps, additionalStageExplanation } from "./additional-method-stages";
import { CodeView, keepArrowsInCode } from "./code-view";
import { BallotTallyVisual, IRVRoundVisual, PairwiseVisual } from "./method-visualization";

const button = "inline-flex min-h-11 items-center justify-center gap-2 rounded-[3px] border border-mi-rule px-3 py-2 text-sm font-medium text-mi-ink hover:bg-mi-wash focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink";
const PLURALITY_STEPS = [{ id: "count", label: "Count" }, { id: "winner", label: "Winner" }];
const CONDORCET_STEPS = [{ id: "pairwise", label: "Pairwise" }, { id: "condorcet_return", label: "Return winner" }];
const LOCKING_STEPS = [
  { id: "pairwise", label: "Pairwise" },
  { id: "condorcet", label: "Winner check" },
  { id: "order", label: "Strength" },
  { id: "lock", label: "Lock" },
  { id: "cycle", label: "Cycle" },
  { id: "winner", label: "Winner" },
];

/** Inspects a Python response. It does not resolve ballots in the browser. */
export function MethodCodeInspector({ method, resolution, source, sourceLabel = "Recorded Python result", context }: {
  method: InspectableMethod;
  resolution: ProfileResolveResponse;
  source: CountSource;
  sourceLabel?: string;
  context?: ReactNode;
}) {
  const uniqueId = useId();
  const exampleId = `${uniqueId}-example`;
  const [sourceOpen, setSourceOpen] = useState(false);
  const [phase, setPhase] = useState(method === "ranked_pairs" ? "pairwise" : "count");
  const [roundIndex, setRoundIndex] = useState(0);
  const [showCheck, setShowCheck] = useState(false);
  const [showExample, setShowExample] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");
  const listing = useMemo(() => stageListing(source), [source]);
  const result = resolution.results.find((item) => item.method === method);
  if (!result) return null;
  const label = METHOD_META[method].label;
  const isCondorcet = result.trace.kind === "ranked_pairs" && result.trace.had_condorcet_winner;
  const steps = method === "plurality" ? PLURALITY_STEPS : method === "ranked_pairs" ? isCondorcet ? CONDORCET_STEPS : LOCKING_STEPS : additionalMethodSteps(method);
  const activePhase = steps.some((step) => step.id === phase) ? phase : steps[0].id;
  const irvTrace = result.trace.kind === "irv" ? result.trace : undefined;
  const inspectedRoundIndex = irvTrace && activePhase === "winner" ? irvTrace.rounds.length - 1 : roundIndex;
  const selectedRound = irvTrace ? inspectIRVRound(irvTrace, inspectedRoundIndex) : undefined;
  const sourcePhase = irvTrace ? irvSourcePhase(irvTrace, inspectedRoundIndex, activePhase)
    : activePhase === "condorcet_return" && showCheck ? "condorcet"
    : activePhase === "order" && showCheck ? "priority" : activePhase;
  const excerpt = source.excerpts[sourcePhase];
  const rowStates = stageRowStates(listing, excerpt, STAGE_EMPHASIS[sourcePhase]);
  const notes = placeNotes(listing, rowStates, stageNotes(result, resolution, sourcePhase, inspectedRoundIndex));
  const example = buildCountExample(method, resolution, source);
  const explanation = explainStage(method, activePhase, resolution, result.winner, isCondorcet, inspectedRoundIndex);

  async function copyExample() {
    try {
      await navigator.clipboard.writeText(example);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
      setShowExample(true);
    }
  }

  return (
    <section className="min-w-0" aria-label={`${label} calculation inspector`}>
      <h3 className="sr-only">{sourceLabel}</h3>
      <div className="grid grid-cols-2 gap-1 border-b border-mi-rule bg-mi-wash/60 p-1.5 sm:flex sm:flex-wrap" role="group" aria-label={`${label} calculation stage`}>
        {steps.map((step, index) => (
          <button key={step.id} type="button" aria-pressed={activePhase === step.id} onClick={() => { setPhase(step.id); setShowCheck(false); if (step.id === "winner" && result.trace.kind === "irv") setRoundIndex(result.trace.rounds.length - 1); }} className={cn("flex min-h-11 min-w-0 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink sm:flex-1", activePhase === step.id ? "bg-mi-surface text-mi-ink shadow-sm ring-1 ring-mi-rule" : "text-mi-ink-2 hover:bg-mi-surface/70")}>
            <span className="font-mi-mono text-mi-muted">{index + 1}</span>{step.label}
          </button>
        ))}
      </div>
      <div className="min-w-0 space-y-5 p-3 sm:p-5 lg:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-mi-ink-2">{resolution.total_voters} voters · seed {resolution.tiebreak_seed}</p>
          <button type="button" onClick={copyExample} className={button} aria-label={copyStatus === "copied" ? "Copied Python example" : "Copy runnable example"}>{copyStatus === "copied" ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}{copyStatus === "copied" ? "Copied" : "Copy example"}</button>
        </div>
        <div className="grid min-w-0 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <section aria-label={`${label} Python source for selected stage`} className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <p className="break-all font-mi-mono text-sm text-mi-ink">{source.path}</p>
              <p className="text-sm text-mi-ink-2">Lines {excerpt.startLine}–{excerpt.startLine + excerpt.lines.length - 1}</p>
            </div>
            {activePhase === "condorcet_return" && <button type="button" onClick={() => setShowCheck(!showCheck)} aria-pressed={showCheck} className={button}>{showCheck ? "Show the early return" : "Show the winner check"}</button>}
            {activePhase === "order" && <button type="button" onClick={() => setShowCheck(!showCheck)} aria-pressed={showCheck} className={button}>{showCheck ? "Show strength grouping" : "Show equal-strength tie handling"}</button>}
            <CodeView rows={listing} states={rowStates} notes={notes} label={`${label} Python source, lines ${excerpt.startLine}–${excerpt.startLine + excerpt.lines.length - 1} in this stage`} />
            <p className="text-sm leading-relaxed text-mi-ink-2">Actual package source. This stage’s lines are in color, the red mark sits beside the line that drives it, and <code className="font-mi-mono">#</code> notes show the saved result.</p>
            <details className="min-w-0 border-t border-mi-rule pt-3" open={sourceOpen} onToggle={(event) => {
              if (event.target === event.currentTarget) setSourceOpen(event.currentTarget.open);
            }}>
              <summary className="min-h-11 cursor-pointer text-sm font-medium text-mi-ink">Read the complete {label} source</summary>
              {sourceOpen && <><p className="mb-3 break-all font-mi-mono text-sm text-mi-ink-2">SHA-256 (LF): {source.sha256}</p>
              <CodeView rows={excerptListing(source.source.trimEnd().split("\n"), 1)} label={`Complete ${label} Python source`} /></>}
            </details>
          </section>
          <section aria-label={`${label} calculation state`} className="min-w-0 space-y-4 rounded-xl border border-mi-rule bg-mi-wash/50 p-3 sm:p-4">
            <h4 className="break-words text-lg font-semibold leading-snug text-mi-ink" aria-live="polite">{explanation.title}</h4>
            {irvTrace && <div className="flex flex-wrap items-center gap-2"><p className="mr-1 text-sm font-medium text-mi-ink">Recorded round</p><div className="flex flex-wrap gap-2" role="group" aria-label="IRV recorded round">{irvTrace.rounds.map((round, index) => <button key={round.round_number} type="button" className={cn(button, "min-w-11", selectedRound?.index === index && "border-mi-ink bg-mi-surface")} aria-pressed={selectedRound?.index === index} onClick={() => { setRoundIndex(index); if (activePhase === "winner") setPhase("count"); }}>{round.round_number}{round.round_number === irvTrace.winning_round ? " · final" : ""}</button>)}</div></div>}
            {result.trace.kind === "ranked_pairs" ? (
              <RankedState phase={activePhase} resolution={resolution} trace={result.trace} winner={result.winner} />
            ) : result.trace.kind === "irv" ? (
              <IRVRoundVisual key={`${activePhase}-${inspectedRoundIndex}`} result={result} phase={activePhase} resolution={resolution} roundIndex={inspectedRoundIndex} />
            ) : (
              <BallotTallyVisual result={result} phase={activePhase} resolution={resolution} />
            )}
            <p className="break-words text-base leading-relaxed text-mi-ink-2">{explanation.body}</p>
            {activePhase === "winner" && result.tiebreaks.length > 0 && <details className="rounded-[3px] border border-mi-rule px-3"><summary className="min-h-11 cursor-pointer py-3 text-sm font-medium text-mi-ink">See the recorded tiebreaks</summary><ol className="space-y-2 pb-3 text-sm text-mi-ink">{result.tiebreaks.map((tie, index) => <li key={index} className="break-words">{index + 1}. {tie.tied.join(", ")} → {tie.chose}</li>)}</ol></details>}
          </section>
        </div>
        {context && <div className="border-t border-mi-rule pt-4">{context}</div>}
        <section aria-label={`Reproduce ${label}`} className="min-w-0 space-y-3 border-t border-mi-rule pt-4">
          <div className="flex flex-wrap items-start justify-between gap-3"><p className="max-w-2xl text-sm leading-relaxed text-mi-ink-2">The copied example includes every ballot, the seed, and assertions for the returned result. Save it as <code className="break-all font-mi-mono">{method}_example.py</code> in the <a href="https://github.com/BenDotWillcox/voting-paradigm" className="underline underline-offset-4">repository</a>, then run <code className="break-words font-mi-mono">python {method}_example.py</code> with Python 3.11+.</p><button type="button" aria-expanded={showExample} aria-controls={exampleId} onClick={() => setShowExample(!showExample)} className={button}>{showExample ? "Hide" : "View"} runnable example</button></div>
          <p role="status" className={copyStatus === "failed" ? "text-sm text-mi-ink" : "sr-only"}>{copyStatus === "copied" ? "Python example copied to clipboard." : copyStatus === "failed" ? "Clipboard access is unavailable. Select and copy the example below." : ""}</p>
          {showExample && <textarea id={exampleId} aria-label={`${label} runnable Python example`} readOnly wrap="off" spellCheck={false} value={example} rows={12} onKeyDown={keepArrowsInCode} className="block w-full min-w-0 resize-y rounded-md border border-mi-rule bg-mi-wash p-3 font-mi-mono text-base leading-6 text-mi-ink focus-visible:outline-2 focus-visible:outline-mi-ink" />}
        </section>
      </div>
    </section>
  );
}

function explainStage(method: InspectableMethod, phase: string, resolution: ProfileResolveResponse, winner: string, isCondorcet: boolean, roundIndex: number) {
  const result = resolution.results.find((item) => item.method === method)!;
  if (result.trace.kind !== "plurality" && result.trace.kind !== "ranked_pairs") return additionalStageExplanation(result, phase, roundIndex);
  if (result.trace.kind === "plurality") {
    const total = result.trace.first_choices[winner];
    return phase === "count"
      ? { title: "One mark adds one vote", body: "The loop adds one to the marked candidate for every ballot. The recorded ballot groups expand into individual single-choice ballots in the runnable example." }
      : { title: `${winner} ${result.tiebreaks.length ? "wins the tied largest tally" : "has the most marks"}`, body: `${winner} wins with ${total} of ${resolution.total_voters} votes. Plurality chooses the largest tally; it does not require a majority. ${result.tiebreaks.length ? "The saved result records a seeded tiebreak." : "This count has one leader, so no tiebreak is used."}` };
  }
  const trace = result.trace as RankedPairsTrace;
  const sources = recordedGraphSources(resolution.rankings.candidates, trace.locked);
  const groups = recordedVictoryGroups(trace, resolution.pairwise);
  const labels: Record<string, { title: string; body: string }> = {
    pairwise: { title: "Every ranking contributes to each two-way race", body: "Read each row as the voters preferring that candidate to the column candidate. These are the matrix entries returned by Python, built from the recorded ranked ballots." },
    condorcet_return: { title: `${winner} beats every rival: return ${winner}`, body: `The Condorcet check finds ${winner}. The implementation returns immediately, with empty locked and skipped lists. This count never enters the locking pass.` },
    condorcet: { title: isCondorcet ? `${winner} beats every rival` : "No candidate strictly beats every rival", body: isCondorcet ? `The winner check finds ${winner}.` : "A loss or a pairwise tie prevents a candidate from passing this check. Python returns None and continues to the locking pass." },
    order: { title: groups.length ? "Group victories by strength" : "There are no strict pairwise victories", body: groups.length ? `Strength means margin, then winning votes. These groups summarize saved edges; they are not a combined processing log. ${trace.tiebreak_priority.length ? "Python recorded a candidate priority because equal-strength victories needed an ordering decision." : groups.some((group) => group.edges.length > 1) ? "Some victories have equal strength, but Python needed no candidate-priority draw for this count." : "Every recorded victory has a distinct strength."}` : "Every two-way race is tied, so there are no victory edges to order or lock. The final source selection uses the seeded tiebreak." },
    lock: { title: "Keep victories that preserve an acyclic graph", body: "These solid arrows are the victories recorded as locked by Python. Each accepted edge points from the two-way winner to the loser." },
    cycle: { title: trace.skipped.length ? `${trace.skipped.length} ${trace.skipped.length === 1 ? "victory was" : "victories were"} skipped` : "No victory was skipped", body: trace.skipped.length ? "For a proposed winner → loser edge, the helper searches from loser back to winner. A reachable winner would close a cycle. The graph shows the final recorded locks and the selected skipped edge; it is not a playback of intermediate graph states." : "The saved trace contains no skipped victories. The source shows the cycle check used by the locking pass; no rejected edge is invented for this result." },
    winner: { title: sources.length === 1 ? `${winner} is the only source of the locked graph` : `${winner} wins the source tiebreak`, body: sources.length === 1 ? `${winner} is the only candidate with no incoming locked edge, so Python returns ${winner}. Skipped victories do not count as incoming edges.` : `The final graph has ${sources.length} candidates with no incoming locked edge: ${sources.join(", ")}. Python uses the seeded tiebreak to choose ${winner} from them. This is separate from any priority used to order equal-strength victories.` },
  };
  return labels[phase];
}


function BallotRows({ resolution, singleChoice = false }: { resolution: ProfileResolveResponse; singleChoice?: boolean }) {
  return <details className="rounded-[3px] border border-mi-rule px-3"><summary className="min-h-11 cursor-pointer py-3 text-sm font-medium text-mi-ink">{singleChoice ? "See the ballot groups" : "See the ranked ballot groups"}</summary><ul className="space-y-2 pb-3">{resolution.rankings.rows.map((row) => <li key={row.ranking.join("|")} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-mi-ink"><span className="font-mi-mono">{row.count} ×</span>{(singleChoice ? row.ranking.slice(0, 1) : row.ranking).map((id, index) => <span key={id} className="inline-flex min-w-0 max-w-full items-center gap-2">{index > 0 && <span aria-label="preferred to">›</span>}<CandidateMark id={id} size={13} className="min-w-0 [&>span]:break-all" /></span>)}</li>)}</ul></details>;
}

function PairwiseTable({ resolution }: { resolution: ProfileResolveResponse }) {
  const candidates = resolution.rankings.candidates;
  return <div role="region" aria-label="Pairwise counts table" tabIndex={0} onKeyDown={keepArrowsInCode} className="min-w-0 overflow-x-auto overscroll-contain focus-visible:outline-2 focus-visible:outline-mi-ink"><table className={cn("w-full table-fixed border-collapse text-center text-sm text-mi-ink", candidates.length > 3 ? "min-w-[22rem]" : "min-w-[14rem]")}><caption className="mb-2 text-left text-sm text-mi-ink-2">Voters preferring the row to the column</caption><thead><tr className="border-b border-mi-rule"><th scope="col" className="py-2 font-normal">vs.</th>{candidates.map((id) => <th key={id} scope="col" className="px-1 py-2 font-normal"><CandidateMark id={id} size={12} className="min-w-0 [&>span]:break-all" /></th>)}</tr></thead><tbody>{candidates.map((a) => <tr key={a} className="border-b border-mi-rule"><th scope="row" className="px-1 py-3 font-normal"><CandidateMark id={a} size={12} className="min-w-0 [&>span]:break-all" /></th>{candidates.map((b) => <td key={b} className={cn("py-3 font-mi-mono text-base", a !== b && resolution.pairwise[a][b] > resolution.pairwise[b][a] && "bg-mi-wash font-semibold")}>{a === b ? "—" : resolution.pairwise[a][b]}</td>)}</tr>)}</tbody></table></div>;
}

function RankedState({ phase, resolution, trace, winner }: { phase: string; resolution: ProfileResolveResponse; trace: RankedPairsTrace; winner: string }) {
  const [skippedIndex, setSkippedIndex] = useState(0);
  const selectId = useId();
  if (phase === "pairwise") return <><PairwiseVisual resolution={resolution} /><details className="rounded-md border border-mi-rule p-3"><summary className="min-h-11 cursor-pointer text-sm font-medium text-mi-ink">Inspect the complete pairwise matrix</summary><PairwiseTable resolution={resolution} /></details><BallotRows resolution={resolution} /></>;
  if (phase === "condorcet" || phase === "condorcet_return") return <><PairwiseTable resolution={resolution} />{trace.had_condorcet_winner && <div className="break-words rounded-[3px] bg-mi-wash p-3 font-mi-mono text-sm text-mi-ink">winner = {winner}<br />locked = []<br />skipped = []</div>}</>;
  if (phase === "order") {
    const groups = recordedVictoryGroups(trace, resolution.pairwise);
    return <div className="space-y-3">{groups.length ? <ul className="space-y-3" aria-label="Recorded victories grouped by strength">{groups.map((group) => <li key={`${group.margin}:${group.winningVotes}`} className="space-y-2 rounded-[3px] border border-mi-rule p-3"><p className="font-mi-mono text-sm text-mi-ink">Margin {group.margin} · {group.winningVotes} winning votes</p><ul className="space-y-2 text-sm text-mi-ink-2">{group.edges.map((edge) => <li key={`${edge.winner}-${edge.loser}`} className="break-words">{edge.winner} → {edge.loser} · {edge.status}</li>)}</ul>{group.edges.length > 1 && <p className="text-sm text-mi-ink-2">Equal strength; order within this list does not indicate processing order.</p>}</li>)}</ul> : <p className="text-sm text-mi-ink">No positive margins were recorded.</p>}<div className="rounded-[3px] bg-mi-wash p-3 text-sm text-mi-ink"><p className="font-medium">Recorded candidate priority</p><p className="mt-1 break-words">{trace.tiebreak_priority.length ? trace.tiebreak_priority.join(" → ") : "None needed"}</p>{trace.tiebreak_priority.length > 0 && <p className="mt-2 text-mi-ink-2">Highest priority first. In affected groups, Python sorts by winner priority, then reverses loser priority for a shared winner.</p>}</div></div>;
  }
  const selectedSkipped = trace.skipped[Math.min(skippedIndex, trace.skipped.length - 1)];
  const shownSkipped = phase === "cycle" && selectedSkipped ? [selectedSkipped] : phase === "winner" ? trace.skipped : [];
  return <>
    {phase === "cycle" && trace.skipped.length > 0 && <div className="space-y-2"><label htmlFor={selectId} className="block text-sm font-medium text-mi-ink">Recorded skipped victory</label><select id={selectId} value={Math.min(skippedIndex, trace.skipped.length - 1)} onChange={(event) => setSkippedIndex(Number(event.target.value))} className="min-h-11 w-full min-w-0 rounded-[3px] border border-mi-rule bg-mi-surface px-3 text-base text-mi-ink">{trace.skipped.map((edge, index) => <option key={`${edge.winner}-${edge.loser}`} value={index}>{edge.winner} → {edge.loser} · margin {edge.margin}</option>)}</select></div>}
    <LockedGraph candidates={resolution.rankings.candidates} locked={trace.locked} skipped={shownSkipped} winner={phase === "winner" ? winner : undefined} />
    <RecordedEdges label="Recorded locks, in saved order" edges={trace.locked} />
    {phase !== "lock" && <RecordedEdges label="Recorded skips, in saved order" edges={trace.skipped} />}
    {phase === "winner" && <p className="break-words text-sm text-mi-ink">Candidates with no incoming locked edge: {recordedGraphSources(resolution.rankings.candidates, trace.locked).join(", ")}.</p>}
  </>;
}

function RecordedEdges({ label, edges }: { label: string; edges: Victory[] }) {
  return <div className="space-y-2 text-sm text-mi-ink"><p className="font-medium">{label}</p>{edges.length ? <ol className="space-y-2">{edges.map((edge, index) => <li key={`${edge.winner}-${edge.loser}`} className="break-words">{index + 1}. {edge.winner} → {edge.loser} · margin {edge.margin}</li>)}</ol> : <p className="text-mi-ink-2">None</p>}</div>;
}

function LockedGraph({ candidates, locked, skipped, winner }: { candidates: string[]; locked: Victory[]; skipped: Victory[]; winner?: string }) {
  const markerId = useId().replace(/:/g, "");
  const positions = new Map(candidates.map((candidate, index) => {
    const angle = -Math.PI / 2 + 2 * Math.PI * index / candidates.length;
    return [candidate, [140 + 88 * Math.cos(angle), 140 + 88 * Math.sin(angle)] as const] as const;
  }));
  const edges = [...locked.map((edge) => ({ ...edge, skipped: false })), ...skipped.map((edge) => ({ ...edge, skipped: true }))];
  const description = edges.length ? edges.map((edge) => `${edge.winner} to ${edge.loser}, ${edge.skipped ? "skipped" : "locked"}, margin ${edge.margin}`).join("; ") : "no victory edges";
  const useNumbers = candidates.some((candidate) => candidate.length > 3);
  return <figure className="space-y-2"><svg viewBox="0 0 280 280" className="mx-auto block w-full max-w-[20rem] rounded-[3px] bg-mi-wash" role="img" aria-label={`Final recorded Ranked Pairs graph: ${description}${winner ? `. Winner ${winner}` : ""}`}><defs><marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,1 L9,5 L0,9 z" fill="var(--mi-ink)" /></marker></defs>{edges.map((edge) => {
    const [x1, y1] = positions.get(edge.winner)!;
    const [x2, y2] = positions.get(edge.loser)!;
    const length = Math.hypot(x2 - x1, y2 - y1);
    const ux = (x2 - x1) / length;
    const uy = (y2 - y1) / length;
    return <line key={`${edge.winner}-${edge.loser}`} x1={x1 + 22 * ux} y1={y1 + 22 * uy} x2={x2 - 25 * ux} y2={y2 - 25 * uy} stroke="var(--mi-ink)" strokeWidth={2} strokeDasharray={edge.skipped ? "6 5" : undefined} markerEnd={`url(#${markerId})`} />;
  })}{candidates.map((candidate, index) => {
    const [x, y] = positions.get(candidate)!;
    return <g key={candidate}>{winner === candidate && <circle cx={x} cy={y} r={21} fill="none" stroke="var(--mi-ink)" strokeWidth={2} />}<GlyphShapeSvg id={candidate} cx={x} cy={y} r={13} /><text x={140 + (x - 140) * 1.26} y={140 + (y - 140) * 1.26} textAnchor="middle" dominantBaseline="central" fill="var(--mi-ink)" fontSize={22} className="font-mi-mono">{useNumbers ? index + 1 : candidate}</text></g>;
  })}</svg><figcaption className="space-y-1 text-sm text-mi-ink-2"><p>Solid = locked{skipped.length > 0 ? "; dashed = skipped" : ""}. Margins appear in the recorded lists.</p>{useNumbers && candidates.map((candidate, index) => <p key={candidate} className="break-words">{index + 1}: {candidate}</p>)}</figcaption></figure>;
}

