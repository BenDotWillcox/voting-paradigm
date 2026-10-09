"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

interface StepState {
  /** Index of the step whose slot contains the trigger line. */
  step: number;
  stepCount: number;
}

const StepContext = React.createContext<StepState>({ step: 0, stepCount: 0 });
/** Kept separate so step-driven graphics don't re-render every scroll frame. */
const ProgressContext = React.createContext(0);

/** Active step for graphics inside a <Scrolly>. */
export function useScrollyStep(): StepState {
  return React.useContext(StepContext);
}

/**
 * 0..1 progress through the active step's slot (from its top to the next
 * step's top). For scrubbed animations; re-renders on every scroll frame.
 */
export function useScrollyProgress(): number {
  return React.useContext(ProgressContext);
}

/**
 * Progress through one specific step's slot: 0 before it, 1 after it, and
 * the live 0..1 value while it is active. For scrubbing a sequence (census
 * years, seat numbers) across a single long step.
 */
export function useScrollyStepProgress(stepIndex: number): number {
  const { step } = useScrollyStep();
  const progress = useScrollyProgress();
  if (step < stepIndex) return 0;
  if (step > stepIndex) return 1;
  return progress;
}

interface ScrollyProps {
  /** The pinned figure. Read state with useScrollyStep / useScrollyProgress. */
  graphic: React.ReactNode;
  /** <ScrollyStep> elements. */
  children: React.ReactNode;
  /**
   * side: graphic pinned beside the prose on wide screens.
   * overlay: graphic pinned full-width, steps scroll over it as cards.
   * stage: on wide screens the graphic fills the viewport and steps pin as
   *   a lower-third caption at the bottom left, inside the graphic (which
   *   should keep that corner clear; see `STAGE_CAPTION`).
   * Narrow screens use one layout for all three: the graphic pins at the
   * top as an opaque band, and each step's card pins just below it, then
   * slides away underneath it, so text never covers the graphic.
   */
  layout?: "side" | "overlay" | "stage";
  /**
   * Viewport fraction (from the top) where a step becomes active. Defaults
   * to mid-screen beside a side graphic, and low on screen in overlay mode
   * so the pinned graphic at the top stays visible while a card is active.
   */
  trigger?: number;
  className?: string;
  /** Accessible name for the section. */
  label?: string;
}

/**
 * Sticky-graphic scrollytelling section. Steps are discovered from the DOM
 * (`[data-scrolly-step]`), so they can be server-rendered prose. The active
 * step gets `data-active` for styling. Measurement runs once on mount and
 * then at most once per animation frame while scrolling.
 */
