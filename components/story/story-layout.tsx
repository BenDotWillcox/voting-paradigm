import * as React from "react";

import { storySerif } from "@/lib/story/fonts";
import { cn } from "@/lib/utils";

/**
 * Editorial page primitives. Server components: prose and headings render
 * as static HTML; only figures that animate opt into the client.
 */

export function StoryRoot({
  children,
  className,
  theme,
}: {
  children: React.ReactNode;
  className?: string;
  /**
   * Per-demo visual identity: selects the `[data-story-theme]` token
   * overrides in app/globals.css. Omit for the shared default.
   */
  theme?: "apportionment";
}) {
  return (
    <div
      data-story-theme={theme}
      className={cn(
        "story min-h-screen pb-32 [counter-reset:sidenote]",
        storySerif.variable,
        className
      )}
    >
      {children}
    </div>
  );
}

export function StoryHeader({
  kicker,
  title,
  dek,
  meta,
}: {
  kicker: string;
  title: React.ReactNode;
  dek?: React.ReactNode;
  meta?: React.ReactNode;
}) {
  return (
    <header className="mx-auto max-w-4xl px-4 pt-16 pb-10 sm:pt-24 sm:pb-14">
      <p className="text-sm font-medium tracking-wide text-story-accent">{kicker}</p>
      <h1 className="mt-4 font-story-serif text-4xl leading-[1.08] font-medium tracking-[-0.015em] text-balance sm:text-6xl">
        {title}
      </h1>
      {dek ? (
        <p className="mt-6 max-w-3xl font-story-serif text-xl leading-snug text-pretty text-story-ink-2 sm:text-2xl">
          {dek}
        </p>
      ) : null}
      {meta ? <div className="mt-8 text-sm text-story-muted">{meta}</div> : null}
    </header>
  );
}

/** Reading column: ~65 characters per line, serif body. */
export function Prose({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mx-auto max-w-[38rem] px-4 font-story-serif text-[1.1875rem] leading-[1.7] text-story-ink",
        "[&_p]:my-6 [&_p]:text-pretty",
        "[&_a]:underline [&_a]:decoration-story-axis [&_a]:underline-offset-4 hover:[&_a]:decoration-story-ink",
        "[&_strong]:font-semibold [&_em]:italic",
        "[&_ul]:my-6 [&_ul]:list-disc [&_ul]:pl-6 [&_li]:my-2",
        className
      )}
    >
      {children}
    </div>
  );
}

export function SectionHeading({
  kicker,
  children,
  id,
}: {
  kicker?: string;
  children: React.ReactNode;
  id?: string;
}) {
  return (
    <div className="mx-auto mt-24 mb-2 max-w-[38rem] px-4" id={id}>
      {kicker ? (
        <p className="text-sm font-medium tracking-wide text-story-accent">{kicker}</p>
      ) : null}
      <h2 className="mt-2 font-story-serif text-3xl leading-tight font-medium tracking-[-0.01em] text-balance sm:text-4xl">
        {children}
      </h2>
    </div>
  );
}

/**
 * The single headline number of a section. Sans, proportional figures; the
 * serif never carries data.
 */
export function BigNumber({
  value,
  label,
  note,
}: {
  value: string;
  label: React.ReactNode;
  note?: React.ReactNode;
}) {
  return (
    <div className="mx-auto my-16 max-w-[38rem] px-4">
      <div className="text-6xl leading-none font-semibold tracking-tight text-story-ink sm:text-7xl">
        {value}
      </div>
      <p className="mt-4 font-story-serif text-xl leading-snug text-story-ink-2">{label}</p>
      {note ? <p className="mt-2 text-sm text-story-muted">{note}</p> : null}
    </div>
  );
}
