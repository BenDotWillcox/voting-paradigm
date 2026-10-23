"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export interface Step {
  id: string;
  /** Index into the deck's chapters. */
  chapter: number;
  /** Short name, for the counter and screen readers. */
  title: string;
  content: React.ReactNode;
}

// After the last scroll event, wait this long before reading the step
const SETTLE_MS = 120;
// Longest a chosen step's scroll may take before a reading counts again
const SCROLL_GRACE_MS = 2000;
// From this width up, each step is sized to the screen below the deck's top
const FIT_QUERY = "(min-width: 1024px)";
// Room kept below a fitted step for the pinned "Try it yourself" tab
const BOTTOM_ROOM = 64;
// A fitted step is never shorter than this, however short the window
const MIN_STEP_HEIGHT = 320;

/**
 * The chapters and their steps, one step at a time. Steps sit in a horizontal
 * scroll-snap track, so trackpads and touch swipe between them; the arrows,
 * the arrow keys anywhere outside a control, and the chapter tabs (arrow
 * keys, Home, End) move through them. On large screens each step fills the
 * window below the deck, so a step reads without scrolling the page; content
 * still too tall for that scrolls inside its step. On small screens the
 * track takes the height of the step showing. Steps off screen are inert.
 */
export function StepDeck({
  chapters,
  steps,
  index,
  onIndex,
  keys,
}: {
  chapters: readonly string[];
  steps: Step[];
  index: number;
  onIndex: (index: number) => void;
  /** Whether the arrow keys move between steps (off while a dialog is open). */
  keys: boolean;
}) {
  const root = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const stepRefs = useRef<(HTMLElement | null)[]>([]);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const settle = useRef<number | null>(null);
  // A scroll this deck started, so readings on the way are not taken as swipes
  const heading = useRef<{ target: number; until: number } | null>(null);
  // Fitted to the window on large screens; null follows the step's own height
  const [fitted, setFitted] = useState<number | null>(null);
  const [natural, setNatural] = useState<number | null>(null);

  const chapter = steps[index]?.chapter ?? 0;
  const inChapter = steps.filter((step) => step.chapter === chapter);
  const position = inChapter.findIndex((step) => step === steps[index]);

  const go = useCallback(
    (next: number) => onIndex(Math.max(0, Math.min(steps.length - 1, next))),
    [onIndex, steps.length]
  );

  // Scroll to the chosen step unless a swipe already brought it into view,
  // start it from its top, and bring the deck back into view
  useEffect(() => {
    const element = track.current;
    if (!element) return;
    const target = index * element.clientWidth;
    if (Math.abs(element.scrollLeft - target) > 2) {
      heading.current = { target, until: performance.now() + SCROLL_GRACE_MS };
      element.scrollTo({ left: target, behavior: "smooth" });
    }
    stepRefs.current[index]?.scrollTo({ top: 0 });
    const deck = root.current;
    if (deck && deck.getBoundingClientRect().top < 0) deck.scrollIntoView({ block: "start" });
  }, [index]);

  // On large screens a step fills the window from the track's top down
  const measure = useCallback(() => {
    const element = track.current;
    if (!element) return;
    if (!window.matchMedia(FIT_QUERY).matches) {
      setFitted(null);
      return;
    }
    const top = element.getBoundingClientRect().top + window.scrollY;
    setFitted(Math.max(MIN_STEP_HEIGHT, Math.floor(window.innerHeight - top - BOTTOM_ROOM)));
  }, []);

  // The page's header collapses after the first step, which moves the track
  // without resizing the page (it is at least a screen tall), so measure on
  // every step as well as when the page or the window changes
  useEffect(measure, [index, measure]);
  useEffect(() => {
    const query = window.matchMedia(FIT_QUERY);
    const observer = new ResizeObserver(measure);
    observer.observe(document.body);
    window.addEventListener("resize", measure);
    query.addEventListener("change", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
      query.removeEventListener("change", measure);
    };
  }, [measure]);

  // On small screens the track is as tall as the step showing
  useEffect(() => {
    const step = stepRefs.current[index];
    if (!step || fitted !== null) return;
    const observer = new ResizeObserver(() => setNatural(step.offsetHeight));
    observer.observe(step);
    return () => observer.disconnect();
  }, [index, fitted]);

  // Keep the step in place when the track's width changes; its height
  // changes with every step and must not interrupt a scroll
  const width = useRef(0);
  useEffect(() => {
    const element = track.current;
    if (!element) return;
    const observer = new ResizeObserver(() => {
      if (element.clientWidth === width.current) return;
      width.current = element.clientWidth;
      element.scrollTo({ left: index * element.clientWidth });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [index]);

  // The arrow keys step through the deck, except where a control uses them
  useEffect(() => {
    if (!keys) return;
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest(
          "input, textarea, select, [contenteditable=true], [role=slider], [role=tablist], [role=radiogroup], [role=dialog]"
        )
      ) {
        return;
      }
      event.preventDefault();
      go(index + (event.key === "ArrowRight" ? 1 : -1));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [keys, index, go]);

  function goToChapter(next: number) {
    const first = steps.findIndex((step) => step.chapter === next);
    if (first >= 0) go(first);
  }

  function onTabKey(event: React.KeyboardEvent, at: number) {
    const moves: Record<string, number> = {
      ArrowLeft: at - 1,
      ArrowRight: at + 1,
      Home: 0,
      End: chapters.length - 1,
    };
    const next = moves[event.key];
    if (next === undefined) return;
    event.preventDefault();
    const clamped = Math.max(0, Math.min(chapters.length - 1, next));
    goToChapter(clamped);
    tabRefs.current[clamped]?.focus();
  }

  const height = fitted ?? natural;

  return (
    <div ref={root} aria-roledescription="carousel" aria-label="Steps">
      <div className="flex items-center gap-2">
        <ArrowButton label="Previous step" disabled={index === 0} onClick={() => go(index - 1)}>
          <ChevronLeft className="size-4" />
        </ArrowButton>
        <div
          role="tablist"
          aria-label="Chapters"
          className="flex min-w-0 flex-1 gap-1 overflow-x-auto [scrollbar-width:none]"
        >
          {chapters.map((title, at) => (
            <button
              key={title}
              ref={(element) => {
                tabRefs.current[at] = element;
              }}
              type="button"
              role="tab"
              aria-selected={at === chapter}
              aria-controls={`step-${steps[index]?.id}`}
              tabIndex={at === chapter ? 0 : -1}
              onClick={() => goToChapter(at)}
              onKeyDown={(event) => onTabKey(event, at)}
              className={cn(
                "shrink-0 rounded-[3px] px-2.5 py-1 text-sm whitespace-nowrap",
                "focus-visible:outline-1 focus-visible:outline-offset-1 focus-visible:outline-mi-ink",
                at === chapter
                  ? "bg-mi-ink text-mi-surface"
                  : "text-mi-ink-2 hover:bg-mi-wash hover:text-mi-ink"
              )}
            >
              <span className="mr-1.5 font-mi-mono text-xs opacity-70">{at + 1}</span>
              {title}
            </button>
          ))}
        </div>
        <span className="hidden shrink-0 font-mi-mono text-xs text-mi-muted sm:inline" aria-live="polite">
          Step {position + 1} of {inChapter.length}
        </span>
        <ArrowButton
          label="Next step"
          disabled={index === steps.length - 1}
          onClick={() => go(index + 1)}
        >
          <ChevronRight className="size-4" />
        </ArrowButton>
      </div>

      <div
        ref={track}
        className="mt-3 flex snap-x snap-mandatory items-start overflow-x-auto overflow-y-hidden overscroll-x-contain transition-[height] duration-300 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        style={height === null ? undefined : { height }}
        onScroll={() => {
          if (settle.current) window.clearTimeout(settle.current);
          settle.current = window.setTimeout(() => {
            const element = track.current;
            if (!element) return;
            const scroll = heading.current;
            if (scroll) {
              const arrived = Math.abs(element.scrollLeft - scroll.target) <= 2;
              if (!arrived && performance.now() < scroll.until) return;
              heading.current = null;
            }
            const showing = Math.round(element.scrollLeft / element.clientWidth);
            if (showing !== index) onIndex(showing);
          }, SETTLE_MS);
        }}
      >
        {steps.map((step, at) => (
          <section
            key={step.id}
            ref={(element) => {
              stepRefs.current[at] = element;
              // Off-screen steps take no focus or pointer input. Set as a
              // property: React 18 drops an unknown boolean attribute.
              if (element) element.inert = at !== index;
            }}
            id={`step-${step.id}`}
            role="group"
            aria-roledescription="step"
            aria-label={step.title}
            // Relative, so absolutely positioned content (screen-reader
            // labels among it) is clipped by the track, not the page
            className={cn(
              "relative w-full shrink-0 snap-start snap-always px-px",
              fitted !== null && "overflow-y-auto overscroll-y-contain"
            )}
            style={fitted === null ? undefined : { height: fitted }}
          >
            {step.content}
          </section>
        ))}
      </div>
    </div>
  );
}

function ArrowButton({
  label,
  disabled,
  onClick,
  children,
}: {
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
      className="grid size-8 shrink-0 place-items-center rounded-[3px] border border-mi-rule text-mi-ink hover:border-mi-ink focus-visible:outline-1 focus-visible:outline-mi-ink disabled:opacity-35 disabled:hover:border-mi-rule"
    >
      {children}
    </button>
  );
}

/**
 * One step's frame: a kicker with its number and the transition from the
 * step before, the claim the step proves and its takeaway, an intro on how
 * to read it, the content, and a side column for an explainer. It fills its
 * step, so a short step still reads as a full screen.
 */
export function StepFrame({
  number,
  transition,
  title,
  takeaway,
  intro,
  aside,
  children,
}: {
  number: string;
  transition?: React.ReactNode;
  title: string;
  takeaway?: React.ReactNode;
  intro?: React.ReactNode;
  aside?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-full rounded-[4px] border border-mi-rule bg-mi-surface p-4 sm:p-6">
      <p className="text-xs text-mi-muted">
        <span className="font-mi-mono">{number}</span>
        {transition ? <span> · {transition}</span> : null}
      </p>
      <h2 className="mt-1 text-2xl font-semibold tracking-[-0.02em] text-mi-ink">{title}</h2>
      {takeaway ? <p className="mt-2 max-w-3xl text-base leading-relaxed text-mi-ink">{takeaway}</p> : null}
      {intro ? <div className="mt-2 max-w-3xl text-sm leading-relaxed text-mi-ink-2">{intro}</div> : null}
      <div className={cn("mt-5 grid gap-6", aside && "lg:grid-cols-[minmax(0,1fr)_18rem]")}>
        <div className="min-w-0">{children}</div>
        {aside ? <aside className="space-y-3 text-sm leading-relaxed text-mi-ink-2">{aside}</aside> : null}
      </div>
    </div>
  );
}
