"use client";

import * as React from "react";

import { SITE_PALETTE as P } from "@/lib/site";

import { Sketch, rng, type Stroke } from "./pencil";

/**
 * Things that pass across the whole page every so often, in the same
 * pencil as the sketches: a gust of wind streaks with leaves tumbling in
 * it, a few birds, or a ballot folded into a paper plane. Everything
 * travels left to right, the way the tree's leaves blow.
 */

const GRAPHITE = "#3c4252";
const GREEN = "#3fae6a";

function drawn(seed: number, draw: (s: Sketch) => void): Stroke[] {
  const sketch = new Sketch(rng(seed));
  draw(sketch);
  return sketch.strokes;
}

const PLANE = drawn(5, (s) => {
  s.curve(
    [
      [6, 30],
      [94, 6],
      [48, 46],
      [40, 30],
      [6, 30],
    ],
    { width: 1.3, wobble: 0.5 }
  );
  s.line(94, 6, 40, 30, { width: 1, soft: true });
  s.line(48, 46, 44, 33, { width: 1, soft: true });
  // The ballot it was folded from: a ruled line and a filled oval.
  s.line(20, 28, 52, 21, { tone: "blue", width: 0.8, soft: true });
  s.circle(62, 18, 2.2, { tone: "blue", width: 0.9 });
});

const BIRD = drawn(7, (s) => s.curve([[2, 12], [8, 5], [16, 10], [24, 4], [30, 11]], { width: 1.3, wobble: 0.3 }));

const LEAF = drawn(9, (s) => {
  s.curve([[2, 8], [9, 2], [18, 6], [10, 13], [2, 8]], { tone: "green", width: 1.1, wobble: 0.2 });
  s.line(3, 8, 17, 6, { tone: "green", width: 0.7, soft: true, wobble: 0.2 });
});

/** Long wind streaks across a 1000-wide strip, each ending in a curl. */
const STREAKS = [0, 1, 2].map((i) => {
  const y = 30 + i * 36;
  const points: [number, number][] = [];
  for (let x = 0; x <= 860; x += 40) points.push([x, y + Math.sin(x * 0.012 + i * 1.7) * 10]);
  for (let a = 0; a <= Math.PI * 1.6; a += 0.4) points.push([880 + Math.sin(a) * 18, y - 18 + Math.cos(a) * 18]);
  return drawn(20 + i, (s) => s.curve(points, { width: 1.2, wobble: 2 }))[0];
});

const TONE: Record<string, string> = { graphite: GRAPHITE, blue: P.blue, green: GREEN };

function Drawing({ strokes, width, height }: { strokes: Stroke[]; width: number; height: number }) {
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="block size-full overflow-visible">
      <g filter="url(#sk-pencil)">
        {strokes.map((stroke, i) => (
          <path
            key={i}
            d={stroke.d}
            fill="none"
            stroke={TONE[stroke.tone] ?? GRAPHITE}
            strokeWidth={stroke.width}
            strokeOpacity={stroke.soft ? 0.45 : 0.7}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
      </g>
    </svg>
  );
}

type Kind = "gust" | "birds" | "plane";

/** Seconds each crossing takes, including its slowest traveler. */
const DURATION: Record<Kind, number> = { gust: 7, birds: 15, plane: 13 };
const ORDER: Kind[] = ["gust", "birds", "plane", "gust", "birds", "gust", "plane"];
/** Heights, as percentages of the viewport, so crossings vary; all above the hand of cards. */
const HEIGHTS = [10, 38, 22, 44, 6, 30, 16];

interface Passing {
  key: number;
  kind: Kind;
  y: number;
}

function Gust() {
  return (
    <>
      <svg viewBox="0 0 1000 140" preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible">
        <g filter="url(#sk-pencil)">
          {STREAKS.map((stroke, i) => (
            <path
              key={i}
              d={stroke.d}
              pathLength={1}
              className="sk-streak"
              stroke={GRAPHITE}
              strokeWidth={1.2}
              strokeOpacity={0.5}
              vectorEffect="non-scaling-stroke"
              style={{ "--delay": `${i * 0.4}s` } as React.CSSProperties}
            />
          ))}
        </g>
      </svg>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="sk-traveler" style={{ top: `${18 + i * 20}%`, "--dur": `${3.6 + i * 0.6}s`, "--delay": `${0.2 + i * 0.35}s` } as React.CSSProperties}>
          <div className="sk-flutter" style={{ "--rise": `${i % 2 ? -14 : 12}px` } as React.CSSProperties}>
            <div className="sk-tumble size-4">
              <Drawing strokes={LEAF} width={20} height={15} />
            </div>
          </div>
        </div>
      ))}
    </>
  );
}

function Birds() {
  const flock: [number, number, number][] = [
    [0, 0, 1],
    [-34, 18, 0.85],
    [-30, -16, 0.8],
    [-64, 6, 0.7],
  ];
  return (
    <div className="sk-traveler" style={{ "--dur": `${DURATION.birds}s`, "--delay": "0s" } as React.CSSProperties}>
      <div className="sk-flutter" style={{ "--rise": "-26px" } as React.CSSProperties}>
        {flock.map(([x, y, scale], i) => (
          <div key={i} className="absolute" style={{ left: x, top: y, width: 30 * scale, height: 16 * scale }}>
            <div className="sk-flap size-full" style={{ animationDelay: `${i * -0.13}s` }}>
              <Drawing strokes={BIRD} width={32} height={16} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Plane() {
  return (
    <div className="sk-traveler" style={{ "--dur": `${DURATION.plane}s`, "--delay": "0s" } as React.CSSProperties}>
      <div className="sk-glide h-[42px] w-[84px]">
        <Drawing strokes={PLANE} width={100} height={50} />
      </div>
    </div>
  );
}

export function Weather() {
  const [passing, setPassing] = React.useState<Passing[]>([]);

  React.useEffect(() => {
    let n = 0;
    let cancelled = false;
    const timers = new Set<number>();
    const later = (seconds: number, run: () => void) => {
      const id = window.setTimeout(() => {
        timers.delete(id);
        if (!cancelled) run();
      }, seconds * 1000);
      timers.add(id);
    };
    const next = () => {
      const item: Passing = { key: n, kind: ORDER[n % ORDER.length], y: HEIGHTS[n % HEIGHTS.length] };
      n++;
      setPassing((current) => [...current, item]);
      later(DURATION[item.kind] + 0.5, () => setPassing((current) => current.filter((p) => p.key !== item.key)));
      // Every 8 to 13 seconds, on a fixed rhythm.
      later(8 + ((n * 3.7) % 5), next);
    };
    later(4.5, next);
    return () => {
      cancelled = true;
      for (const id of timers) window.clearTimeout(id);
    };
  }, []);

  return (
    <>
      {passing.map((p) => (
        <div key={p.key} className="sk-passing" style={{ top: `${p.y}%` }}>
          {p.kind === "gust" ? <Gust /> : p.kind === "birds" ? <Birds /> : <Plane />}
        </div>
      ))}
    </>
  );
}
