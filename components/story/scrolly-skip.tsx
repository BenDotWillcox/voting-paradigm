"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A button inside a <ScrollyStep> that skips the rest of the step's scrubbed
 * sequence: it scrolls so the next step becomes active (its slot's top at
 * the trigger line), for readers who want the outcome, not the animation.
 */
export function ScrollySkip({ children, className }: { children: React.ReactNode; className?: string }) {
  const ref = React.useRef<HTMLButtonElement | null>(null);
  const skip = () => {
    const slot = ref.current?.closest("[data-scrolly-step]");
    const next = slot?.nextElementSibling;
    if (!(next instanceof HTMLElement)) return;
    const wide = window.matchMedia("(min-width: 1024px)").matches;
    const layout = slot?.closest("[data-layout]")?.getAttribute("data-layout");
    // Keep in step with Scrolly's trigger lines.
    const trigger = layout === "overlay" || !wide ? 0.82 : layout === "stage" ? 0.7 : 0.55;
    const top = next.getBoundingClientRect().top + window.scrollY - window.innerHeight * trigger + 4;
    window.scrollTo({ top, behavior: "smooth" });
  };
  return (
    <button
      ref={ref}
      type="button"
      onClick={skip}
      data-scroll-hint=""
      className={cn(
        "font-sans text-sm text-story-ink-2 underline decoration-story-axis underline-offset-4 hover:text-story-ink",
        className
      )}
    >
      {children}
    </button>
  );
}
