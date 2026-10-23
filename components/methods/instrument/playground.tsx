"use client";

import { ChevronUp, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

/**
 * "Try it yourself": a tab pinned to the bottom of the screen pulls the full
 * instrument up as a sheet over the page, and closing it returns to the
 * slide. "Advanced controls" opens a drawer for the full electorate editor:
 * from the right on large screens, with the content reflowing beside it,
 * and from the bottom on small ones, so the graphs stay in view while
 * editing. Escape closes the drawer, then the sheet.
 */
export function Playground({
  open,
  onOpenChange,
  advanced,
  onAdvancedChange,
  status,
  drawer,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  advanced: boolean;
  onAdvancedChange: (open: boolean) => void;
  /** A one-line summary of the electorate, beside the title. */
  status: React.ReactNode;
  drawer: React.ReactNode;
  children: React.ReactNode;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const tab = useRef<HTMLButtonElement>(null);
  const sheet = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLElement>(null);
  const wasOpen = useRef(open);

  // Closed parts take no focus or pointer input. Set as properties: React 18
  // drops an unknown boolean attribute.
  useEffect(() => {
    if (sheet.current) sheet.current.inert = !open;
    if (panel.current) panel.current.inert = !advanced;
  }, [open, advanced]);

  // Lock the page behind the sheet, focus the sheet, and hand focus back
  useEffect(() => {
    if (open) {
      const previous = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      heading.current?.focus();
      wasOpen.current = true;
      return () => {
        document.body.style.overflow = previous;
      };
    }
    if (wasOpen.current) {
      wasOpen.current = false;
      tab.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (advanced) onAdvancedChange(false);
      else onOpenChange(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, advanced, onOpenChange, onAdvancedChange]);

  return (
    <>
      <button
        ref={tab}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => onOpenChange(true)}
        className={cn(
          "fixed bottom-0 left-1/2 z-30 inline-flex -translate-x-1/2 items-center gap-2 rounded-t-[6px] border border-b-0 border-mi-ink bg-mi-ink px-5 py-2.5 text-sm font-medium text-mi-surface shadow-lg transition-transform",
          "hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink",
          open && "pointer-events-none translate-y-full"
        )}
      >
        <ChevronUp className="size-4" aria-hidden />
        Try it yourself
      </button>

      <div
        aria-hidden
        onClick={() => onOpenChange(false)}
        className={cn(
          "fixed inset-0 z-40 bg-black/35 transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0"
        )}
      />

      <div
        ref={sheet}
        role="dialog"
        aria-modal="true"
        aria-labelledby="playground-title"
        className={cn(
          "fixed inset-x-0 bottom-0 z-50 flex h-[92dvh] flex-col rounded-t-[10px] border-t border-mi-ink bg-mi-page shadow-2xl transition-transform duration-300",
          open ? "translate-y-0" : "pointer-events-none translate-y-full"
        )}
      >
        <header className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-mi-rule px-4 py-3 sm:px-6">
          <h2
            ref={heading}
            id="playground-title"
            tabIndex={-1}
            className="text-lg font-semibold tracking-[-0.01em] text-mi-ink outline-none"
          >
            Playground
          </h2>
          {/* Its own row on small screens, beside the title on larger ones */}
          <div className="order-last basis-full font-mi-mono text-xs text-mi-ink-2 sm:order-none sm:min-w-0 sm:flex-1 sm:basis-auto">
            {status}
          </div>
          <button
            type="button"
            aria-pressed={advanced}
            onClick={() => onAdvancedChange(!advanced)}
            className={cn(
              "ml-auto inline-flex items-center gap-1.5 rounded-[3px] border px-2.5 py-1 text-sm sm:ml-0",
              advanced
                ? "border-mi-ink bg-mi-ink text-mi-surface"
                : "border-mi-rule text-mi-ink hover:border-mi-ink"
            )}
          >
            <SlidersHorizontal className="size-3.5" aria-hidden />
            Advanced controls
          </button>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Close the playground"
            title="Close the playground"
            className="grid size-8 place-items-center rounded-[3px] text-mi-ink-2 hover:bg-mi-wash hover:text-mi-ink"
          >
            <X className="size-4" />
          </button>
        </header>

        <div className="relative min-h-0 flex-1">
          <div
            className={cn(
              "@container h-full overflow-y-auto px-4 py-5 sm:px-6",
              advanced && "pb-[58dvh] lg:pr-[27rem] lg:pb-5"
            )}
          >
            {children}
          </div>

          <aside
            ref={panel}
            aria-label="Advanced controls"
            className={cn(
              "absolute inset-x-0 bottom-0 flex h-[55dvh] flex-col border-t border-mi-ink bg-mi-surface shadow-[0_-8px_24px_rgb(0_0_0/0.12)] transition-transform duration-300",
              "lg:inset-x-auto lg:top-0 lg:right-0 lg:h-auto lg:w-[26rem] lg:border-t-0 lg:border-l lg:shadow-[-8px_0_24px_rgb(0_0_0/0.08)]",
              advanced ? "translate-x-0 translate-y-0" : "pointer-events-none translate-y-full lg:translate-x-full lg:translate-y-0"
            )}
          >
            <div className="flex shrink-0 items-center justify-between border-b border-mi-rule px-4 py-2.5">
              <p className="text-sm font-medium text-mi-ink">Advanced controls</p>
              <button
                type="button"
                onClick={() => onAdvancedChange(false)}
                aria-label="Close advanced controls"
                title="Close advanced controls"
                className="grid size-7 place-items-center rounded-[3px] text-mi-ink-2 hover:bg-mi-wash hover:text-mi-ink"
              >
                <X className="size-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">{drawer}</div>
          </aside>
        </div>
      </div>
    </>
  );
}
