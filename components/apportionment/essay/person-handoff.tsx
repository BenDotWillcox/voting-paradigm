"use client";

import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";

import { PersonFigure, RUSH_STEPS, VIEW } from "./person-figure";
import { usePersona, type PersonPlace } from "./persona";

/** Viewport height (share from the top) where the person leaves the stage. */
const DEPART_AT = 0.45;
/** The flight never takes less scroll than this, in px. */
const MIN_FLIGHT = 240;
/** Scrolling this far into the flight finishes an intro still playing. */
const FINISH_AT = 0.35;

/**
 * Carries the reader's finished person from the intro's stage down into the
 * crowd's first circle as the reader scrolls between them. Scroll-linked,
 * so it reverses on the way back up. A fixed overlay draws the person in
 * flight, interpolating between where the stage shows them
 * (`[data-person-source]`) and where the crowd's canvas will draw them
 * (`[data-person-target]`, which publishes that spot as data attributes);
 * `personAt` tells both places when to stand aside. Both measured live, so
 * the overlay matches each exactly at the ends of the flight.
 */
export function PersonHandoff() {
  const { persona, phase, setPhase, setPersonAt } = usePersona();
  const reducedMotion = useReducedMotion();
  const overlayRef = React.useRef<HTMLDivElement | null>(null);
  const running = phase === "shuffle" || phase === "assemble";
  const enabled = persona !== null && !reducedMotion && (phase === "complete" || running);
  const readableCategories = React.useMemo(
    () => persona?.readable.map((piece) => piece.category),
    [persona]
  );

  React.useEffect(() => {
    if (!enabled) {
      setPersonAt(null);
      return;
    }
    if (running) setPersonAt(null);
    let frame = 0;
    let place: PersonPlace = null;
    const settle = (next: PersonPlace) => {
      if (next === place) return;
      place = next;
      setPersonAt(next);
    };

    const update = () => {
      frame = 0;
      const source = document.querySelector("[data-person-source] svg");
      const target = document.querySelector<HTMLCanvasElement>("[data-person-target]");
      const overlay = overlayRef.current;
      if (!source || !target || !overlay) return;
      const from = source.getBoundingClientRect();
      const to = target.getBoundingClientRect();
      const section = target.closest("section");

      // The flight spans the scroll from "person mid-screen on the stage"
      // to "crowd figure pinned" (its section reaching the top).
      const start = from.top + window.scrollY + from.height / 2 - window.innerHeight * DEPART_AT;
      const pinned = (section ?? target).getBoundingClientRect().top + window.scrollY;
      const end = Math.max(pinned, start + MIN_FLIGHT);
      const t = clamp01((window.scrollY - start) / (end - start));

      if (running) {
        // Scrolling on finishes the intro, so the finished person travels.
        if (t > FINISH_AT) setPhase("complete");
        overlay.style.opacity = "0";
        return;
      }
      settle(t <= 0 ? "stage" : t >= 1 ? "crowd" : "flight");
      if (t <= 0 || t >= 1) {
        overlay.style.opacity = "0";
        return;
      }

      // Where the crowd draws the person: published by its canvas, or (before
      // its first draw) the single-person framing it starts from.
      const published = Number(target.dataset.focalH);
      const landingHeight = published > 0 ? published : Math.min(to.width, to.height) * 0.42 * 0.7;
      const landingX = to.left + (published > 0 ? Number(target.dataset.focalX) : to.width / 2);
      const landingY = to.top + (published > 0 ? Number(target.dataset.focalY) : to.height / 2);

      const e = easeInOutCubic(t);
      const x = lerp(from.left + from.width / 2, landingX, e);
      const y = lerp(from.top + from.height / 2, landingY, e);
      const height = lerp(from.height, landingHeight, e);
      // A little lift and lean mid-flight, gone at both ends.
      const lift = Math.sin(Math.PI * t);
      overlay.style.opacity = "1";
      overlay.style.transform =
        `translate3d(${(x - VIEW.width / 2).toFixed(1)}px, ${(y - VIEW.height / 2).toFixed(1)}px, 0) ` +
        `rotate(${(-6 * lift).toFixed(2)}deg) scale(${((height / VIEW.height) * (1 + 0.08 * lift)).toFixed(4)})`;
    };
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      window.cancelAnimationFrame(frame);
    };
  }, [enabled, running, setPhase, setPersonAt]);

  if (!enabled || !persona) return null;
  return (
    <div
      ref={overlayRef}
      aria-hidden="true"
      className="pointer-events-none fixed top-0 left-0 z-30 text-story-ink will-change-transform"
      style={{ width: VIEW.width, height: VIEW.height, opacity: 0, transformOrigin: "center" }}
    >
      <PersonFigure
        roleId={persona.role.id}
        mode="assembled"
        arrived={3 + RUSH_STEPS}
        readableCategories={readableCategories}
        seed={persona.seed}
        className="block h-full w-full"
      />
    </div>
  );
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}
