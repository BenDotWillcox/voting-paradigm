"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

import { useScrollyProgress, useScrollyStep } from "./scrolly";

/**
 * Part of a <ScrollyStep> that appears partway through the step: once the
 * reader has scrolled `at` (0..1) through the step's slot, and from then on.
 * Lets one pinned caption grow as its figure moves on, instead of handing
 * over to a new step. Its space is reserved from the start, so the caption
 * never jumps, and its text is always in the document for assistive tech.
 */
export function ScrollyReveal({
  at,
  children,
  className,
}: {
  at: number;
  children: React.ReactNode;
  className?: string;
}) {
  const ref = React.useRef<HTMLDivElement | null>(null);
  const [index, setIndex] = React.useState<number | null>(null);
  const { step } = useScrollyStep();
  const progress = useScrollyProgress();

  // Which step this sits in, from the DOM (steps are server-rendered).
  React.useEffect(() => {
    const slot = ref.current?.closest("[data-scrolly-step]");
    const root = slot?.parentElement;
    if (!slot || !root) return;
    setIndex(Array.from(root.querySelectorAll(":scope > [data-scrolly-step]")).indexOf(slot));
  }, []);

  const shown = index !== null && (step > index || (step === index && progress >= at));
  return (
    <div
      ref={ref}
      data-scrolly-reveal=""
      className={cn(
        "mt-4 transition-[opacity,translate] duration-500 ease-out",
        shown ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0",
        className
      )}
    >
      {children}
    </div>
  );
}