export function Scrolly({
  graphic,
  children,
  layout = "side",
  trigger,
  className,
  label,
}: ScrollyProps) {
  const rootRef = React.useRef<HTMLElement | null>(null);
  const graphicRef = React.useRef<HTMLDivElement | null>(null);
  const [stepState, setStepState] = React.useState<StepState>({ step: 0, stepCount: 0 });
  const [progress, setProgress] = React.useState(0);
  // The pinned graphic's height: on narrow screens, step cards pin below it.
  const [graphicHeight, setGraphicHeight] = React.useState(0);

  React.useEffect(() => {
    const node = graphicRef.current;
    if (!node) return;
    const observer = new ResizeObserver(() => setGraphicHeight(Math.round(node.offsetHeight)));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  // Each step's text height, as `--step-h` on its slot: a step too tall for
  // the space below its pin pins higher instead, so its end stays readable.
  React.useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const slots = Array.from(root.querySelectorAll<HTMLElement>("[data-scrolly-step]"));
    const observer = new ResizeObserver(() => {
      for (const slot of slots) {
        const content = slot.firstElementChild as HTMLElement | null;
        if (content) slot.style.setProperty("--step-h", `${content.offsetHeight}px`);
      }
    });
    slots.forEach((slot) => slot.firstElementChild && observer.observe(slot.firstElementChild));
    return () => observer.disconnect();
  }, []);

  React.useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    let frame = 0;
    let fallback = 0;
    const wideQuery = window.matchMedia("(min-width: 1024px)");

    const measure = () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(fallback);
      frame = 0;
      fallback = 0;
      const steps = Array.from(root.querySelectorAll<HTMLElement>("[data-scrolly-step]"));
      if (steps.length === 0) return;
      const overlay = layout === "overlay" || !wideQuery.matches;
      const triggerY =
        window.innerHeight * (trigger ?? (overlay ? 0.82 : layout === "stage" ? 0.7 : 0.55));
      const tops = steps.map((el) => el.getBoundingClientRect().top);
      const end = root.getBoundingClientRect().bottom;

      let active = 0;
      for (let i = 0; i < tops.length; i++) if (tops[i] <= triggerY) active = i;
      const slotStart = tops[active];
      // The last step ends when the pinned graphic starts to scroll away
      // (the section's bottom reaching the viewport's), not at the section
      // edge, so a scrubbed finale completes while the graphic is in view.
      const slotEnd =
        active + 1 < tops.length
          ? tops[active + 1]
          : Math.max(slotStart + 1, end - (window.innerHeight - triggerY));
      const nextProgress = clamp01((triggerY - slotStart) / Math.max(1, slotEnd - slotStart));

      steps.forEach((el, i) => el.toggleAttribute("data-active", i === active));
      setStepState((prev) =>
        prev.step === active && prev.stepCount === steps.length
          ? prev
          : { step: active, stepCount: steps.length }
      );
      setProgress((prev) => (Math.abs(prev - nextProgress) < 0.002 ? prev : nextProgress));
    };
    // Measure on the next frame, with a timer fallback for when frames are
    // throttled (an occluded window can report "visible" yet never paint).
    const schedule = () => {
      if (frame || fallback) return;
      frame = window.requestAnimationFrame(measure);
      fallback = window.setTimeout(measure, 150);
    };

    measure();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      window.cancelAnimationFrame(frame);
      window.clearTimeout(fallback);
    };
  }, [trigger, layout]);

  const side = layout === "side";
  const stage = layout === "stage";

  return (
    <StepContext.Provider value={stepState}>
      <ProgressContext.Provider value={progress}>
        <section
          ref={rootRef}
          aria-label={label}
          data-layout={layout}
          // Wide side and stage layouts set steps as plain text, not cards.
          data-steps={side || stage ? "plain" : "card"}
          style={
            graphicHeight ? ({ "--scrolly-graphic": `${graphicHeight}px` } as React.CSSProperties) : undefined
          }
          className={cn(
            "group/scrolly relative mx-auto my-16 max-w-7xl px-4",
            // Gap between steps, and where a step's text pins while its
            // slot scrolls (see ScrollyStep): just below the graphic band on
            // narrow screens.
            "[--scrolly-gap:40svh] [--scrolly-pin:calc(var(--scrolly-graphic,50svh)+0.75rem)]",
            // Keep in step with STAGE_CAPTION (a static class for Tailwind).
            "[--stage-caption:min(420px,34%)]",
            // How visible a wide plain step stays once the next one is active.
            "[--step-dim:0.35]",
            layout === "overlay" && "lg:[--scrolly-pin:56svh]",
            side &&
              "lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16 lg:[--scrolly-gap:32vh] lg:[--scrolly-pin:30vh]",
            // Stage captions pin around the middle of the graphic.
            // Stage captions pin mid-graphic and fade out entirely as they
            // leave, so they never cross the graphic's header.
            stage && "lg:my-8 lg:[--scrolly-gap:24vh] lg:[--scrolly-pin:40vh] lg:[--step-dim:0]",
            className
          )}
        >
          <div
            ref={graphicRef}
            data-scrolly-graphic=""
            className={cn(
              // Narrow: an opaque band above the steps, which pass under it.
              // It spans the section's gutters so no card edge shows beside it.
              "sticky top-0 z-20 -mx-4 flex items-start bg-story-page px-4 pt-4 pb-3",
              "lg:z-0 lg:mx-0 lg:h-svh lg:bg-transparent lg:px-0 lg:pb-6",
              side && "lg:order-2 lg:h-screen lg:items-center lg:self-start lg:py-6",
              // Stage: a frame of about 80% of the screen, centered, so its
              // header sits well below the top edge.
              stage && "lg:items-center lg:py-0"
            )}
          >
            <div className={cn("w-full", stage && "lg:h-[min(80vh,46rem)]")}>{graphic}</div>
          </div>
          <div
            data-scrolly-steps=""
            className={cn(
              "relative z-10 pt-[8svh] pb-[30svh]",
              "lg:-mt-[100svh] lg:pt-[62svh] lg:pb-[20svh]",
              side && "lg:order-1 lg:mt-0 lg:pt-[30vh] lg:pb-[18vh]",
              stage && "lg:w-[var(--stage-caption)] lg:pt-[75vh] lg:pb-[14vh]"
            )}
          >
            {children}
          </div>
        </section>
      </ProgressContext.Provider>
    </StepContext.Provider>
  );
}

/**
 * Stage layout: the caption column's width on wide screens. Graphics in a
 * stage keep this much of their left side clear below their header.
 */
export const STAGE_CAPTION = { maxPx: 420, share: 0.34 } as const;

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}
