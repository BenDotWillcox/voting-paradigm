"use client";

import * as React from "react";
import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";

import { jumpToSection } from "../defer-until-near";

export interface ChapterStep {
  title: string;
  body: React.ReactNode;
}

const pad = (value: number) => String(value).padStart(2, "0");

/**
 * Scrolls past the chapter holding `from` to the next one, or opens the
 * explorer and jumps to it after the last. A chapter that fits on screen lands
 * centered; a taller one lands at its top.
 */
function goToNextChapter(from: Element | null) {
  let target = from?.closest(".dd-chapter")?.nextElementSibling ?? null;
  while (target && !target.classList.contains("dd-chapter")) target = target.nextElementSibling;
  if (!target) return jumpToSection("explorer");
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const fits = target.getBoundingClientRect().height <= window.innerHeight;
  target.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: fits ? "center" : "start" });
}

/** The "Next chapter" button on its own, for chapters without step controls. */
export function NextChapterButton({ label = "Next chapter" }: { label?: string }) {
  const ref = React.useRef<HTMLButtonElement>(null);
  return <button ref={ref} type="button" className="dd-tool" onClick={() => goToNextChapter(ref.current)}>{label}<ChevronDown aria-hidden="true" /></button>;
}

/**
 * A walkthrough chapter: numbered steps docked beside one figure, like the
 * explorer's control rail. Only the active step's text is open; the figure
 * follows the step. Arrow keys step while focus is inside the chapter. Next on
 * the last step moves on to the following chapter, or to the explorer after
 * the last one.
 */
export function ChapterConsole({ number, title, steps, step, onStep, onwardLabel = "Next chapter", onEnter, children }: {
  number: number;
  title: string;
  /** The last step's button, which scrolls on past this chapter. */
  onwardLabel?: string;
  /** Called once, the first time the chapter scrolls into view. */
  onEnter?: () => void;
  steps: ChapterStep[];
  step: number;
  onStep: (step: number) => void;
  children: React.ReactNode;
}) {
  const id = React.useId();
  const sectionRef = React.useRef<HTMLElement>(null);
  const go = (next: number) => onStep(Math.max(0, Math.min(steps.length - 1, next)));
  const last = step === steps.length - 1;
  const onEnterRef = React.useRef(onEnter);
  onEnterRef.current = onEnter;
  const watches = Boolean(onEnter);
  React.useEffect(() => {
    const node = sectionRef.current;
    if (!watches || !node) return;
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      observer.disconnect();
      onEnterRef.current?.();
    }, { threshold: 0.35 });
    observer.observe(node);
    return () => observer.disconnect();
  }, [watches]);
  const onward = () => goToNextChapter(sectionRef.current);
  return (
    <section ref={sectionRef} className="dd-chapter" aria-labelledby={`${id}-title`}
      onKeyDown={(event) => {
        if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) return;
        if (event.key === "ArrowRight") { event.preventDefault(); go(step + 1); }
        else if (event.key === "ArrowLeft") { event.preventDefault(); go(step - 1); }
      }}>
      <header className="dd-chapter-head">
        <span className="dd-chapter-number">Chapter {pad(number)}</span>
        <h3 id={`${id}-title`} className="dd-chapter-title">{title}</h3>
      </header>
      <div className="dd-chapter-body">
        <div className="dd-steps">
          <ol className="dd-step-list">
            {steps.map((item, index) => (
              <li key={item.title} className="dd-step" data-active={index === step || undefined}>
                <button type="button" aria-expanded={index === step} aria-controls={`${id}-step-${index}`} onClick={() => go(index)}>
                  <span className="dd-led" data-state={index === step ? "on" : undefined} />
                  <span className="dd-step-index">{pad(index + 1)}</span>
                  <span>{item.title}</span>
                </button>
                <div id={`${id}-step-${index}`} className="dd-step-body" hidden={index !== step}>{item.body}</div>
              </li>
            ))}
          </ol>
          <div className="dd-step-controls">
            <button type="button" className="dd-tool" onClick={() => go(step - 1)} disabled={step === 0}><ChevronLeft aria-hidden="true" />Prev</button>
            <span className="dd-status" aria-live="polite">{pad(step + 1)} / {pad(steps.length)}</span>
            {last
              ? <button type="button" className="dd-tool" onClick={onward}>{onwardLabel}<ChevronDown aria-hidden="true" /></button>
              : <button type="button" className="dd-tool" onClick={() => go(step + 1)}>Next<ChevronRight aria-hidden="true" /></button>}
          </div>
        </div>
        {children}
      </div>
    </section>
  );
}
