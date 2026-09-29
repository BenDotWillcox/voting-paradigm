import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * One prose step in a <Scrolly>. Server-renderable. On narrow screens (and
 * in overlay layout) it is a card floating over the pinned graphic; beside
 * the graphic on wide screens it is plain text that dims when inactive.
 */
export function ScrollyStep({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      data-scrolly-step=""
      className={cn(
        "mx-auto w-full max-w-md rounded-lg bg-story-surface/95 p-5 shadow-sm ring-1 ring-story-rule backdrop-blur-sm",
        "font-story-serif text-lg leading-relaxed text-story-ink [&_p+p]:mt-4",
        "[&_strong]:font-semibold",
        "lg:group-data-[layout=side]/scrolly:mx-0 lg:group-data-[layout=side]/scrolly:max-w-none",
        "lg:group-data-[layout=side]/scrolly:bg-transparent lg:group-data-[layout=side]/scrolly:p-0",
        "lg:group-data-[layout=side]/scrolly:shadow-none lg:group-data-[layout=side]/scrolly:ring-0",
        "lg:group-data-[layout=side]/scrolly:backdrop-blur-none",
        "lg:group-data-[layout=side]/scrolly:text-xl lg:group-data-[layout=side]/scrolly:opacity-35",
        "lg:group-data-[layout=side]/scrolly:transition-opacity lg:group-data-[layout=side]/scrolly:duration-300",
        "lg:group-data-[layout=side]/scrolly:data-active:opacity-100",
        className
      )}
    >
      {children}
    </div>
  );
}
