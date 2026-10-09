"use client";

import { List, X } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

const CHAPTERS = [
  { id: "top", label: "Start" },
  { id: "act-1", label: "I · One seat, many people" },
  { id: "act-2", label: "II · The freeze" },
  { id: "act-3", label: "III · Dealing the seats" },
  { id: "act-4", label: "IV · Just add seats?" },
  { id: "coda", label: "Back to one person" },
  { id: "what-it-takes", label: "What it would take" },
  { id: "methods", label: "Methods & sources" },
] as const;

const MODE_KEY = "nebula-civitas.apportionment.reading";

/**
 * The essay's way around: a progress line across the top, a table of
 * contents (a rail in the left margin on wide screens, a Contents menu on
 * phones) that jumps to any chapter, and text-only reading (no pinned
 * figures, every step's words in one column; see app/globals.css).
 */
export function StoryNav() {
  const [open, setOpen] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [current, setCurrent] = React.useState(0);
  const [textOnly, setTextOnly] = React.useState(false);

  React.useEffect(() => {
    try {
      setTextOnly(window.localStorage.getItem(MODE_KEY) === "text");
    } catch {
      // No storage: the default mode.
    }
  }, []);

  React.useEffect(() => {
    const root = document.documentElement;
    if (textOnly) root.setAttribute("data-reading", "text");
    else root.removeAttribute("data-reading");
    try {
      window.localStorage.setItem(MODE_KEY, textOnly ? "text" : "scroll");
    } catch {
      // No storage: the mode lasts for this page view.
    }
    // Pinned figures re-measure their steps after the layout changes.
    window.dispatchEvent(new Event("resize"));
    return () => root.removeAttribute("data-reading");
  }, [textOnly]);

  React.useEffect(() => {
    let frame = 0;
    const measure = () => {
      frame = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setProgress(max > 0 ? Math.min(1, window.scrollY / max) : 0);
      // A chapter is current once its start passes the line where scrolly
      // steps become active (Scrolly's trigger), so a jump highlights it.
      const line = window.innerHeight * (window.matchMedia("(min-width: 1024px)").matches ? 0.72 : 0.84);
      let index = 0;
      CHAPTERS.forEach((chapter, i) => {
        const el = document.getElementById(chapter.id);
        if (el && el.getBoundingClientRect().top <= line) index = i;
      });
      setCurrent(index);
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
      window.cancelAnimationFrame(frame);
    };
  }, []);

  const jump = (id: string) => {
    setOpen(false);
    if (id === "top") {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    const el = document.getElementById(id);
    if (!el) return;
    // A scrolly step becomes active when its top reaches the trigger line.
    const step = el.hasAttribute("data-scrolly-step") && !textOnly;
    const wide = window.matchMedia("(min-width: 1024px)").matches;
    const offset = step ? window.innerHeight * (wide ? 0.7 : 0.82) - 4 : 24;
    window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - offset, behavior: "smooth" });
  };

  const textToggle = (
    <label className="flex cursor-pointer items-center gap-2 text-story-ink-2">
      <input type="checkbox" checked={textOnly} onChange={(event) => setTextOnly(event.target.checked)} />
      Text only (no animated figures)
    </label>
  );

  return (
    <>
      <div aria-hidden="true" className="pointer-events-none fixed inset-x-0 top-0 z-40 h-[3px]">
        <div className="h-full bg-story-accent transition-[width] duration-150" style={{ width: `${progress * 100}%` }} />
      </div>

      {/* Wide screens: a rail of ticks in the left margin, one per chapter,
          the current one longer and in ink. Hovering or tabbing in opens
          the names beside it (always shown where the margin has room). Only
          the tick column takes clicks until it opens, so it never covers
          the page. */}
      <nav
        aria-label="Chapters"
        className="group/rail fixed top-1/2 left-2 z-40 hidden -translate-y-1/2 font-sans text-sm lg:block"
      >
        {/* The open panel; invisible (so it takes no clicks) until then. */}
        <div
          aria-hidden="true"
          className="invisible absolute -top-2 -bottom-14 left-0 w-72 rounded-lg bg-story-surface/95 shadow-lg ring-1 ring-story-rule backdrop-blur-sm group-focus-within/rail:visible group-hover/rail:visible"
        />
        <ol className="relative">
          {CHAPTERS.map((chapter, i) => (
            <li key={chapter.id}>
              <button
                type="button"
                onClick={(event) => {
                  jump(chapter.id);
                  // A mouse click closes the rail; keyboard focus stays put.
                  if (event.detail > 0) event.currentTarget.blur();
                }}
                aria-label={chapter.label}
                aria-current={i === current ? "location" : undefined}
                className="relative flex h-7 w-10 items-center pl-2.5"
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "h-[3px] rounded-full transition-[width,background-color] duration-300",
                    i === current ? "w-6 bg-story-ink" : "w-3 bg-story-axis"
                  )}
                />
                <span
                  aria-hidden="true"
                  className={cn(
                    "invisible absolute left-full ml-1 whitespace-nowrap group-focus-within/rail:visible group-hover/rail:visible min-[1680px]:visible",
                    i === current ? "font-semibold text-story-ink" : "text-story-ink-2 hover:text-story-ink"
                  )}
                >
                  {chapter.label}
                </span>
              </button>
            </li>
          ))}
        </ol>
        <div className="invisible absolute top-full left-2.5 mt-3 w-64 border-t border-story-rule pt-2 group-focus-within/rail:visible group-hover/rail:visible">
          {textToggle}
        </div>
      </nav>

      {/* Phones and tablets: the same chapters behind a Contents button. */}
      <nav aria-label="Chapters" className="fixed right-3 bottom-3 z-40 font-sans text-sm lg:hidden">
        {open ? (
          <div className="mb-2 w-72 rounded-lg bg-story-surface p-2 shadow-xl ring-1 ring-story-rule">
            <ol>
              {CHAPTERS.map((chapter, i) => (
                <li key={chapter.id}>
                  <button
                    type="button"
                    onClick={() => jump(chapter.id)}
                    aria-current={i === current ? "location" : undefined}
                    className={cn(
                      "w-full rounded-md px-3 py-1.5 text-left hover:bg-story-page",
                      i === current ? "font-semibold text-story-ink" : "text-story-ink-2"
                    )}
                  >
                    {chapter.label}
                  </button>
                </li>
              ))}
            </ol>
            <div className="mt-2 border-t border-story-rule px-3 pt-2.5 pb-1">{textToggle}</div>
          </div>
        ) : null}
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="ml-auto flex items-center gap-2 rounded-full bg-story-surface px-4 py-2 text-story-ink shadow-lg ring-1 ring-story-rule hover:bg-story-page"
        >
          {open ? <X aria-hidden="true" className="h-4 w-4" /> : <List aria-hidden="true" className="h-4 w-4" />}
          <span className="hidden sm:inline">Contents</span>
          <span className="sr-only sm:hidden">Contents</span>
          <span className="text-story-muted tabular-nums">{Math.round(progress * 100)}%</span>
        </button>
      </nav>
    </>
  );
}
