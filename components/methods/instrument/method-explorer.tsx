"use client";

import { ArrowDown, PencilLine } from "lucide-react";
import { useEffect, useRef } from "react";

import type { CountSources } from "@/lib/methods/count-inspector";
import { METHOD_META } from "@/lib/methods/instrument";
import type { StepId } from "@/lib/methods/sections";
import { COUNT_ORDER } from "@/lib/methods/walkthrough";
import { cn } from "@/lib/utils";
import type { ProfileResolveResponse, VotingMethod } from "@/types/methods";

import { MethodCodeInspector } from "./method-code-inspector";
import type { GalleryFailure } from "./method-trace";

const SEGMENT_LABEL: Record<VotingMethod, string> = {
  plurality: "Plurality",
  irv: "Instant runoff",
  borda: "Borda",
  ranked_pairs: "Ranked Pairs",
  approval: "Approval",
  score: "Score",
  quadratic: "Quadratic",
};

/** A method switch, its stages, then actual source and a concrete worked count. */
export function MethodExplorer({ method, onMethod, reference, cycle, useCycle, onCycle, input, onInput, playground, playgroundKey, pendingMessage, onEdit, sources, onReference }: {
  method: VotingMethod;
  onMethod: (method: VotingMethod) => void;
  reference: ProfileResolveResponse;
  cycle?: ProfileResolveResponse;
  useCycle: boolean;
  onCycle: (cycle: boolean) => void;
  input: "reference" | "playground";
  onInput: (input: "reference" | "playground") => void;
  playground?: ProfileResolveResponse;
  playgroundKey: string;
  pendingMessage: string;
  onEdit: () => void;
  sources: CountSources;
  failures?: GalleryFailure[];
  onReference?: (step: StepId) => void;
}) {
  const methodButtons = useRef<Partial<Record<VotingMethod, HTMLButtonElement>>>({});
  const methodStrip = useRef<HTMLDivElement>(null);
  // Changing inputs resets the inspector; retain focus on a control outside it.
  function focusMethod() { methodButtons.current[method]?.focus({ preventScroll: true }); }

  // On narrow screens the methods scroll sideways; keep the selected one in
  // view by scrolling the strip itself, never the page.
  useEffect(() => {
    const strip = methodStrip.current;
    const button = methodButtons.current[method];
    if (!strip || !button || strip.scrollWidth <= strip.clientWidth) return;
    const left = button.offsetLeft - strip.offsetLeft;
    if (left >= strip.scrollLeft && left + button.offsetWidth <= strip.scrollLeft + strip.clientWidth) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    strip.scrollTo({ left: Math.max(0, left - 6), behavior: reduce ? "auto" : "smooth" });
  }, [method]);
  const showingCycle = input === "reference" && method === "ranked_pairs" && useCycle && cycle;
  const resolution = input === "playground" ? playground : showingCycle || reference;
  const context = <div className="min-w-0 space-y-4">
    {input === "reference" && method === "ranked_pairs" && cycle && <div className="flex flex-wrap items-center gap-3">
      <p className="text-sm font-medium text-mi-ink">Ranked Pairs examples</p>
      <div role="group" aria-label="Ranked Pairs examples" className="flex flex-wrap gap-2">
        {[{ label: "Majority cycle", value: true }, { label: "Condorcet winner", value: false }].map((example) => <button key={example.label} type="button" onClick={() => { onCycle(example.value); focusMethod(); }} aria-pressed={useCycle === example.value} className={cn("min-h-11 rounded-md border border-mi-rule px-3 py-2 text-sm font-medium text-mi-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink", useCycle === example.value ? "border-mi-ink bg-mi-wash" : "hover:bg-mi-wash")}>{example.label}</button>)}
      </div>
    </div>}
    <div className="flex flex-col items-start gap-4 rounded-lg bg-mi-wash p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
      <div className="min-w-0 max-w-2xl space-y-1.5">
        <h3 className="text-base font-semibold text-mi-ink">{input === "playground" ? "You’re inspecting your electorate" : "What would your voters choose?"}</h3>
        <p className="text-sm leading-relaxed text-mi-ink-2">{input === "playground" ? "These counts and the runnable Python example use your current voters and preferences. Edit them in the playground to see what changes." : "Choose your own candidates, voter groups, and preferences in the playground below. Compare every method, then bring your counts back here with “Trace this count”."}</p>
      </div>
      <div className="flex w-full shrink-0 flex-col items-stretch gap-2 sm:w-auto sm:items-end">
        <button type="button" onClick={onEdit} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-mi-ink px-4 py-2 text-sm font-medium text-mi-surface hover:bg-mi-ink/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink">{input === "playground" ? <PencilLine size={16} aria-hidden /> : <ArrowDown size={16} aria-hidden />}{input === "playground" ? "Edit your electorate" : "Create a custom electorate"}</button>
        {input === "playground" && <button type="button" onClick={() => { onInput("reference"); focusMethod(); }} className="min-h-11 rounded-md px-2 py-2 text-sm font-medium text-mi-ink underline underline-offset-4 hover:bg-mi-surface focus-visible:outline-2 focus-visible:outline-mi-ink">Return to the example</button>}
      </div>
    </div>
  </div>;

  return <div className="min-w-0 overflow-hidden rounded-xl border border-mi-rule bg-mi-surface">
    <div ref={methodStrip} role="group" aria-label="Choose a voting method" className="flex gap-1 overflow-x-auto overscroll-x-contain border-b border-mi-rule bg-mi-ink p-1.5 [scrollbar-width:none] lg:grid lg:grid-cols-7 lg:overflow-visible [&::-webkit-scrollbar]:hidden">
      {COUNT_ORDER.map((value) => <button type="button" key={value} ref={(element) => { if (element) methodButtons.current[value] = element; }} onClick={() => onMethod(value)} aria-pressed={method === value} title={METHOD_META[value].rule} className={cn("min-h-11 shrink-0 whitespace-nowrap rounded-md px-3.5 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-mi-surface lg:min-h-12 lg:min-w-0 lg:px-2", method === value ? "bg-mi-surface text-mi-ink shadow-sm" : "text-mi-surface/85 hover:bg-mi-surface/15")}>
        {SEGMENT_LABEL[value]}
      </button>)}
    </div>
    {resolution && resolution.results.some((result) => result.method === method) ? <MethodCodeInspector key={`${method}-${input === "playground" ? playgroundKey : showingCycle ? "cycle" : "reference"}`} method={method} resolution={resolution} source={sources[method]} sourceLabel={input === "playground" ? "Playground Python result" : "Recorded Python result"} context={context} /> : <div className="space-y-4 p-4 sm:p-6">{context}<p role="status" className="rounded-md bg-mi-wash p-4 text-base leading-relaxed text-mi-ink">{resolution ? "This input does not support the selected method. Choose another method or edit the electorate." : pendingMessage}</p></div>}
    {onReference && <div className="border-t border-mi-rule px-4 py-2 sm:px-6"><button type="button" onClick={() => onReference("comparison")} className="min-h-11 py-2 text-left text-sm font-medium text-mi-ink underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-mi-ink">Why can these methods disagree? <span aria-hidden>↓</span></button></div>}
  </div>;
}
