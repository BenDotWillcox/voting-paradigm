"use client";

import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";
import { cn } from "@/lib/utils";

interface TearTextProps {
  /** Text before the tear. */
  left: string;
  /** Text after the tear. */
  right: string;
  /**
   * 0 = intact, 1 = fully torn (still readable), for scroll-driven use.
   * Omit to loop: the words stretch, tear, hang apart, then snap back
   * together, for as long as they are on screen.
   */
  strain?: number;
  className?: string;
}

/**
 * The shape of the tear at one instant. `stretch` is tension before the
 * break (letters pull long), `tear` is the break itself (the halves part
 * along a jagged edge, the right half sags), `close` (negative) is the
 * overshoot as the halves slam back together.
 */
interface Pose {
  stretch: number;
  tear: number;
  close: number;
}

const LOOP_MS = 7200;
/** Reduced motion: hold a readable partial tear instead of animating. */
const STATIC_POSE: Pose = { stretch: 0.2, tear: 0.35, close: 0 };
/** Fibers bridging the gap: vertical position (%) and the tear at which each snaps. */
const FIBERS = [
  { top: 22, snap: 0.32 },
  { top: 41, snap: 0.55 },
  { top: 57, snap: 0.24 },
  { top: 74, snap: 0.44 },
];

/**
 * Words under tension: the two halves stretch, tear apart along a jagged
 * edge, and come back together. The title loops this while visible; the end
 * of Act I drives it from scroll. Screen readers get the plain text; the
 * visual halves are hidden from them.
 */
export function TearText({ left, right, strain, className }: TearTextProps) {
  const reducedMotion = useReducedMotion();
  const rootRef = React.useRef<HTMLSpanElement | null>(null);
  const leftRef = React.useRef<HTMLSpanElement | null>(null);
  const rightRef = React.useRef<HTMLSpanElement | null>(null);
  const fiberRefs = React.useRef<Array<HTMLSpanElement | null>>([]);
  const looping = strain === undefined;

  // Styles are written straight to the nodes: the loop runs every frame and
  // must not re-render React.
  const apply = React.useCallback((pose: Pose) => {
    const style = poseStyle(pose);
    if (leftRef.current) Object.assign(leftRef.current.style, style.left);
    if (rightRef.current) Object.assign(rightRef.current.style, style.right);
    fiberRefs.current.forEach((fiber, i) => {
      if (fiber) Object.assign(fiber.style, style.fibers[i]);
    });
  }, []);

  // Scroll-driven: map strain to a pose (tension first, then the break).
  React.useEffect(() => {
    if (looping) return;
    apply(strainPose(Math.max(0, Math.min(1, strain ?? 0))));
  }, [looping, strain, apply]);

  // Loop: runs only while the words are on screen.
  React.useEffect(() => {
    if (!looping) return;
    if (reducedMotion) {
      apply(STATIC_POSE);
      return;
    }
    const node = rootRef.current;
    if (!node) return;
    let frame = 0;
    let start = 0;
    let visible = false;
    const tick = (now: number) => {
      if (!start) start = now;
      apply(loopPose(((now - start) % LOOP_MS) / LOOP_MS));
      frame = requestAnimationFrame(tick);
    };
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting === visible) return;
      visible = entry.isIntersecting;
      cancelAnimationFrame(frame);
      if (visible) frame = requestAnimationFrame(tick);
    });
    observer.observe(node);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [looping, reducedMotion, apply]);

  const transition = looping ? undefined : "transform 120ms linear";

  return (
    <span
      ref={rootRef}
      className={cn("inline-flex flex-wrap items-baseline justify-center", className)}
    >
      <span className="sr-only">
        {left} {right}
      </span>
      <span
        ref={leftRef}
        aria-hidden="true"
        className="inline-block will-change-transform"
        style={{ transformOrigin: "right center", transition }}
      >
        {left}
      </span>
      <span aria-hidden="true" className="relative inline-block w-[0.28em] self-stretch">
        {FIBERS.map((fiber, i) => (
          <span
            key={fiber.top}
            ref={(node) => {
              fiberRefs.current[i] = node;
            }}
            className="absolute left-1/2 h-px w-[0.3em] bg-current"
            style={{ top: `${fiber.top}%`, opacity: 0 }}
          />
        ))}
      </span>
      <span
        ref={rightRef}
        aria-hidden="true"
        className="inline-block will-change-transform"
        style={{ transformOrigin: "left center", transition }}
      >
        {right}
      </span>
    </span>
  );
}

