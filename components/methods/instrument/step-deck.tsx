"use client";

import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { referenceReturn } from "@/lib/methods/sections";
import { cn } from "@/lib/utils";

const RETURN_LABELS: Record<string, string> = {
  comparison: "Back to comparison",
  experiment: "Back to experiment",
  implementation: "Back to implementation",
  testing: "Back to testing",
};

export interface Step {
  id: string;
  /** Index into the deck's chapters. */
  chapter: number;
  /** Short name, for the counter and screen readers. */
  title: string;
  /** Reference material is outside the main demo's next/previous sequence. */
  optional?: boolean;
  content: React.ReactNode;
}

/**
 * One step at a time, at the reader's normal text size. Content flows down
 * the page instead of scaling or scrolling inside a fixed slide. Hidden
 * steps stay mounted so an experiment retains its state when revisited.
 */
export function StepDeck({
  header,
  chapters,
  steps,
  index,
  onIndex,
  keys,
  referenceReturnIndex,
}: {
  header: React.ReactNode;
  chapters: readonly string[];
  steps: Step[];
  index: number;
  onIndex: (index: number) => void;
  /** Whether the arrow keys move between steps (off while a dialog is open). */
  keys: boolean;
  /** Return to the main part that opened a reference; direct links use its chapter default. */
  referenceReturnIndex?: number;
}) {
  const navigation = useRef<HTMLDivElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const stepRefs = useRef<(HTMLElement | null)[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const current = steps[index];
  const optional = Boolean(current?.optional);
  const sequence = steps.flatMap((step, at) => (
    optional ? step.optional && step.chapter === current.chapter : !step.optional
  ) ? [at] : []);
  const position = sequence.indexOf(index);
  const previous = sequence[position - 1];
  const next = sequence[position + 1];
  const defaultReturnId = referenceReturn(current?.id);
  const returnIndex = referenceReturnIndex !== undefined && steps[referenceReturnIndex] && !steps[referenceReturnIndex].optional
    ? referenceReturnIndex
    : steps.findIndex((step) => step.id === defaultReturnId);
  const returnLabel = RETURN_LABELS[steps[returnIndex]?.id ?? ""] ?? "Back to the demo";

  const goTo = useCallback((at: number | undefined) => {
    if (at === undefined || at < 0 || at >= steps.length) return;
    if (menuOpen) menuButton.current?.focus({ preventScroll: true });
    setMenuOpen(false);
    onIndex(at);
  }, [menuOpen, onIndex, steps.length]);

  function labelOf(at: number | undefined) {
    if (at === undefined) return "";
    const step = steps[at];
    if (step.optional) return step.title;
    const part = steps.filter((item) => !item.optional).indexOf(step) + 1;
    return `${part} ${step.title}`;
  }

  useEffect(() => {
    const controls = navigation.current;
    if (controls && controls.getBoundingClientRect().top < 0) controls.scrollIntoView({ block: "start" });
    // A link inside the previous step may have opened this one. Keep focus
    // visible instead of leaving it inside the now-hidden reference panel.
    const focusedStep = document.activeElement?.closest("[data-methods-step]");
    const shown = stepRefs.current[index];
    if (shown && focusedStep && focusedStep !== shown) shown.focus({ preventScroll: true });
  }, [index]);

  useEffect(() => {
    if (!keys) return;
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest(
          "input, textarea, select, button, a, summary, [contenteditable=true], [role=slider], [role=tablist], [role=radiogroup], [role=dialog]"
        )
      ) return;
      const destination = event.key === "ArrowRight" ? next : previous;
      if (destination === undefined) return;
      event.preventDefault();
      goTo(destination);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [keys, previous, next, goTo]);

  return (
    <div aria-label="Voting methods demo">
      {header}
      <div className="mt-4 grid items-start gap-x-6 gap-y-3 xl:grid-cols-[15rem_minmax(0,1fr)] xl:gap-x-8">
        <div className="min-w-0 xl:col-start-2 xl:row-start-1">
          {optional && returnIndex >= 0 ? (
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 text-sm">
              <p className="text-mi-ink-2">Reference · {chapters[current.chapter]}</p>
              <button
                type="button"
                onClick={() => goTo(returnIndex)}
                className="ml-auto inline-flex min-h-11 items-center gap-1.5 rounded-[3px] border border-mi-rule px-3 py-2 text-mi-ink hover:border-mi-ink focus-visible:outline-2 focus-visible:outline-mi-ink"
              >
                <ChevronLeft className="size-4" aria-hidden />
                {returnLabel}
              </button>
            </div>
          ) : null}
          <div ref={navigation} className="scroll-mt-4">
            <div className="hidden h-14 grid-cols-[minmax(0,1fr)_9rem_minmax(0,1fr)] items-center gap-3 xl:grid">
              <NavButton
                direction="previous"
                kind={optional ? "reference" : "part"}
                disabled={previous === undefined}
                label={labelOf(previous)}
                onClick={() => goTo(previous)}
              />
              <p className="text-center text-sm text-mi-ink-2" aria-live="polite">
                {optional ? "Reference" : "Part"} {position + 1} of {sequence.length}
              </p>
              <NavButton
                direction="next"
                kind={optional ? "reference" : "part"}
                disabled={next === undefined}
                label={labelOf(next)}
                onClick={() => goTo(next)}
              />
            </div>
            <div className="flex h-14 items-center gap-2 xl:hidden">
              <ArrowButton label={optional ? "Previous reference" : "Previous part"} disabled={previous === undefined} onClick={() => goTo(previous)}>
                <ChevronLeft className="size-4" />
              </ArrowButton>
              <button
                ref={menuButton}
                type="button"
                aria-expanded={menuOpen}
                aria-controls="methods-step-menu"
                onClick={() => setMenuOpen((open) => !open)}
                title={`${optional ? "Reference · " : ""}${labelOf(index)}`}
                className="flex h-14 min-w-0 flex-1 items-center justify-between gap-2 rounded-[3px] border border-mi-rule px-3 py-2 text-left text-sm text-mi-ink hover:border-mi-ink focus-visible:outline-2 focus-visible:outline-mi-ink"
              >
                <span className="line-clamp-2">{optional ? "Reference · " : ""}{labelOf(index)}</span>
                <ChevronDown className={cn("size-4 shrink-0 transition-transform", menuOpen && "rotate-180")} />
              </button>
              <ArrowButton label={optional ? "Next reference" : "Next part"} disabled={next === undefined} onClick={() => goTo(next)}>
                <ChevronRight className="size-4" />
              </ArrowButton>
            </div>
            <p className="sr-only xl:hidden" aria-live="polite">
              {optional ? "Reference" : "Part"} {position + 1} of {sequence.length}
            </p>
            <nav
              id="methods-step-menu"
              aria-label="Choose a part or reference"
              hidden={!menuOpen}
              className="mt-2 rounded-[3px] border border-mi-rule bg-mi-surface p-3 xl:hidden"
            >
              <StepRail chapters={chapters} steps={steps} index={index} onGo={goTo} />
            </nav>
          </div>
        </div>
        <nav aria-label="Parts and references" className="hidden xl:sticky xl:top-6 xl:col-start-1 xl:row-start-2 xl:block">
          <StepRail chapters={chapters} steps={steps} index={index} onGo={goTo} />
        </nav>
        <div className="min-w-0 xl:col-start-2 xl:row-start-2">
          {steps.map((step, at) => (
            <section
              key={step.id}
              ref={(element) => { stepRefs.current[at] = element; }}
              id={`step-${step.id}`}
              data-methods-step
              role="group"
              aria-roledescription={step.optional ? "reference" : "part"}
              aria-label={step.title}
              hidden={at !== index}
              tabIndex={-1}
              className="relative min-w-0 outline-none"
            >
              {step.content}
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Previous or next, naming the step it goes to. */
function NavButton({ direction, kind, disabled, label, onClick }: {
  direction: "previous" | "next";
  kind: "part" | "reference";
  disabled: boolean;
  label: string;
  onClick: () => void;
}) {
  const next = direction === "next";
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      aria-label={disabled ? undefined : `${next ? "Next" : "Previous"} ${kind}: ${label}`}
      title={disabled ? undefined : label}
      className={cn(
        "flex h-14 min-w-0 items-center gap-2 rounded-[3px] border px-3 py-2 text-sm",
        "focus-visible:outline-2 focus-visible:outline-mi-ink",
        next ? "justify-end text-right" : "justify-start text-left",
        disabled ? "invisible" : next
          ? "border-mi-ink bg-mi-ink text-mi-surface hover:opacity-90"
          : "border-mi-rule text-mi-ink hover:border-mi-ink"
      )}
    >
      {next ? null : <ChevronLeft className="size-4 shrink-0" aria-hidden />}
      <span className="line-clamp-2">{label}</span>
      {next ? <ChevronRight className="size-4 shrink-0" aria-hidden /> : null}
    </button>
  );
}

/** Main chapters and optional references remain directly accessible. */
function StepRail({ chapters, steps, index, onGo }: {
  chapters: readonly string[];
  steps: Step[];
  index: number;
  onGo: (index: number) => void;
}) {
  const current = steps[index]?.chapter ?? 0;
  const firstOptionalChapter = steps.find((step) => step.optional)?.chapter;
  return (
    <ol className="space-y-2">
      {chapters.map((title, at) => {
        const own = steps.flatMap((step, i) => step.chapter === at ? [[step, i] as const] : []);
        if (!own.length) return null;
        const optional = own.every(([step]) => step.optional);
        const open = at === current;
        const expandable = own.length > 1;
        return (
          <li key={title}>
            {at === firstOptionalChapter ? (
              <p className="mt-6 border-t border-mi-rule px-2.5 pt-5 pb-2 text-sm font-medium text-mi-ink-2">Reference material</p>
            ) : null}
            <button
              type="button"
              aria-expanded={expandable ? open : undefined}
              aria-current={!expandable && open ? "step" : undefined}
              onClick={() => onGo(own[0][1])}
              className={cn(
                "flex min-h-11 w-full items-baseline gap-2 rounded-[3px] px-2.5 py-2.5 text-left text-base",
                "focus-visible:outline-2 focus-visible:outline-mi-ink",
                open ? "bg-mi-ink text-mi-surface" : "text-mi-ink hover:bg-mi-wash"
              )}
            >
              {optional ? null : <span className="font-mi-mono text-sm opacity-80">{at + 1}</span>}
              <span className="flex-1">{title}</span>
              {expandable ? <span className="font-mi-mono text-sm opacity-80">{own.length}</span> : null}
            </button>
            {open && expandable ? (
              <ol className="mt-1 mb-2 ml-3 border-l border-mi-rule pl-2">
                {own.map(([step, i], within) => (
                  <li key={step.id}>
                    <button
                      type="button"
                      aria-current={i === index ? "step" : undefined}
                      onClick={() => onGo(i)}
                      className={cn(
                        "flex min-h-11 w-full items-center gap-2 rounded-[3px] border-l-2 px-2 py-2 text-left text-sm",
                        "focus-visible:outline-2 focus-visible:outline-mi-ink",
                        i === index ? "border-mi-ink bg-mi-wash font-medium text-mi-ink" : "border-transparent text-mi-ink-2 hover:text-mi-ink"
                      )}
                    >
                      {optional ? null : <span className="w-8 shrink-0 font-mi-mono text-mi-ink-2">{at + 1}.{within + 1}</span>}
                      <span>{step.title}</span>
                    </button>
                  </li>
                ))}
              </ol>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function ArrowButton({ label, disabled, onClick, children }: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="grid size-11 shrink-0 place-items-center rounded-[3px] border border-mi-rule text-mi-ink hover:border-mi-ink focus-visible:outline-2 focus-visible:outline-mi-ink disabled:opacity-35 disabled:hover:border-mi-rule"
    >
      {children}
    </button>
  );
}

/** A naturally sized step with a claim, its evidence, and optional context. */
export function StepFrame({ number, transition, title, takeaway, intro, aside, children, compact = false }: {
  number: string;
  transition?: React.ReactNode;
  title: string;
  takeaway?: React.ReactNode;
  intro?: React.ReactNode;
  aside?: React.ReactNode;
  children: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={cn("rounded-[4px] border border-mi-rule bg-mi-surface p-4 sm:p-6", !compact && "lg:p-8")}>
      {!compact && <p className="text-sm leading-relaxed text-mi-ink-2">
        <span className="font-mi-mono">{number}</span>
        {transition ? <span> · {transition}</span> : null}
      </p>}
      <h2 className={cn("font-semibold leading-tight tracking-[-0.02em] text-mi-ink", compact ? "text-xl sm:text-2xl" : "mt-2 text-2xl sm:text-3xl")}>{title}</h2>
      {takeaway ? <p className="mt-3 max-w-3xl text-base leading-relaxed text-mi-ink">{takeaway}</p> : null}
      {intro ? <div className="mt-3 max-w-3xl text-base leading-relaxed text-mi-ink-2">{intro}</div> : null}
      <div className={cn("grid gap-6", compact ? "mt-3" : "mt-6", aside && "xl:grid-cols-[minmax(0,1fr)_18rem]")}>
        <div className="min-w-0">{children}</div>
        {aside ? <aside className="space-y-3 text-base leading-relaxed text-mi-ink-2">{aside}</aside> : null}
      </div>
    </div>
  );
}
