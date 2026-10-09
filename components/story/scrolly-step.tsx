import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * One prose step in a <Scrolly>. Server-renderable. On narrow screens (and
 * in overlay layout) it is a card floating over the pinned graphic; beside
 * the graphic on wide screens it is plain text that dims when inactive.
 *
 * The step is a slot (its content plus the scroll distance after it) and
 * its content is sticky inside the slot, so the words stay beside the
 * graphic for as long as the graphic is acting them out. The next step's
 * content pushes it away.
 */
export function ScrollyStep({
  children,
  className,
  hold,
  id,
}: {
  children: React.ReactNode;
  className?: string;
  /** Anchor for chapter navigation (jumping here makes this step active). */
  id?: string;
  /**
   * Extra scroll distance after the step, in viewport heights. Lengthens the
   * step's slot for scrubbed sequences; the text stays pinned throughout.
   */
  hold?: number;
}) {
  return (
    <div data-scrolly-step="" id={id} className="group/step">
      <div
        data-scrolly-content=""
        className={cn(
          // The margin keeps a gap when the next step pushes this one away.
          // Pins at --scrolly-pin, or higher if the text would run off the
          // bottom of the screen (--step-h is measured by Scrolly).
          "sticky top-[min(var(--scrolly-pin),calc(100svh_-_var(--step-h,0px)_-_1rem))] mb-10",
          "mx-auto w-full max-w-md rounded-lg bg-story-surface/95 p-5 shadow-sm ring-1 ring-story-rule backdrop-blur-sm",
          "font-story-serif text-lg leading-relaxed text-story-ink [&_p+p]:mt-4",
          "[&_strong]:font-semibold",
          "lg:group-data-[steps=plain]/scrolly:mx-0 lg:group-data-[steps=plain]/scrolly:max-w-none",
          "lg:group-data-[steps=plain]/scrolly:bg-transparent lg:group-data-[steps=plain]/scrolly:p-0",
          "lg:group-data-[steps=plain]/scrolly:shadow-none lg:group-data-[steps=plain]/scrolly:ring-0",
          "lg:group-data-[steps=plain]/scrolly:backdrop-blur-none",
          "lg:group-data-[steps=plain]/scrolly:text-xl lg:group-data-[steps=plain]/scrolly:opacity-[var(--step-dim)]",
          "lg:group-data-[steps=plain]/scrolly:transition-opacity lg:group-data-[steps=plain]/scrolly:duration-300",
          "lg:group-data-[steps=plain]/scrolly:group-data-active/step:opacity-100",
          className
        )}
      >
        {children}
      </div>
      {/* The slot's scroll distance. A real element, not padding: sticky
          content can only travel within its parent's content box. */}
      <div
        aria-hidden="true"
        data-scrolly-spacer=""
        style={{
          height: hold ? `calc(var(--scrolly-gap) + ${hold * 100}svh)` : "var(--scrolly-gap)",
        }}
      />
    </div>
  );
}
