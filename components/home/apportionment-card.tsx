"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";
import { DotField, type DotTone } from "@/components/story/dot-field";
import { NAMED_SIZES, SWEEP_START, spreadAt } from "@/lib/apportionment/house-sizes";
import { CUBE_ROOT_SEATS, WYOMING_RULE_SEATS } from "@/lib/districting-cap-scale";
import { storySerif } from "@/lib/story/fonts";
import { hemicycleLayout, type SeatDot } from "@/lib/story/hemicycle";
import { cn } from "@/lib/utils";

import { statusLabel, type ShowcaseDemo } from "./demo-types";

/**
 * House sizes the card steps through. The named sizes (435, the Wyoming
 * Rule, the cube-root rule, 1,000) hold longer; the steps between them keep
 * the growth reading as continuous.
 */
const STOPS = [SWEEP_START, 480, 530, WYOMING_RULE_SEATS, 630, CUBE_ROOT_SEATS, 780, 880, 1000];
const STEP_MS = 1400;
const NAMED_MS = 2600;
const END_MS = 3400;
/** First step after the pointer arrives: start promptly, not after a hold. */
const START_MS = 350;

const NAMED_LABEL = new Map(NAMED_SIZES.map(({ size, label }) => [size, label]));

/**
 * Demo 4's home card, in the essay's "civic almanac" identity: the House
 * grows past 435 seat by seat while the largest-to-smallest district ratio
 * barely moves until the chamber nears 1,000. Today's seats stay warm gray,
 * added seats are muted ink blue, and each step's new seats arrive in full
 * ink blue. Numbers come from the essay's shared house-size module.
 *
 * The chamber rests at 435 and plays while hovered or focused; leaving
 * returns it to 435. Touch screens have no hover, so there it plays while
 * the card is on screen instead.
 */
export function ApportionmentCard({ demo }: { demo: ShowcaseDemo }) {
  const reducedMotion = useReducedMotion();
  const canHover = useCanHover();
  const visible = useInView<HTMLAnchorElement>();
  const [hovered, setHovered] = React.useState(false);
  const [step, setStep] = React.useState(0);
  const [previous, setPrevious] = React.useState<number | null>(null);
  const playing = !reducedMotion && (canHover ? hovered : visible.inView);

  React.useEffect(() => {
    if (!playing) {
      setStep(0);
      setPrevious(null);
      return;
    }
    const size = STOPS[step];
    const last = step === STOPS.length - 1;
    const hold =
      step === 0 && previous === null
        ? START_MS
        : last
          ? END_MS
          : NAMED_LABEL.has(size)
            ? NAMED_MS
            : STEP_MS;
    const timer = window.setTimeout(() => {
      setPrevious(last ? null : size);
      setStep(last ? 0 : step + 1);
    }, hold);
    return () => window.clearTimeout(timer);
  }, [step, previous, playing]);

  const size = STOPS[step];
  const spread = spreadAt(size);
  const layout = React.useMemo(() => hemicycleLayout(size), [size]);
  const dots = React.useMemo<SeatDot[]>(
    () => layout.slots.map((slot, i) => ({ key: `seat-${i}`, fips: "", x: slot.x, y: slot.y })),
    [layout]
  );
  const toneFor = React.useCallback(
    (dot: SeatDot): DotTone => {
      const index = Number(dot.key.slice("seat-".length));
      if (index < SWEEP_START) return "neutral";
      return previous !== null && index >= previous ? "focus" : "added";
    },
    [previous]
  );
  const largest = hemicycleLayout(STOPS[STOPS.length - 1]).dotRadius;

  const card = (
    <div
      data-story-theme="apportionment"
      className={cn(
        "story flex h-full flex-col rounded-xl border border-[var(--story-rule)] bg-story-surface p-6 text-story-ink transition-shadow hover:shadow-md",
        storySerif.variable
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-story-muted">Demo {demo.number}</p>
          <h2 className="font-story-serif text-2xl leading-tight font-medium tracking-[-0.01em]">
            {demo.title}
          </h2>
        </div>
        <span className="rounded-full border border-[var(--story-rule)] px-2.5 py-0.5 text-xs font-medium text-story-accent">
          {statusLabel[demo.status]}
        </span>
      </div>
      <p className="mt-2 font-story-serif text-lg leading-snug text-story-ink-2">{demo.tagline}</p>

      <div className="mt-4">
        <DotField
          dots={dots}
          dotRadius={layout.dotRadius}
          reserveRadius={Math.max(layout.dotRadius, largest)}
          toneFor={toneFor}
          enter="slide"
          duration={900}
          ariaLabel="A House chamber growing from 435 seats to 1,000, one dot per seat"
        />
        <dl className="mt-2 flex items-end justify-between gap-4 font-sans">
          <div>
            <dt className="h-4 text-xs text-story-muted">{NAMED_LABEL.get(size) ?? "House size"}</dt>
            <dd className="text-2xl leading-tight font-semibold tabular-nums">
              {size.toLocaleString("en-US")}
              <span className="text-sm font-normal text-story-muted"> seats</span>
            </dd>
          </div>
          <div className="text-right">
            <dt className="text-xs text-story-muted">Largest ÷ smallest district</dt>
            <dd className="text-2xl leading-tight font-semibold tabular-nums">{spread.ratio.toFixed(2)}×</dd>
          </div>
        </dl>
      </div>

      <p className="mt-4 text-sm leading-6 text-story-ink-2">{demo.description}</p>
      <ul className="mt-4 flex flex-wrap gap-1.5">
        {demo.showcase.map((tag) => (
          <li
            key={tag}
            className="rounded-md border border-[var(--story-rule)] px-2 py-0.5 text-xs text-story-ink-2"
          >
            {tag}
          </li>
        ))}
      </ul>
      <div className="mt-auto flex items-center gap-1 pt-4 text-sm font-medium text-story-accent">
        Read the essay
        <ArrowRight className="h-4 w-4" />
      </div>
    </div>
  );

  return demo.href ? (
    <Link
      ref={visible.ref}
      href={demo.href}
      className="block h-full"
      onPointerEnter={(event) => event.pointerType === "mouse" && setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      onFocus={() => setHovered(true)}
      onBlur={() => setHovered(false)}
    >
      {card}
    </Link>
  ) : (
    card
  );
}

/** Whether the primary pointer can hover (false on touch screens). */
function useCanHover(): boolean {
  return React.useSyncExternalStore(
    (onChange) => {
      const query = window.matchMedia("(hover: hover)");
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    },
    () => window.matchMedia("(hover: hover)").matches,
    () => true
  );
}

/** Whether the element is on screen, so the loop only runs while seen. */
function useInView<T extends Element>(): { ref: React.RefCallback<T>; inView: boolean } {
  const [node, setNode] = React.useState<T | null>(null);
  const [inView, setInView] = React.useState(false);
  React.useEffect(() => {
    if (!node) return;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), {
      threshold: 0.35,
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [node]);
  return { ref: setNode, inView };
}
