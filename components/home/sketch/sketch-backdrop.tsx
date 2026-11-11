"use client";

import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";
import { SITE_PALETTE as P } from "@/lib/site";

import { DOODLES, MOTIFS, type Motif } from "./motifs";
import { rng, type Motion, type Tone } from "./pencil";
import { Weather } from "./weather";

/**
 * The home page's background: abstract pencil sketches that come and go in
 * whatever paper the page leaves open, roughly in the order democracy grew.
 * Each draws itself stroke by stroke, lingers, then erases in the order it
 * was drawn. A new one starts every couple of seconds wherever there is
 * room: clear of the headline, intro and cards, and never on top of
 * another sketch; when nothing is free it waits. Once drawn, parts keep
 * moving: pebbles
 * drop, turbines spin, flags wave, leaves blow away. The last two, a growing
 * tree beside sun, wind and solar panels, arrive together and stay longest
 * before the cycle begins again. Between them, small doodles (a waving
 * hand, a ballot box, speech bubbles) fill the smaller gaps, and now and
 * then a gust, a few birds or a paper-plane ballot crosses the page.
 * Reduced motion shows a still arrangement instead.
 *
 * Plain SVG and CSS animations: no canvas, nothing to load. A pencil filter
 * roughens each stroke's edge and breaks it with graphite grain.
 */

const TONES: Record<Tone, string> = {
  graphite: "#3c4252",
  blue: P.blue,
  aqua: "#14adbd",
  rose: P.rose,
  sun: "#f0a53a",
  violet: P.violet,
  green: "#3fae6a",
};

/** How a kind of sketch paces itself, in seconds, and how wide it is drawn: a share of the viewport, clamped in pixels. */
interface Pace {
  draw: number;
  hold: number;
  width: [min: number, share: number, max: number];
}

const MAIN: Pace = { draw: 3.2, hold: 4.4, width: [130, 0.17, 260] };
const FINALE: Pace = { draw: 5.5, hold: 11, width: [170, 0.22, 340] };
const DOODLE: Pace = { draw: 1.4, hold: 3.6, width: [60, 0.07, 100] };
const ERASE = 1.8;
const MAIN_GAP = 2.2;
const DOODLE_GAP = 2.6;
/** How soon to look again when there is no room. */
const RETRY = 0.7;
/** Pencil speed, in viewBox units a second, before a sketch is fitted to its draw time. */
const SPEED = 220;

interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** A placed sketch: its box in viewport pixels. */
interface Place extends Box {
  x: number;
  y: number;
  width: number;
}

const area = (b: Box) => Math.max(0, b.right - b.left) * Math.max(0, b.bottom - b.top);
const overlap = (a: Box, b: Box) =>
  area({ left: Math.max(a.left, b.left), top: Math.max(a.top, b.top), right: Math.min(a.right, b.right), bottom: Math.min(a.bottom, b.bottom) });

/** What sketches keep clear of: the elements the page marks with data-sketch-avoid. */
function content(): Box[] {
  return [...document.querySelectorAll("[data-sketch-avoid]")].map((el) => el.getBoundingClientRect());
}

/**
 * The best open spot for a sketch, or null when there is no room. Candidates
 * are a grid over the viewport; a spot qualifies if it is at least three
 * quarters on screen, barely touches the page content and keeps clear of
 * every sketch already on the paper. Among those, it takes the one farthest
 * from the others, leaning toward `side`.
 */
function findPlace(motif: Motif, pace: Pace, taken: Box[], side: "left" | "right" | "any", rand: () => number): Place | null {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const [min, share, max] = pace.width;
  const width = Math.min(max, Math.max(min, vw * share));
  const height = (width * motif.height) / motif.width;
  const screen = { left: 0, top: 0, right: vw, bottom: vh };
  const blocks = content();
  const gap = 14;
  let best: Place | null = null;
  let bestScore = -Infinity;
  for (let fx = 0.04; fx <= 0.96; fx += 0.04) {
    for (let fy = 0.05; fy <= 0.95; fy += 0.05) {
      const x = fx * vw;
      const y = fy * vh;
      const box = { left: x - width / 2, top: y - height / 2, right: x + width / 2, bottom: y + height / 2 };
      const size = width * height;
      if (overlap(box, screen) < size * 0.75) continue;
      const covered = blocks.reduce((sum, b) => sum + overlap(box, b), 0) / size;
      if (covered > 0.12) continue;
      const padded = { left: box.left - gap, top: box.top - gap, right: box.right + gap, bottom: box.bottom + gap };
      if (taken.some((t) => overlap(padded, t) > 0)) continue;
      const nearest = taken.reduce((d, t) => Math.min(d, Math.hypot(x - (t.left + t.right) / 2, y - (t.top + t.bottom) / 2)), 700);
      const leaning = side === "any" ? 0 : (side === "left") === x < vw / 2 ? 160 : 0;
      const score = nearest + leaning - covered * 600 + rand() * 40;
      if (score > bestScore) {
        bestScore = score;
        best = { ...box, x, y, width };
      }
    }
  }
  return best;
}

