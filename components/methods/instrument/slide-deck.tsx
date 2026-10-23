"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export interface Slide {
  id: string;
  title: string;
  content: React.ReactNode;
}

// After the last scroll event, wait this long before reading the slide
const SETTLE_MS = 120;
// Longest a chosen slide's scroll may take before a reading counts again
const SCROLL_GRACE_MS = 2000;

/**
 * The sections, one at a time. Slides sit in a horizontal scroll-snap track,
 * so trackpads and touch swipe between them; the arrows, the dots and the
 * section tabs (arrow keys, Home, End) move by one. Slides off screen are
 * inert, and the track takes the height of the slide showing.
 */
export function SlideDeck({
  slides,
  index,
  onIndex,
}: {
  slides: Slide[];
  index: number;
  onIndex: (index: number) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const slideRefs = useRef<(HTMLElement | null)[]>([]);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const settle = useRef<number | null>(null);
  // A scroll this deck started, so readings on the way are not taken as swipes
  const heading = useRef<{ target: number; until: number } | null>(null);
  const [height, setHeight] = useState<number | null>(null);

  // Scroll to the chosen slide unless a swipe already brought it into view
  useEffect(() => {
    const element = track.current;
    if (!element) return;
    const target = index * element.clientWidth;
    if (Math.abs(element.scrollLeft - target) > 2) {
      heading.current = { target, until: performance.now() + SCROLL_GRACE_MS };
      element.scrollTo({ left: target, behavior: "smooth" });
    }
  }, [index]);

  // The track is as tall as the slide showing, and follows it as it grows
  useEffect(() => {
    const slide = slideRefs.current[index];
    if (!slide) return;
    const observer = new ResizeObserver(() => setHeight(slide.offsetHeight));
    observer.observe(slide);
    return () => observer.disconnect();
  }, [index]);

  // Keep the slide in place when the track's width changes; its height
  // changes with every slide and must not interrupt a scroll
  const width = useRef(0);
  useEffect(() => {
    const element = track.current;
    if (!element) return;
    const observer = new ResizeObserver(() => {
      if (element.clientWidth === width.current) return;
      width.current = element.clientWidth;
      element.scrollTo({ left: index * element.clientWidth });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [index]);

  function go(next: number) {
    onIndex(Math.max(0, Math.min(slides.length - 1, next)));
  }

  function onTabKey(event: React.KeyboardEvent, position: number) {
    const moves: Record<string, number> = {
      ArrowLeft: position - 1,
      ArrowRight: position + 1,
      Home: 0,
      End: slides.length - 1,
    };
    const next = moves[event.key];
    if (next === undefined) return;
    event.preventDefault();
    const clamped = Math.max(0, Math.min(slides.length - 1, next));
    go(clamped);
    tabRefs.current[clamped]?.focus();
  }

  return (
    <div aria-roledescription="carousel" aria-label="Sections">
      <div className="flex items-center gap-2">
        <ArrowButton label="Previous section" disabled={index === 0} onClick={() => go(index - 1)}>
          <ChevronLeft className="size-4" />
        </ArrowButton>
        <div
          role="tablist"
          aria-label="Sections"
          className="flex min-w-0 flex-1 gap-1 overflow-x-auto [scrollbar-width:none]"
        >
          {slides.map((slide, position) => (
            <button
              key={slide.id}
              ref={(element) => {
                tabRefs.current[position] = element;
              }}
              type="button"
              role="tab"
              id={`tab-${slide.id}`}
              aria-selected={position === index}
              aria-controls={`slide-${slide.id}`}
              tabIndex={position === index ? 0 : -1}
              onClick={() => go(position)}
              onKeyDown={(event) => onTabKey(event, position)}
              className={cn(
                "shrink-0 rounded-[3px] px-2.5 py-1 text-sm whitespace-nowrap",
                "focus-visible:outline-1 focus-visible:outline-offset-1 focus-visible:outline-mi-ink",
                position === index
                  ? "bg-mi-ink text-mi-surface"
                  : "text-mi-ink-2 hover:bg-mi-wash hover:text-mi-ink"
              )}
            >
              <span className="mr-1.5 font-mi-mono text-xs opacity-70">
                {String(position + 1).padStart(2, "0")}
              </span>
              {slide.title}
            </button>
          ))}
        </div>
        <ArrowButton
          label="Next section"
          disabled={index === slides.length - 1}
          onClick={() => go(index + 1)}
        >
          <ChevronRight className="size-4" />
        </ArrowButton>
      </div>

      <div
        ref={track}
        className="mt-4 flex snap-x snap-mandatory items-start overflow-x-auto overflow-y-hidden overscroll-x-contain transition-[height] duration-300 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        style={height === null ? undefined : { height }}
        onScroll={() => {
          if (settle.current) window.clearTimeout(settle.current);
          settle.current = window.setTimeout(() => {
            const element = track.current;
            if (!element) return;
            const scroll = heading.current;
            if (scroll) {
              const arrived = Math.abs(element.scrollLeft - scroll.target) <= 2;
              if (!arrived && performance.now() < scroll.until) return;
              heading.current = null;
            }
            const showing = Math.round(element.scrollLeft / element.clientWidth);
            if (showing !== index) onIndex(showing);
          }, SETTLE_MS);
        }}
      >
        {slides.map((slide, position) => (
          <section
            key={slide.id}
            ref={(element) => {
              slideRefs.current[position] = element;
              // Off-screen slides take no focus or pointer input. Set as a
              // property: React 18 drops an unknown boolean attribute.
              if (element) element.inert = position !== index;
            }}
            id={`slide-${slide.id}`}
            role="tabpanel"
            aria-roledescription="slide"
            aria-labelledby={`tab-${slide.id}`}
            // Relative, so absolutely positioned content (screen-reader
            // labels among it) is clipped by the track, not the page
            className="relative w-full shrink-0 snap-start snap-always px-px"
          >
            {slide.content}
          </section>
        ))}
      </div>

      <div className="mt-4 flex justify-center gap-1.5" aria-hidden>
        {slides.map((slide, position) => (
          <button
            key={slide.id}
            type="button"
            tabIndex={-1}
            onClick={() => go(position)}
            className={cn(
              "h-1.5 rounded-full transition-all",
              position === index ? "w-5 bg-mi-ink" : "w-1.5 bg-mi-rule hover:bg-mi-muted"
            )}
          />
        ))}
      </div>
    </div>
  );
}

function ArrowButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="grid size-8 shrink-0 place-items-center rounded-[3px] border border-mi-rule text-mi-ink hover:border-mi-ink focus-visible:outline-1 focus-visible:outline-mi-ink disabled:opacity-35 disabled:hover:border-mi-rule"
    >
      {children}
    </button>
  );
}

/**
 * One slide's frame: a kicker with the transition from the slide before, the
 * claim the graph proves and its takeaway, an intro on how to read the graph,
 * the graph, and a side column for the explainer.
 */
export function SlideFrame({
  number,
  transition,
  title,
  takeaway,
  intro,
  aside,
  children,
}: {
  number: number;
  transition?: React.ReactNode;
  title: string;
  takeaway?: React.ReactNode;
  intro?: React.ReactNode;
  aside?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-[4px] border border-mi-rule bg-mi-surface p-4 sm:p-6">
      <p className="text-xs text-mi-muted">
        <span className="font-mi-mono">{String(number).padStart(2, "0")}</span>
        {transition ? <span> · {transition}</span> : null}
      </p>
      <h2 className="mt-1 text-2xl font-semibold tracking-[-0.02em] text-mi-ink">{title}</h2>
      {takeaway ? <p className="mt-2 max-w-3xl text-base leading-relaxed text-mi-ink">{takeaway}</p> : null}
      {intro ? <div className="mt-2 max-w-3xl text-sm leading-relaxed text-mi-ink-2">{intro}</div> : null}
      <div className={cn("mt-5 grid gap-6", aside && "lg:grid-cols-[minmax(0,1fr)_18rem]")}>
        <div className="min-w-0">{children}</div>
        {aside ? <aside className="space-y-3 text-sm leading-relaxed text-mi-ink-2">{aside}</aside> : null}
      </div>
    </div>
  );
}
