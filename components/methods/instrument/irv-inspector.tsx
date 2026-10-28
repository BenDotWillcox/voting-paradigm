"use client";

import { Check, Code2, Copy } from "lucide-react";
import { useState } from "react";

import { buildIRVExample, type IRVPhase, type IRVSource } from "@/lib/methods/irv-inspector";
import type { Story } from "@/lib/methods/stories";
import { cn } from "@/lib/utils";
import type { IRVRoundTrace } from "@/types/methods";

import { CandidateMark } from "./glyph";

const PHASES: { id: IRVPhase; label: string }[] = [
  { id: "count", label: "Count" },
  { id: "eliminate", label: "Eliminate" },
  { id: "transfer", label: "Transfer" },
  { id: "winner", label: "Winner" },
];

const button = "inline-flex min-h-11 items-center justify-center gap-2 rounded-[3px] border border-mi-rule px-3 py-2 text-sm font-medium text-mi-ink hover:bg-mi-wash focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink";

/** Explains saved round data alongside source; never recounts ballots in JavaScript. */
export function IRVInspector({ story, source }: { story: Story; source: IRVSource }) {
  const [phase, setPhase] = useState<IRVPhase>("eliminate");
  const [sourceOpen, setSourceOpen] = useState(false);
  const [showExample, setShowExample] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");
  const before = story.before.results.find((result) => result.method === "irv");
  const after = story.after.results.find((result) => result.method === "irv");
  if (before?.trace.kind !== "irv" || after?.trace.kind !== "irv") return null;

  const firstBefore = before.trace.rounds[0];
  const firstAfter = after.trace.rounds[0];
  const finalBefore = before.trace.rounds[before.trace.rounds.length - 1];
  const finalAfter = after.trace.rounds[after.trace.rounds.length - 1];
  const outBefore = firstBefore.eliminated.join(" and ");
  const outAfter = firstAfter.eliminated.join(" and ");
  const first = phase === "count" || phase === "eliminate";
  const shownBefore = first ? firstBefore : finalBefore;
  const shownAfter = first ? firstAfter : finalAfter;
  const thresholdBefore = Math.floor(story.before.total_voters / 2) + 1;
  const thresholdAfter = Math.floor(story.after.total_voters / 2) + 1;
  const excerpt = source.excerpts[phase];
  const example = buildIRVExample(story, source);
  const change = story.specimen.transformation;
  const addedTo = change?.kind === "add_voters" ? change.ranking[0] : "";
  const title = {
    count: `Only ${addedTo}'s first-choice count changes`,
    eliminate: `The first changed decision: ${outBefore} → ${outAfter}`,
    transfer: "A different elimination sends ballots a different way",
    winner: `The winner changes from ${before.winner} to ${after.winner}`,
  }[phase];
  const explanation = {
    count: `The same loop counts every ballot. ${addedTo} rises from ${firstBefore.counts[addedTo]} to ${firstAfter.counts[addedTo]}; the other first-choice counts stay fixed.`,
    eliminate: `Neither count has a majority. The smallest tally is ${Math.min(...Object.values(firstBefore.counts))} before and ${Math.min(...Object.values(firstAfter.counts))} after. That changes which candidate is eliminated. Neither elimination needs a tiebreak.`,
    transfer: `Before, ${outBefore}'s ${firstBefore.counts[outBefore]} ballots move to ${before.winner}. After, ${outAfter}'s ${firstAfter.counts[outAfter]} ballots move to ${after.winner}. The helper advances each ballot past eliminated candidates; the counting loop tallies its next active choice.`,
    winner: `${before.winner} finishes with ${finalBefore.counts[before.winner]} of ${story.before.total_voters} votes; ${after.winner} finishes with ${finalAfter.counts[after.winner]} of ${story.after.total_voters}. Both clear the majority check. No ballots are exhausted in this example.`,
  }[phase];

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
    <section className="min-w-0 rounded-[4px] border border-mi-rule" aria-label="IRV calculation inspector">
      <header className="flex flex-wrap items-start justify-between gap-3 px-4 py-4 sm:px-5">
        <div className="min-w-0 space-y-2">
          <h3 className="flex items-center gap-2 text-base font-semibold text-mi-ink"><Code2 size={19} aria-hidden /> One rule, two outcomes</h3>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-mi-ink" aria-label={`Before: ${before.winner} wins. After: ${after.winner} wins.`}><span className="inline-flex items-center gap-2">Before <CandidateMark id={before.winner} size={18} /></span><span className="inline-flex items-center gap-2">After <CandidateMark id={after.winner} size={18} /></span></p>
        </div>
        <button type="button" onClick={copyExample} className={button}>{copyStatus === "copied" ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}{copyStatus === "copied" ? "Copied Python example" : "Copy runnable example"}</button>
      </header>
      <div className="min-w-0 space-y-5 border-t border-mi-rule p-4 sm:p-5">
        <p className="text-sm leading-relaxed text-mi-ink-2">
          Replay of the saved Python counts. Choose a stage to see its state and the source that produces it.
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="group" aria-label="Calculation stage">
          {PHASES.map((item, index) => (
            <button key={item.id} type="button" aria-pressed={phase === item.id} onClick={() => setPhase(item.id)}
              className={cn(button, "justify-start", phase === item.id && "border-mi-ink bg-mi-wash")}
            >
              <span className="font-mi-mono text-mi-ink-2">{index + 1}</span> {item.label}
            </button>
          ))}
        </div>

        <div className="grid min-w-0 items-start gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <section className="min-w-0 space-y-3" aria-label="Python source for selected stage">
            <div>
              <p className="break-all font-mi-mono text-sm text-mi-ink">{source.path}</p>
              <p className="mt-1 text-sm text-mi-ink-2">Lines {excerpt.startLine}–{excerpt.startLine + excerpt.lines.length - 1} · {phase === "eliminate" ? "Find the fewest votes" : PHASES.find((item) => item.id === phase)?.label}</p>
            </div>
            <SourceCode lines={excerpt.lines} startLine={excerpt.startLine} label="Python excerpt" highlight={phase} />
            <p className="text-sm text-mi-ink-2 lg:hidden">Scroll the code sideways for long lines.</p>
            {phase === "eliminate" && <p className="text-sm leading-relaxed text-mi-ink-2">This excerpt finds the fewest votes. Each count has one last-place candidate, which the method then eliminates.</p>}
          </section>
          <section className="min-w-0 space-y-4" aria-label="Before and after calculation state">
            <div aria-live="polite" aria-atomic="true">
              <p className="font-mi-mono text-sm text-mi-ink-2">{first ? "Round 1" : "Round 2"}</p>
              <h4 className="mt-1 text-lg font-semibold leading-snug text-mi-ink">{title}</h4>
            </div>
            <table className="w-full table-fixed border-collapse text-sm text-mi-ink">
              <caption className="sr-only">{first ? "First-choice" : "Final-round"} tallies before and after adding two voters</caption>
              <thead><tr className="border-b border-mi-rule text-mi-ink-2">
                <th className="w-1/4 py-2 text-left font-normal" scope="col">Choice</th>
                <th className="py-2 text-center font-normal" scope="col">Before<span className="block">{story.before.total_voters} voters</span></th>
                <th className="py-2 text-center font-normal" scope="col">After<span className="block">{story.after.total_voters} voters</span></th>
              </tr></thead>
              <tbody>{story.before.rankings.candidates.map((candidate) => (
                <tr key={candidate} className="border-b border-mi-rule">
                  <th scope="row" className="py-3 text-left font-normal"><CandidateMark id={candidate} size={15} /></th>
                  <TallyCell candidate={candidate} round={shownBefore} phase={phase} winner={before.winner} />
                  <TallyCell candidate={candidate} round={shownAfter} phase={phase} winner={after.winner} changed={first && firstBefore.counts[candidate] !== firstAfter.counts[candidate]} />
                </tr>
              ))}</tbody>
            </table>
            {(phase === "eliminate" || phase === "winner") && (
              <p className="rounded-[3px] bg-mi-wash p-3 text-sm leading-relaxed text-mi-ink-2">
                A majority needs <strong className="text-mi-ink">{thresholdBefore} votes before</strong> and <strong className="text-mi-ink">{thresholdAfter} after</strong>.
              </p>
            )}
            <p className="text-base leading-relaxed text-mi-ink-2">{explanation}</p>
          </section>

        </div>

        <section className="min-w-0 space-y-3 border-t border-mi-rule pt-5" aria-label="Reproduce the experiment">
          <h4 className="text-base font-semibold text-mi-ink">Run both counts yourself</h4>
          <p className="text-sm leading-relaxed text-mi-ink-2">
            Save as <code className="font-mi-mono">irv_example.py</code> in this project&apos;s root, then run <code className="break-words font-mi-mono">python irv_example.py</code> with Python 3.11+. The example adds the two ballots and checks both winners and every round. No API server is needed.
          </p>
          <p className="sr-only" role="status">{copyStatus === "copied" ? "Python example copied to clipboard." : ""}</p>
          {copyStatus === "failed" && <p role="status" className="text-sm text-mi-ink">Clipboard access is unavailable. Select and copy the example below.</p>}
          <button type="button" className={cn(button, "border-transparent underline underline-offset-4")} aria-expanded={showExample} aria-controls="irv-runnable-example" onClick={() => setShowExample(!showExample)}>{showExample ? "Hide" : "View"} runnable example</button>
          {showExample && <textarea id="irv-runnable-example" aria-label="Runnable Python example" readOnly value={example} spellCheck={false} rows={12} onKeyDown={keepArrowsInInspector} className="block w-full min-w-0 resize-y rounded-[3px] border border-mi-rule bg-mi-wash p-3 font-mi-mono text-base leading-6 text-mi-ink focus-visible:outline-2 focus-visible:outline-mi-ink" />}
        </section>

        <details className="min-w-0 border-t border-mi-rule pt-4" open={sourceOpen} onToggle={(event) => {
          if (event.target === event.currentTarget) setSourceOpen(event.currentTarget.open);
        }}>
          <summary className="min-h-11 cursor-pointer text-sm font-medium text-mi-ink">Read the complete IRV source</summary>
          {sourceOpen && <><p className="mb-3 break-all font-mi-mono text-sm text-mi-ink-2">SHA-256 (LF): {source.sha256}</p>
          <SourceCode lines={source.source.trimEnd().split("\n")} startLine={1} label="Complete IRV Python source" /></>}
        </details>
      </div>
    </section>
  );
}

