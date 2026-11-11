"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { generateBoard } from "@/components/districting/circuit-backdrop";
import { useReducedMotion } from "@/components/story/chart";
import { districtsMono } from "@/lib/districting-fonts";
import type { DistrictingCardData } from "@/lib/districting-home-card";
import { MAP_COLORS } from "@/lib/districts-palette";
import { cn } from "@/lib/utils";

import { useCanHover, useInView } from "./card-hooks";
import { statusLabel, type ShowcaseDemo } from "./demo-types";

type Stage = "seeds" | "power" | "repair" | "rebalance";

/** One stop of the loop: its stage, the frame it shows (-1 for the seeds) and how long it holds. */
interface Stop {
  stage: Stage;
  frame: number;
  hold: number;
}

const SEEDS_MS = 1600;
const ROUND_MS = 220;
const SETTLED_MS = 1500;
const REPAIR_MS = 2400;
const END_MS = 3200;
/** First step after the pointer arrives: start promptly, not after a hold. */
const START_MS = 350;

/**
 * The card's circuit board: the page backdrop's generator, run once for an
 * area larger than any card and cut to the card's top-left corner. The seed
 * fixes the board, so server and browser draw the same one.
 */
const BOARD_WIDTH = 640;
const BOARD_HEIGHT = 1120;
const BOARD_SEED = 0x0003_0435;
/** Electrons run on traces within what a two-column card shows, at the backdrop's pace. */
const ELECTRON_AREA = { width: 450, height: 660 };
const ELECTRON_SPEED = 70;
const ELECTRON_TAIL = 48;
const ELECTRONS = 6;

interface CardBoard {
  traces: string;
  pads: string;
  /** Each electron's trace, its tail as a share of the trace (of 100) and its timing in seconds. */
  electrons: { d: string; tail: number; seconds: number; delay: number }[];
}

let board: CardBoard | null = null;

function cardBoard(): CardBoard {
  if (board) return board;
  const traces = generateBoard(BOARD_WIDTH, BOARD_HEIGHT, BOARD_SEED);
  const line = (points: readonly (readonly [number, number])[]) => `M${points.map(([x, y]) => `${x} ${y}`).join("L")}`;
  const ends = traces.flatMap((trace) => [trace.points[0], trace.points[trace.points.length - 1]]);
  const runs = traces
    .filter((trace) => trace.total >= 100 && trace.points.every(([x, y]) => x < ELECTRON_AREA.width && y < ELECTRON_AREA.height))
    .sort((a, b) => b.total - a.total)
    .slice(0, ELECTRONS);
  board = {
    traces: traces.map((trace) => line(trace.points)).join(""),
    pads: ends.map(([x, y]) => `M${x + 3.5} ${y}a3.5 3.5 0 1 0 -7 0a3.5 3.5 0 1 0 7 0`).join(""),
    // Each run takes 70% of its cycle, then rests before the next.
    electrons: runs.map((trace, index) => ({
      d: line(trace.points),
      tail: (ELECTRON_TAIL / trace.total) * 100,
      seconds: trace.total / ELECTRON_SPEED / 0.7,
      delay: index * 0.6,
    })),
  };
  return board;
}

/**
 * The /districts circuit board behind the card's content: steel traces, with
 * electrons running along a few of them while the solve plays. Text carries a
 * board-colored halo, so it reads cleanly over the traces.
 */
const CardCircuit = React.memo(function CardCircuit() {
  const { traces, pads, electrons } = cardBoard();
  return (
    <svg aria-hidden="true" className="dd-card-circuit">
      <g className="dd-card-board">
        <path d={traces} className="dd-card-trace" />
        <path d={pads} className="dd-card-pad" />
      </g>
      {electrons.map((electron, index) => (
        <path
          key={index}
          d={electron.d}
          pathLength={100}
          className="dd-card-electron"
          style={{ "--dd-tail": electron.tail, animationDuration: `${electron.seconds}s`, animationDelay: `${electron.delay}s` } as React.CSSProperties}
        />
      ))}
    </svg>
  );
});