/**
 * One loop, t in [0, 1): rest, build tension, rip, hang apart, snap back
 * with an overshoot, settle.
 */
function loopPose(t: number): Pose {
  const ms = t * LOOP_MS;
  const rest = 1300;
  const pull = rest + 1500; // tension builds
  const rip = pull + 380; // the break
  const hang = rip + 1500; // apart, drifting slightly
  const close = hang + 650; // halves rush back
  const settle = close + 500; // overshoot dies away
  if (ms < rest) return { stretch: 0, tear: 0, close: 0 };
  if (ms < pull) {
    const p = (ms - rest) / (pull - rest);
    return { stretch: p * p * (3 - 2 * p), tear: 0, close: 0 };
  }
  if (ms < rip) {
    const p = (ms - pull) / (rip - pull);
    const snap = 1 - (1 - p) ** 3;
    // Once it breaks, the stretched halves recoil while the gap opens.
    return { stretch: 1 - 0.75 * snap, tear: snap, close: 0 };
  }
  if (ms < hang) {
    const p = (ms - rip) / (hang - rip);
    return { stretch: 0.25 - 0.25 * p, tear: 1 + 0.06 * Math.sin(p * Math.PI), close: 0 };
  }
  if (ms < close) {
    const p = (ms - hang) / (close - hang);
    return { stretch: 0, tear: 1 - p * p * p, close: 0 };
  }
  if (ms < settle) {
    const p = (ms - close) / (settle - close);
    // A small bump past closed, decaying.
    return { stretch: 0, tear: 0, close: -Math.sin(p * Math.PI) * (1 - p) * 0.9 };
  }
  return { stretch: 0, tear: 0, close: 0 };
}

/** Scroll-driven strain: the first 40% is tension, the rest the tear. */
function strainPose(s: number): Pose {
  if (s < 0.4) return { stretch: s / 0.4, tear: 0, close: 0 };
  const tear = (s - 0.4) / 0.6;
  return { stretch: 1 - 0.75 * tear, tear, close: 0 };
}

function poseStyle({ stretch, tear, close }: Pose) {
  const gap = 0.05 * stretch + 0.36 * tear + 0.06 * close; // em, each side
  const scale = 1 + 0.07 * stretch;
  const jag = 0.13 * Math.max(0, tear);
  const sag = 2.4 * tear; // degrees
  const spacing = `${(0.018 * stretch).toFixed(4)}em`;
  return {
    left: {
      transform: `translateX(${(-gap).toFixed(4)}em) scaleX(${scale.toFixed(4)})`,
      letterSpacing: spacing,
      clipPath: tornEdge("right", jag),
    },
    right: {
      transform: `translateX(${gap.toFixed(4)}em) translateY(${(0.035 * tear).toFixed(4)}em) rotate(${sag.toFixed(3)}deg) scaleX(${scale.toFixed(4)})`,
      letterSpacing: spacing,
      clipPath: tornEdge("left", jag),
    },
    // Fibers stretch across the opening gap, then snap one by one.
    fibers: FIBERS.map((fiber) => {
      const holding = tear > 0.02 && tear < fiber.snap;
      return {
        opacity: holding ? String(0.55 * Math.min(1, tear / 0.08)) : "0",
        transform: `translateX(-50%) scaleX(${(1 + (gap * 2) / 0.3).toFixed(3)})`,
      };
    }),
  };
}

/**
 * A zigzag clip along one vertical edge, `depth` em deep (0 leaves the box
 * intact). In em so both halves tear equally regardless of word length.
 */
function tornEdge(side: "left" | "right", depth: number): string {
  const steps = [0, 12, 26, 38, 52, 64, 78, 90, 100];
  const inset = (i: number) => (i % 2 === 1 ? depth : depth * 0.25).toFixed(3);
  if (side === "right") {
    const edge = steps.map((y, i) => `calc(100% - ${inset(i)}em) ${y}%`).join(", ");
    return `polygon(0% 0%, ${edge}, 0% 100%)`;
  }
  const edge = steps
    .map((y, i) => `${inset(i)}em ${y}%`)
    .reverse()
    .join(", ");
  return `polygon(100% 0%, 100% 100%, ${edge})`;
}
