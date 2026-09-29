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

interface ScrollyProps {
  /** The pinned figure. Read state with useScrollyStep / useScrollyProgress. */
  graphic: React.ReactNode;
  /** <ScrollyStep> elements. */
  children: React.ReactNode;
  /**
   * side: graphic pinned beside the prose on wide screens.
   * overlay: graphic pinned full-width, steps scroll over it as cards.
   * Narrow screens always use overlay.
   */
  layout?: "side" | "overlay";
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
  const [stepState, setStepState] = React.useState<StepState>({ step: 0, stepCount: 0 });
  const [progress, setProgress] = React.useState(0);

  React.useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    let frame = 0;
    const wideQuery = window.matchMedia("(min-width: 1024px)");

    const measure = () => {
      frame = 0;
      const steps = Array.from(root.querySelectorAll<HTMLElement>("[data-scrolly-step]"));
      if (steps.length === 0) return;
      const overlay = layout === "overlay" || !wideQuery.matches;
      const triggerY = window.innerHeight * (trigger ?? (overlay ? 0.82 : 0.55));
      const tops = steps.map((el) => el.getBoundingClientRect().top);
      const end = root.getBoundingClientRect().bottom;

      let active = 0;
      for (let i = 0; i < tops.length; i++) if (tops[i] <= triggerY) active = i;
      const slotStart = tops[active];
      const slotEnd = active + 1 < tops.length ? tops[active + 1] : end;
      const nextProgress = clamp01((triggerY - slotStart) / Math.max(1, slotEnd - slotStart));

      steps.forEach((el, i) => el.toggleAttribute("data-active", i === active));
      setStepState((prev) =>
        prev.step === active && prev.stepCount === steps.length
          ? prev
          : { step: active, stepCount: steps.length }
      );
      setProgress((prev) => (Math.abs(prev - nextProgress) < 0.002 ? prev : nextProgress));
    };
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(measure);
    };

    measure();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [trigger, layout]);

  const side = layout === "side";

  return (
    <StepContext.Provider value={stepState}>
      <ProgressContext.Provider value={progress}>
        <section
          ref={rootRef}
          aria-label={label}
          data-layout={layout}
          className={cn(
            "group/scrolly relative mx-auto my-16 max-w-7xl px-4",
            side && "lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16",
            className
          )}
        >
          <div
            className={cn(
              "sticky top-0 flex h-svh items-start pt-4 pb-6",
              side && "lg:order-2 lg:h-screen lg:items-center lg:self-start lg:py-6"
            )}
          >
            <div className="w-full">{graphic}</div>
          </div>
          <div
            className={cn(
              "relative z-10 -mt-[100svh] pt-[70svh] pb-[45svh]",
              "flex flex-col gap-[75svh]",
              side && "lg:order-1 lg:mt-0 lg:pt-[45vh] lg:pb-[50vh] lg:gap-[65vh]"
            )}
          >
            {children}
          </div>
        </section>
      </ProgressContext.Provider>
    </StepContext.Provider>
  );
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}