const FINALE_AT = MOTIFS.length - 2;

interface Timing {
  start: number;
  duration: number;
  eraseAt: number;
}

/** When each stroke draws and erases: in order, overlapping, fitted to the draw time. */
function timings(motif: Motif, pace: Pace): { strokes: Timing[]; life: number } {
  let at = 0;
  const raw = motif.strokes.map((stroke) => {
    const duration = Math.min(0.8, Math.max(0.1, stroke.length / SPEED));
    const start = at;
    at += duration * 0.5;
    return { start, duration };
  });
  const total = Math.max(...raw.map((r) => r.start + r.duration));
  const fit = pace.draw / total;
  const n = motif.strokes.length;
  const strokes = raw.map((r, i) => ({ start: r.start * fit, duration: r.duration * fit, eraseAt: pace.draw + pace.hold + (i / n) * (ERASE - 0.5) }));
  return { strokes, life: pace.draw + pace.hold + ERASE + 0.2 };
}

interface Sketching {
  key: string;
  motif: Motif;
  pace: Pace;
  /** Center and width, as CSS lengths. */
  x: string;
  y: string;
  width: string;
  tilt: number;
}

/** CSS variables that drive a moving group's animation (see .sk-move in globals.css). */
function motionStyle(motion: Motion, startsAt: number): React.CSSProperties {
  const base: Record<string, string> = { "--move-at": `${startsAt.toFixed(2)}s` };
  if ("pivot" in motion) {
    base["--px"] = `${motion.pivot[0].toFixed(1)}px`;
    base["--py"] = `${motion.pivot[1].toFixed(1)}px`;
  }
  switch (motion.kind) {
    case "spin":
    case "wave":
    case "pulse":
      return { ...base, "--period": `${motion.period}s` } as React.CSSProperties;
    case "sway":
      return { ...base, "--period": `${motion.period}s`, "--deg": `${motion.degrees}deg` } as React.CSSProperties;
    case "bob":
      return { ...base, "--period": `${motion.period}s`, "--dist": `${-motion.distance}px` } as React.CSSProperties;
    case "drop":
      return { ...base, "--period": `${motion.period}s`, "--dist": `${-motion.distance}px`, "--delay": `${motion.delay}s` } as React.CSSProperties;
    case "fly":
      return {
        ...base,
        "--delay": `${motion.delay.toFixed(2)}s`,
        "--fly": `${motion.duration.toFixed(2)}s`,
        "--tx": `${motion.to[0].toFixed(0)}px`,
        "--ty": `${motion.to[1].toFixed(0)}px`,
        "--turn": `${motion.turn.toFixed(0)}deg`,
      } as React.CSSProperties;
  }
}

function MotifSketch({ sketching, still }: { sketching: Sketching; still: boolean }) {
  const { motif, pace } = sketching;
  const { strokes } = React.useMemo(() => timings(motif, pace), [motif, pace]);

  // Strokes and moving groups nest as the sketch drew them; groups start moving once it is drawn.
  const render = (parent: number | undefined): React.ReactNode[] => [
    ...motif.strokes.flatMap((stroke, i) =>
      stroke.group === parent
        ? [
            <path
              key={`s${i}`}
              d={stroke.d}
              pathLength={1}
              className="sk-stroke"
              stroke={TONES[stroke.tone]}
              strokeWidth={stroke.width}
              strokeOpacity={(stroke.tone === "graphite" ? 0.62 : 0.8) * (stroke.soft ? 0.6 : 1)}
              style={
                {
                  "--start": `${strokes[i].start.toFixed(2)}s`,
                  "--dur": `${strokes[i].duration.toFixed(2)}s`,
                  "--erase-at": `${strokes[i].eraseAt.toFixed(2)}s`,
                } as React.CSSProperties
              }
            />,
          ]
        : []
    ),
    ...motif.groups.flatMap((group, g) =>
      group.parent === parent
        ? [
            <g key={`g${g}`} className={`sk-move sk-${group.motion.kind}`} style={motionStyle(group.motion, pace.draw)}>
              {render(g)}
            </g>,
          ]
        : []
    ),
  ];

  return (
    <svg
      viewBox={`0 0 ${motif.width} ${motif.height}`}
      className="sk-motif"
      data-still={still || undefined}
      style={
        {
          left: sketching.x,
          top: sketching.y,
          "--size": sketching.width,
          "--tilt": `${sketching.tilt}deg`,
          aspectRatio: `${motif.width} / ${motif.height}`,
        } as React.CSSProperties
      }
    >
      <g filter="url(#sk-pencil)">{render(undefined)}</g>
    </svg>
  );
}

const cssWidth = ([min, share, max]: Pace["width"]) => `clamp(${min}px, ${share * 100}vw, ${max}px)`;