/** Seeds, every sampled round in quick succession, then repair and rebalance. */
function loop(frames: number): Stop[] {
  return [
    { stage: "seeds", frame: -1, hold: SEEDS_MS },
    ...Array.from({ length: frames }, (_, frame) => ({
      stage: "power" as const,
      frame,
      hold: frame === frames - 1 ? SETTLED_MS : ROUND_MS,
    })),
    { stage: "repair", frame: frames - 1, hold: REPAIR_MS },
    { stage: "rebalance", frame: frames - 1, hold: END_MS },
  ];
}

/**
 * Demo 3's home card, in the dashboard's "circuit board" identity. Michigan's
 * recorded solve plays from its 13 seeds through the balancing rounds, where
 * weights move the borders and the centers settle, then repair and rebalance
 * mark the blocks they move, and electrons run along the circuit traces
 * behind it. Beside it, each stage's largest gap from the
 * target falls from about two million people to under two. The cells,
 * centers and gaps are the walkthrough's own data.
 *
 * The map rests on the seeds and plays while hovered or focused; leaving
 * returns it to the seeds. Touch screens play it while the card is on
 * screen. Reduced motion holds on the seeds; every gap stays in the list.
 */
export function DistrictingCard({ demo, data }: { demo: ShowcaseDemo; data: DistrictingCardData }) {
  const reducedMotion = useReducedMotion();
  const canHover = useCanHover();
  const visible = useInView<HTMLAnchorElement>();
  const [hovered, setHovered] = React.useState(false);
  const [step, setStep] = React.useState(0);
  const started = React.useRef(false);
  const clipId = `dd-card-land${React.useId().replace(/:/g, "")}`;
  const stops = React.useMemo(() => loop(data.frames.length), [data.frames.length]);
  const playing = !reducedMotion && (canHover ? hovered : visible.inView);

  React.useEffect(() => {
    if (!playing) {
      started.current = false;
      setStep(0);
      return;
    }
    const hold = started.current ? stops[step].hold : START_MS;
    const timer = window.setTimeout(() => {
      started.current = true;
      setStep((current) => (current + 1) % stops.length);
    }, hold);
    return () => window.clearTimeout(timer);
  }, [step, playing, stops]);

  const stop = stops[step];
  const frame = stop.frame < 0 ? data.seeds : data.frames[stop.frame];
  const running = stop.stage === "power" && stop.frame < data.frames.length - 1;
  const rows: { stage: Stage; label: string; detail: string; gap: number }[] = [
    { stage: "seeds", label: "Seeds", detail: `${data.colors.length} drawn, weighted by people`, gap: data.gaps.seeds },
    {
      stage: "power",
      label: "Power diagram",
      detail: running ? `round ${frame.round} of ${data.rounds}` : `${data.rounds} balancing rounds`,
      gap: data.gaps.powerDiagram,
    },
    { stage: "repair", label: "Repair", detail: `${data.repair.count} pieces reattached`, gap: data.gaps.repaired },
    { stage: "rebalance", label: "Rebalance", detail: `${data.rebalance.count} blocks moved`, gap: data.gaps.final },
  ];
  const current = rows.find((row) => row.stage === stop.stage) ?? rows[0];
  const marks = stop.stage === "repair" ? data.repair.marks : stop.stage === "rebalance" ? data.rebalance.marks : null;

  const card = (
    <div
      className={cn("districts-ui dd-home-card @container flex h-full flex-col p-6", districtsMono.variable)}
      data-playing={playing || undefined}
    >
      <CardCircuit />
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-2xl leading-tight font-semibold tracking-tight">{demo.title}</h2>
        <span className="dd-home-chip">
          <span className="dd-led" data-state={demo.status === "live" ? "on" : demo.status === "in-progress" ? "busy" : undefined} />
          {statusLabel[demo.status]}
        </span>
      </div>
      <p className="mt-2 text-lg leading-snug text-muted-foreground">{demo.tagline}</p>

      {/* Map and stages sit side by side from 20rem, with a slightly smaller map until there is room for the full one. */}
      <figure className="mt-4 grid gap-4 @xs:grid-cols-[9.5rem_minmax(0,1fr)] @xs:gap-x-3.5 @sm:grid-cols-[11rem_minmax(0,1fr)] @sm:gap-x-4">
        <div>
          <div className="dd-home-plate aspect-square w-full max-w-[11rem]">
            <svg
              viewBox={`0 0 ${data.view} ${data.view}`}
              className="absolute inset-0 size-full"
              role="img"
              aria-label={`Michigan's ${data.colors.length} districts, ${current.label.toLowerCase()}: the largest gap from the target is ${gap(current.gap)} people`}
            >
              <defs>
                <clipPath id={clipId}>
                  <path d={data.outline} />
                </clipPath>
              </defs>
              <path d={data.outline} fill={MAP_COLORS.casing} />
              <g clipPath={`url(#${clipId})`} stroke={MAP_COLORS.line} strokeWidth={1} strokeLinejoin="round">
                {frame.cells.map(
                  (d, district) =>
                    d && <path key={district} d={d} fill={data.colors[district]} fillOpacity={0.62} vectorEffect="non-scaling-stroke" />
                )}
              </g>
              <path d={data.outline} fill="none" stroke={MAP_COLORS.line} strokeWidth={1} vectorEffect="non-scaling-stroke" />
              {/* Centers belong to the solve; after it, the rings take their place. */}
              {!marks && (
                <g fill="none" strokeLinecap="round">
                  <path d={frame.centers} stroke={MAP_COLORS.casing} strokeWidth={6} vectorEffect="non-scaling-stroke" />
                  <path d={frame.centers} stroke={MAP_COLORS.line} strokeWidth={3.5} vectorEffect="non-scaling-stroke" />
                </g>
              )}
              {marks && (
                <g key={stop.stage} className="dd-fade-in" fill="none" strokeLinecap="round">
                  <path d={marks} stroke={MAP_COLORS.selectionCasing} strokeWidth={9} vectorEffect="non-scaling-stroke" />
                  <path d={marks} stroke={MAP_COLORS.selection} strokeWidth={7} vectorEffect="non-scaling-stroke" />
                  <path d={marks} stroke={MAP_COLORS.selectionCasing} strokeWidth={3} vectorEffect="non-scaling-stroke" />
                </g>
              )}
            </svg>
          </div>
          <p className="mt-1.5 text-[0.7rem] leading-snug text-muted-foreground">
            Each cell is a district and each dot its center. Rings mark blocks moved after the solve.
          </p>
        </div>

        <figcaption>
          <p className="text-xs text-muted-foreground">
            Largest gap from {Math.round(data.target).toLocaleString("en-US")} people
          </p>
          <ol className="mt-1.5 space-y-1.5">
            {rows.map((row) => {
              const active = row.stage === stop.stage;
              return (
                <li key={row.stage} className="dd-home-stage" data-active={active || undefined}>
                  <span className="dd-led" data-state={active ? "on" : undefined} />
                  <span className="truncate text-[13px] @sm:text-sm">{row.label}</span>
                  <b>{gap(row.gap)}</b>
                  <small>{row.detail}</small>
                </li>
              );
            })}
          </ol>
        </figcaption>
      </figure>

      <p className="home-card-description mt-4 text-sm leading-6 text-muted-foreground">{demo.description}</p>
      <ul className="mt-4 flex flex-wrap gap-1.5">
        {demo.showcase.map((tag) => (
          <li key={tag} className="dd-home-tag">
            {tag}
          </li>
        ))}
      </ul>
      <div className="mt-auto flex items-center gap-1 pt-4 text-sm font-medium text-[var(--dd-olive-deep)]">
        Follow the algorithm
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

/** People, signed both ways: whole people above ten, two decimals below. */
function gap(value: number): string {
  return `±${value >= 10 ? Math.round(value).toLocaleString("en-US") : value.toFixed(2)}`;
}
