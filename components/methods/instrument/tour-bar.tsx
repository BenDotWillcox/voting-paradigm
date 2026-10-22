"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { TOUR } from "@/lib/methods/tour";
import { cn } from "@/lib/utils";

/**
 * The tour: six steps, each loading a preset or a gallery specimen. Moving
 * away from a step's electorate leaves the tour without losing the edit.
 */
export function TourBar({
  step,
  onStep,
}: {
  step: number | null;
  onStep: (step: number) => void;
}) {
  const current = step === null ? null : TOUR[step];
  const button =
    "grid size-8 place-items-center rounded-[3px] border border-mi-rule text-mi-ink hover:bg-mi-wash disabled:opacity-35 disabled:hover:bg-transparent";
  return (
    <section aria-label="Tour" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mi-mono text-xs text-mi-muted">Tour</span>
        <ol className="flex flex-wrap gap-1.5">
          {TOUR.map((s, index) => (
            <li key={s.title}>
              <button
                type="button"
                aria-current={index === step ? "step" : undefined}
                onClick={() => onStep(index)}
                className={cn(
                  "rounded-[3px] border px-2.5 py-1 text-sm",
                  index === step
                    ? "border-mi-ink bg-mi-ink text-mi-surface"
                    : "border-mi-rule bg-mi-surface text-mi-ink hover:border-mi-ink"
                )}
              >
                <span className="mr-1.5 font-mi-mono text-xs opacity-70">{index + 1}</span>
                {s.title}
              </button>
            </li>
          ))}
        </ol>
      </div>
      {current && step !== null ? (
        <div className="flex items-start gap-3">
          <button
            type="button"
            className={button}
            disabled={step === 0}
            onClick={() => onStep(step - 1)}
            aria-label="Previous step"
          >
            <ChevronLeft className="size-4" />
          </button>
          <p className="min-h-[3rem] max-w-3xl flex-1 text-base leading-relaxed text-mi-ink" aria-live="polite">
            {current.caption}
          </p>
          <button
            type="button"
            className={button}
            disabled={step === TOUR.length - 1}
            onClick={() => onStep(step + 1)}
            aria-label="Next step"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>
      ) : (
        <p className="text-sm text-mi-muted">
          Off the tour. Pick a step to return to it.
        </p>
      )}
    </section>
  );
}
