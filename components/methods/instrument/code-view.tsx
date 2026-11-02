"use client";

import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";

import { pythonTokens, type ListingRow, type RowState, type TokenKind } from "@/lib/methods/code-listing";
import { cn } from "@/lib/utils";

export const TOKEN_CLASS: Record<TokenKind, string> = {
  plain: "text-mi-code-plain",
  keyword: "text-mi-code-keyword",
  number: "text-mi-code-number",
  call: "text-mi-code-call",
  type: "text-mi-code-type",
  string: "text-mi-code-string",
  comment: "text-mi-code-comment",
};

/**
 * Package source in a dark editor. With `states`, lines outside the stage
 * drop to one grey, the stage's lines keep their syntax colors, and the
 * driving lines get a tint and a red bar that slides between stages. Every
 * change is a stage the reader chose; reduced motion removes the slide.
 * Long lines wrap under their own indent, so narrow screens see whole lines.
 */
export function CodeView({ rows, states, notes = {}, label, className }: {
  rows: ListingRow[];
  states?: RowState[];
  notes?: Record<number, string>;
  label: string;
  className?: string;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const code = useRef<HTMLPreElement>(null);
  const [markerTop, setMarkerTop] = useState<number | null>(null);
  const drive = states?.flatMap((state, index) => state === "drive" ? [index] : []) ?? [];
  const stage = states?.flatMap((state, index) => state !== "context" ? [index] : []) ?? [];
  const marker = drive[drive.length - 1] ?? stage[0];
  const first = drive[0] ?? stage[0];

  // Wrapped rows vary in height, so the marker follows its row's measured top.
  useLayoutEffect(() => {
    const element = code.current;
    if (!element || marker === undefined) { setMarkerTop(null); return; }
    const measure = () => setMarkerTop(element.querySelector<HTMLElement>(`[data-row="${marker}"]`)?.offsetTop ?? null);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [marker, rows]);

  // Keep the stage in view by scrolling the editor, never the page.
  useEffect(() => {
    const box = scroller.current;
    if (!box || first === undefined) return;
    const top = box.querySelector<HTMLElement>(`[data-row="${first}"]`);
    const bottom = box.querySelector<HTMLElement>(`[data-row="${marker ?? first}"]`);
    if (!top || !bottom) return;
    const start = top.offsetTop;
    const end = bottom.offsetTop + bottom.offsetHeight;
    if (start >= box.scrollTop && end <= box.scrollTop + box.clientHeight) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    box.scrollTo({ top: Math.max(0, start - 2 * top.offsetHeight), behavior: reduce ? "auto" : "smooth" });
  }, [first, marker]);

  return (
    <div ref={scroller} role="region" aria-label={label} tabIndex={0} onKeyDown={keepArrowsInCode} className={cn("max-h-[22rem] min-w-0 overflow-auto overscroll-contain rounded-[4px] bg-mi-code py-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink lg:max-h-[28rem]", className)}>
      <pre ref={code} className="relative font-mi-mono text-[0.8125rem] leading-6 sm:text-sm"><code>
        {markerTop !== null && <span aria-hidden className="absolute left-1 top-1 h-4 w-[3px] bg-mi-code-run motion-safe:transition-transform motion-safe:duration-300 motion-safe:ease-out sm:left-1.5" style={{ transform: `translateY(${markerTop}px)` }} />}
        {rows.map((row, index) => {
          const state = states?.[index] ?? "stage";
          const note = notes[index];
          const indent = row.kind === "line" ? row.text.length - row.text.trimStart().length : 0;
          return (
            <span key={index} data-row={index} className={cn("flex pr-3 motion-safe:transition-colors motion-safe:duration-300 sm:pr-6", state === "drive" ? "bg-mi-code-drive" : "bg-transparent")}>
              <span aria-hidden className="w-9 shrink-0 select-none pr-3 text-right text-mi-code-comment sm:w-16 sm:pr-4">{row.kind === "line" ? row.number : ""}</span>
              {/* Continuation lines hang four columns past the line's own indent; the
                  leading spaces stay real text, so copied code keeps its indentation. */}
              <span className="min-w-0 flex-1 whitespace-pre-wrap break-words" style={{ paddingLeft: `${indent + 4}ch`, textIndent: `-${indent + 4}ch` }}>
                {row.kind === "fold"
                  ? <span className="italic text-mi-code-comment">⋯ lines {row.from}–{row.to}</span>
                  : pythonTokens(row.text).map((token, tokenIndex) => <span key={tokenIndex} className={cn("motion-safe:transition-colors motion-safe:duration-300", state === "context" && token.kind !== "comment" ? "text-mi-code-dim" : TOKEN_CLASS[token.kind])}>{token.text}</span>)}
                {note && <span className="italic text-mi-code-note">{"  "}# {note}</span>}
              </span>
            </span>
          );
        })}
      </code></pre>
    </div>
  );
}

export function keepArrowsInCode(event: KeyboardEvent) {
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") event.stopPropagation();
}