function TallyCell({ candidate, round, phase, winner, changed }: {
  candidate: string; round: IRVRoundTrace; phase: IRVPhase; winner: string; changed?: boolean;
}) {
  const eliminated = phase === "eliminate" && round.eliminated.includes(candidate);
  const won = phase === "winner" && winner === candidate;
  const count = round.counts[candidate];
  return (
    <td className={cn("px-1 py-3 text-center", (eliminated || won || changed) && "bg-mi-wash")}>
      <span className="font-mi-mono text-xl">{count ?? "—"}</span>
      {eliminated || won || changed || count === undefined ? <span className="mt-1 block text-sm" aria-label={eliminated ? "Eliminated this round" : count === undefined ? "Previously eliminated" : undefined}>{eliminated ? "Out" : won ? "Winner" : changed ? "+2 new" : "Out"}</span> : null}
    </td>
  );
}

function keepArrowsInInspector(event: React.KeyboardEvent) {
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") event.stopPropagation();
}

function SourceCode({ lines, startLine, label, highlight }: {
  lines: string[]; startLine: number; label: string; highlight?: IRVPhase;
}) {
  const indent = Math.min(...lines.filter((line) => line.trim()).map((line) => line.match(/^ */)![0].length));
  const emphasis = {
    count: /vote_counts\[choice\] \+=|_advance_to_active_choice\(/,
    eliminate: /min_votes =|if count == min_votes/,
    transfer: /while index|index \+=|return index, ranking/,
    winner: /majority_threshold =|if count >|winner = candidate/,
  };
  return (
    <div role="region" aria-label={label} tabIndex={0} onKeyDown={keepArrowsInInspector} className="max-h-[22rem] min-w-0 overflow-auto overscroll-contain rounded-[3px] border border-mi-rule bg-mi-wash py-3 focus-visible:outline-2 focus-visible:outline-mi-ink lg:max-h-[28rem]">
      <pre className="w-max min-w-full font-mi-mono text-sm leading-6 text-mi-ink"><code>{lines.map((line, index) => (
        <span key={index} className={cn("block pr-4", highlight && emphasis[highlight].test(line) && "bg-mi-surface font-semibold ring-1 ring-inset ring-mi-rule")}>
          <span aria-hidden className="mr-4 inline-block w-10 select-none text-right font-normal text-mi-muted">{startLine + index}</span>
          <PythonLine line={line.slice(Number.isFinite(indent) ? indent : 0)} />{"\n"}
        </span>
      ))}</code></pre>
    </div>
  );
}

function PythonLine({ line }: { line: string }) {
  if (line.trimStart().startsWith("#")) return <span className="font-normal text-mi-ink-2">{line}</span>;
  return <>{line.split(/(\b(?:if|else|elif|for|in|while|return|None|True|False|break|def)\b)/g).map((part, index) =>
    /^(?:if|else|elif|for|in|while|return|None|True|False|break|def)$/.test(part)
      ? <span key={index} className="text-blue-700 dark:text-blue-300">{part}</span> : part
  )}</>;
}
