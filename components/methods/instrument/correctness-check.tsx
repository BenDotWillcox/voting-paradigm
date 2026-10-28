"use client";

import { Check, Copy, ExternalLink } from "lucide-react";
import { useId, useState, type KeyboardEvent } from "react";

import { CORRECTNESS_CHECK_EXAMPLE, CORRECTNESS_CHECK_EXCERPT } from "@/lib/methods/correctness-example";

const button = "inline-flex min-h-11 items-center justify-center gap-2 rounded-[3px] border border-mi-rule px-3 py-2 text-left text-sm font-medium text-mi-ink hover:bg-mi-wash focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink";

export function CorrectnessCheck() {
  const exampleId = useId();
  const [expanded, setExpanded] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");

  async function copyExample() {
    try {
      await navigator.clipboard.writeText(CORRECTNESS_CHECK_EXAMPLE);
      setCopyStatus("copied");
    } catch {
      setExpanded(true);
      setCopyStatus("failed");
    }
  }

  return (
    <section className="min-w-0 space-y-4 rounded-[4px] border border-mi-rule p-4 sm:p-5" aria-label="A reproducible correctness check">
      <div>
        <p className="text-sm font-medium text-mi-ink-2">Correctness check · a known edge case</p>
        <h3 className="mt-2 text-xl font-semibold leading-snug text-mi-ink">An exact tie should replay the same way.</h3>
        <p className="mt-3 max-w-3xl text-base leading-relaxed text-mi-ink-2">
          A and B receive one vote each. Count twice with a fresh seed-7 tiebreaker, reversing the candidate and ballot order for the second run. Both runs must flag that a tiebreak was used and return B.
        </p>
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,0.75fr)] lg:items-start">
        <div className="min-w-0">
          <p className="mb-2 text-sm text-mi-ink-2">Check excerpt · setup included in the copied example</p>
          <pre tabIndex={0} aria-label="Python assertions for the tied count" onKeyDown={keepArrowsInCode} className="max-w-full overflow-x-auto rounded-[3px] border border-mi-rule bg-mi-wash p-3 font-mi-mono text-sm leading-6 text-mi-ink focus-visible:outline-2 focus-visible:outline-mi-ink"><code>{CORRECTNESS_CHECK_EXCERPT}</code></pre>
        </div>
        <div className="space-y-3">
          <p className="text-sm font-medium text-mi-ink">Expected result when run</p>
          <dl className="space-y-3 rounded-[3px] bg-mi-wash p-3 text-sm text-mi-ink">
            <div className="flex flex-wrap justify-between gap-2"><dt>Both tallies</dt><dd className="font-mi-mono">A: 1 · B: 1</dd></div>
            <div className="flex flex-wrap justify-between gap-2"><dt>Both winners</dt><dd className="font-mi-mono">B</dd></div>
            <div className="flex flex-wrap justify-between gap-2"><dt>Tiebreak used</dt><dd className="font-mi-mono">True</dd></div>
          </dl>
          <p className="text-sm leading-relaxed text-mi-ink-2">This checks one reproducibility guarantee. The simulations above measure behavior across sampled electorates.</p>
          <a href="https://github.com/BenDotWillcox/voting-paradigm/blob/main/voting/tests/test_tiebreak.py" className={button}>Read the tiebreak tests <ExternalLink size={15} aria-hidden /></a>
        </div>
      </div>

      <div className="space-y-3 border-t border-mi-rule pt-4">
        <p className="text-sm leading-relaxed text-mi-ink-2">Save the complete example as <code className="font-mi-mono">tie_check.py</code> in the repository root and run <code className="break-words font-mi-mono">python tie_check.py</code> with Python 3.11+. No API server is needed.</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={copyExample} className={button}>{copyStatus === "copied" ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}{copyStatus === "copied" ? "Copied Python check" : "Copy runnable check"}</button>
          <button type="button" aria-expanded={expanded} aria-controls={exampleId} onClick={() => setExpanded(!expanded)} className={button}>{expanded ? "Hide" : "View"} complete example</button>
        </div>
        <p role="status" className={copyStatus === "failed" ? "text-sm text-mi-ink" : "sr-only"}>{copyStatus === "copied" ? "Runnable Python check copied." : copyStatus === "failed" ? "Clipboard access is unavailable. Select and copy the example below." : ""}</p>
        {expanded && <textarea id={exampleId} aria-label="Runnable Python correctness check" readOnly wrap="off" value={CORRECTNESS_CHECK_EXAMPLE} spellCheck={false} rows={12} onKeyDown={keepArrowsInCode} className="block w-full min-w-0 resize-y rounded-[3px] border border-mi-rule bg-mi-wash p-3 font-mi-mono text-base leading-6 text-mi-ink focus-visible:outline-2 focus-visible:outline-mi-ink" />}
      </div>
    </section>
  );
}

function keepArrowsInCode(event: KeyboardEvent<HTMLElement>) {
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") event.stopPropagation();
}
