import * as React from "react";

import { cn } from "@/lib/utils";

export interface SidenoteSource {
  title: string;
  publisher?: string;
  url: string;
  locator?: string;
}

interface SidenoteProps {
  /** Unique per page; ties the mobile toggle to its note. */
  id: string;
  children?: React.ReactNode;
  sources?: readonly SidenoteSource[];
}

/**
 * A numbered margin note (Tufte-style). On wide screens the note floats into
 * the right margin beside the line it annotates; on narrow screens the number
 * toggles the note open inline. No JavaScript: a visually hidden checkbox
 * drives the toggle, and CSS counters (reset on StoryRoot) number the notes.
 * Must sit inside a paragraph in <Prose>.
 */
export function Sidenote({ id, children, sources }: SidenoteProps) {
  const inputId = `sidenote-${id}`;
  return (
    <>
      <label
        htmlFor={inputId}
        className={cn(
          "cursor-pointer align-super font-sans text-[0.68em] font-semibold text-story-accent",
          "[counter-increment:sidenote] after:content-[counter(sidenote)]",
          "hover:underline"
        )}
      />
      <input
        type="checkbox"
        id={inputId}
        aria-label="Show note"
        className="peer sr-only"
      />
      <span
        className={cn(
          "my-3 hidden rounded-md bg-story-surface p-3 font-sans text-[0.8rem] leading-relaxed text-story-ink-2 ring-1 ring-story-rule",
          "peer-checked:block",
          "xl:float-right xl:clear-right xl:-mr-[19rem] xl:mt-1 xl:block xl:w-64 xl:bg-transparent xl:p-0 xl:ring-0",
          "before:mr-1 before:font-semibold before:text-story-accent before:content-[counter(sidenote)]"
        )}
      >
        {children}
        {sources && sources.length > 0 ? (
          <span className="mt-1 block text-story-muted">
            {sources.map((source, index) => (
              <span key={source.url + index} className="block">
                <a
                  href={source.url}
                  className="underline decoration-story-axis underline-offset-2 hover:text-story-ink"
                >
                  {source.title}
                </a>
                {source.publisher ? `, ${source.publisher}` : null}
                {source.locator ? ` (${source.locator})` : null}
              </span>
            ))}
          </span>
        ) : null}
      </span>
    </>
  );
}