/** For reduced motion: a fixed arrangement in the top corners, fully drawn. */
const STILL: Sketching[] = [
  { key: "still-1", motif: MOTIFS[0], pace: MAIN, x: "8%", y: "14%", width: cssWidth(MAIN.width), tilt: -3 },
  { key: "still-2", motif: MOTIFS[FINALE_AT], pace: FINALE, x: "9%", y: "30%", width: cssWidth(FINALE.width), tilt: 2 },
  { key: "still-3", motif: MOTIFS[FINALE_AT + 1], pace: FINALE, x: "91%", y: "24%", width: cssWidth(FINALE.width), tilt: -2 },
];

/** Tilts are seeded by position, so the page looks the same each visit. */
const tilt = (n: number) => (((n * 37) % 11) - 5) * 0.9;

export function SketchBackdrop() {
  const reducedMotion = useReducedMotion();
  const [sketches, setSketches] = React.useState<Sketching[]>([]);

  React.useEffect(() => {
    if (reducedMotion) return;
    let key = 0;
    let cancelled = false;
    const timers = new Set<number>();
    const later = (seconds: number, run: () => void) => {
      const id = window.setTimeout(() => {
        timers.delete(id);
        if (!cancelled) run();
      }, seconds * 1000);
      timers.add(id);
    };
    // The paper each sketch on screen is holding, until it has erased.
    const taken = new Map<string, Box>();
    const rand = rng(0x5ce7c4);

    const spawn = (motif: Motif, pace: Pace, place: Place, n: number) => {
      const sketching: Sketching = {
        key: `${motif.id}-${++key}`,
        motif,
        pace,
        x: `${place.x.toFixed(0)}px`,
        y: `${place.y.toFixed(0)}px`,
        width: `${place.width.toFixed(0)}px`,
        tilt: tilt(n),
      };
      taken.set(sketching.key, place);
      setSketches((current) => [...current, sketching]);
      const { life } = timings(motif, pace);
      later(life, () => {
        taken.delete(sketching.key);
        setSketches((current) => current.filter((s) => s.key !== sketching.key));
      });
      return life;
    };

    // The main sketches, oldest to newest, then the finale. Each waits for room.
    let step = 0;
    const nextMain = () => {
      if (step < FINALE_AT) {
        const place = findPlace(MOTIFS[step], MAIN, [...taken.values()], step % 2 ? "right" : "left", rand);
        if (!place) return later(RETRY, nextMain);
        spawn(MOTIFS[step], MAIN, place, step);
        step++;
        later(MAIN_GAP, nextMain);
      } else {
        // The finale's two halves need room at the same time.
        const left = findPlace(MOTIFS[FINALE_AT], FINALE, [...taken.values()], "left", rand);
        const right = left && findPlace(MOTIFS[FINALE_AT + 1], FINALE, [...taken.values(), left], "right", rand);
        if (!left || !right) return later(RETRY, nextMain);
        const life = Math.max(spawn(MOTIFS[FINALE_AT], FINALE, left, FINALE_AT), spawn(MOTIFS[FINALE_AT + 1], FINALE, right, FINALE_AT + 1));
        step = 0;
        later(life + 1, nextMain);
      }
    };

    // Doodles fill the smaller gaps on their own rhythm, skipping a beat when there is none.
    let doodle = 0;
    const nextDoodle = () => {
      const motif = DOODLES[doodle % DOODLES.length];
      const place = findPlace(motif, DOODLE, [...taken.values()], "any", rand);
      if (place) {
        spawn(motif, DOODLE, place, doodle + 3);
        doodle++;
      }
      later(place ? DOODLE_GAP : RETRY, nextDoodle);
    };

    // A beat after load, so the page settles first.
    later(0.6, nextMain);
    later(1.8, nextDoodle);
    return () => {
      cancelled = true;
      for (const id of timers) window.clearTimeout(id);
      setSketches([]);
    };
  }, [reducedMotion]);

  return (
    <div aria-hidden className="sk-paper pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <svg width="0" height="0" className="absolute">
        <filter id="sk-pencil" x="-5%" y="-5%" width="110%" height="110%">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="4" result="wobble" />
          <feDisplacementMap in="SourceGraphic" in2="wobble" scale="1.6" xChannelSelector="R" yChannelSelector="G" result="rough" />
          <feTurbulence type="fractalNoise" baseFrequency="1.8" numOctaves="1" seed="11" result="grain" />
          <feColorMatrix in="grain" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -2.2 1.75" result="tooth" />
          <feComposite in="rough" in2="tooth" operator="in" />
        </filter>
      </svg>
      {(reducedMotion ? STILL : sketches).map((sketching) => (
        <MotifSketch key={sketching.key} sketching={sketching} still={reducedMotion} />
      ))}
      {!reducedMotion && <Weather />}
    </div>
  );
}
