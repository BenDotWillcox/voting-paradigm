"use client";

import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";
import { cn } from "@/lib/utils";

import type { DemoStatus, Readiness } from "./demo-types";

/**
 * The home page's demo grid. Cards show the first lines of their
 * description; pointing at one (or tabbing into it) opens the rest, and the
 * card grows down over the row below rather than pushing it: as the text
 * opens, the cell pulls its bottom margin in by the same amount, in step,
 * so the grid never moves. A sort control reorders the cards by completion,
 * title or real-world readiness, always breaking ties by impressiveness,
 * and the cards glide to their new places.
 */

export interface GridItem {
  id: number;
  title: string;
  status: DemoStatus;
  readiness: Readiness;
  impressiveness: number;
  card: React.ReactNode;
}

type SortKey = "completion" | "title" | "readiness";

const COMPLETION: Record<DemoStatus, number> = { live: 0, "in-progress": 1, planned: 2 };

const SORTS: { key: SortKey; label: string; note: string; compare: (a: GridItem, b: GridItem) => number }[] = [
  {
    key: "completion",
    label: "Completion",
    note: "Live demos first, then those in progress, then planned.",
    compare: (a, b) => COMPLETION[a.status] - COMPLETION[b.status],
  },
  { key: "title", label: "A–Z", note: "By title.", compare: (a, b) => a.title.localeCompare(b.title) },
  {
    key: "readiness",
    label: "Real-world readiness",
    note: "Soonest real-world option first: in use today, then one law away, then needing pilots, then still research.",
    compare: (a, b) => a.readiness - b.readiness,
  },
];

/** How long a card takes to open or close; the CSS transitions on .home-card-description match it. */
const OPEN_MS = 420;

function GridCell({ item, register }: { item: GridItem; register: (id: number, el: HTMLDivElement | null) => void }) {
  const ref = React.useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = React.useState(false);

  const setOpenState = React.useCallback((next: boolean) => {
    const cell = ref.current;
    const text = cell?.querySelector<HTMLElement>(".home-card-description");
    if (!cell || !text) return;
    if (next) {
      // Open to the full text, and pull the cell's bottom in by as much as it grows
      // past its three closed lines (measured from the line height, so a card
      // caught mid-close still opens by the right amount).
      const grow = text.scrollHeight - 3 * parseFloat(getComputedStyle(text).lineHeight);
      if (grow <= 0) return;
      text.style.maxHeight = `${text.scrollHeight}px`;
      cell.style.marginBottom = `${-grow}px`;
    } else {
      text.style.maxHeight = "";
      cell.style.marginBottom = "0px";
    }
    setOpen(next);
  }, []);

  return (
    <div
      ref={(el) => {
        ref.current = el;
        register(item.id, el);
      }}
      className="home-grid-cell"
      data-open={open || undefined}
      data-sketch-avoid
      onPointerEnter={(event) => event.pointerType === "mouse" && setOpenState(true)}
      onPointerLeave={() => open && setOpenState(false)}
      onFocus={() => !open && setOpenState(true)}
      onBlur={(event) => {
        if (open && !ref.current?.contains(event.relatedTarget as Node | null)) setOpenState(false);
      }}
    >
      {item.card}
    </div>
  );
}

export function DemoGrid({ items }: { items: GridItem[] }) {
  const [sort, setSort] = React.useState<SortKey>("completion");
  const reducedMotion = useReducedMotion();
  const cells = React.useRef(new Map<number, HTMLDivElement>());
  const before = React.useRef(new Map<number, DOMRect>());

  const register = React.useCallback((id: number, el: HTMLDivElement | null) => {
    if (el) cells.current.set(id, el);
    else cells.current.delete(id);
  }, []);

  const active = SORTS.find((s) => s.key === sort) ?? SORTS[0];
  const ordered = [...items].sort((a, b) => active.compare(a, b) || a.impressiveness - b.impressiveness);

  const choose = (next: SortKey) => {
    if (next === sort) return;
    // Remember where every card is, so each can glide from there to its new place.
    for (const [id, el] of cells.current) before.current.set(id, el.getBoundingClientRect());
    setSort(next);
  };

  React.useLayoutEffect(() => {
    if (!before.current.size) return;
    if (!reducedMotion) {
      for (const [id, el] of cells.current) {
        const from = before.current.get(id);
        if (!from) continue;
        const to = el.getBoundingClientRect();
        const dx = from.left - to.left;
        const dy = from.top - to.top;
        if (dx || dy) el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }], { duration: 650, easing: "cubic-bezier(0.34, 1.3, 0.64, 1)" });
      }
    }
    before.current.clear();
  }, [sort, reducedMotion]);

  return (
    <section aria-label="Demos" className="mt-10">
      <div className="flex flex-col items-center gap-2 sm:flex-row sm:justify-between">
        <div role="radiogroup" aria-label="Sort demos by" className="inline-flex items-center gap-0.5 rounded-full border border-site-navy/10 bg-white/85 p-1 shadow-[0_1px_2px_rgb(13_23_38/0.06)] backdrop-blur-sm">
          <span className="hidden px-2.5 text-xs font-medium whitespace-nowrap text-site-navy/50 sm:inline">Sort by</span>
          {SORTS.map((option) => (
            <button
              key={option.key}
              type="button"
              role="radio"
              aria-checked={option.key === sort}
              onClick={() => choose(option.key)}
              className={cn(
                "rounded-full px-3 py-1 text-[13px] font-medium whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-site-blue",
                option.key === sort ? "bg-site-navy text-white shadow-sm" : "text-site-navy/70 hover:bg-site-blue/[0.08] hover:text-site-blue"
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p aria-live="polite" className="text-center text-xs text-site-navy/55 sm:text-right">
          {active.note}
        </p>
      </div>

      <div className="home-grid mt-5 grid gap-6 sm:grid-cols-2 xl:grid-cols-3" style={{ "--open-ms": `${OPEN_MS}ms` } as React.CSSProperties}>
        {ordered.map((item) => (
          <GridCell key={item.id} item={item} register={register} />
        ))}
      </div>
    </section>
  );
}
