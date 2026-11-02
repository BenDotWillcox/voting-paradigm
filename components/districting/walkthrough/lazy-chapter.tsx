"use client";

import * as React from "react";

import { useNear } from "../defer-until-near";

const pad = (value: number) => String(value).padStart(2, "0");

/** A chapter's frame while its data loads or before it nears the screen: rail lines and a spinner on the map plate. */
export const ChapterSkeleton = React.forwardRef<HTMLElement, { number: number; title: string }>(function ChapterSkeleton({ number, title }, ref) {
  return (
    <section ref={ref} className="dd-chapter" aria-busy="true" aria-label={`Chapter ${number}: ${title}, loading`}>
      <header className="dd-chapter-head">
        <span className="dd-chapter-number">Chapter {pad(number)}</span>
        <h3 className="dd-chapter-title">{title}</h3>
      </header>
      <div className="dd-chapter-body">
        <div className="dd-steps dd-skeleton-rail" aria-hidden="true">
          {[78, 92, 64, 85, 70].map((width, index) => <span key={index} className="dd-skeleton-line" style={{ width: `${width}%` }} />)}
        </div>
        <div className="dd-map-area dd-chapter-stage">
          <div className="dd-map-frame dd-skeleton-frame" role="status">
            <span className="dd-spinner" aria-hidden="true" />
            <span className="dd-status">Loading chapter {number}…</span>
          </div>
        </div>
      </div>
    </section>
  );
});

/**
 * Mounts a chapter only once its data is ready and it nears the screen; until
 * then its skeleton holds the place, so the page keeps its shape and "Next
 * chapter" still has somewhere to land.
 */
export function LazyChapter({ number, title, render }: { number: number; title: string; render: (() => React.ReactNode) | null }) {
  const ref = React.useRef<HTMLElement>(null);
  const near = useNear(ref);
  if (near && render) return <>{render()}</>;
  return <ChapterSkeleton ref={ref} number={number} title={title} />;
}
