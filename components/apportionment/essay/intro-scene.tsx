"use client";

import { Play } from "lucide-react";
import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";
import {
  ROLES,
  mulberry32,
  personaDescription,
  withArticle,
  type PersonaPiece,
} from "@/lib/apportionment/persona";
import { cn } from "@/lib/utils";

import {
  PersonFigure,
  PIECE_COLORS,
  READABLE_ROWS,
  RUSH_STEPS,
  VIEW,
  type FigureMode,
} from "./person-figure";
import { usePersona } from "./persona";
import { useStateFocus } from "./state-focus";
import { StateTileMap } from "./state-map";

interface IntroSceneProps {
  /** 2020 seats per state, for the map's labels. */
  seats: Readonly<Record<string, number>>;
  /** 2020 national average apportionment population per seat. */
  nationalAverage: number;
}

/** Delays between occupations during the shuffle: fast, then settling. */
const SHUFFLE_DELAYS = [60, 60, 65, 70, 75, 85, 95, 110, 130, 155, 190, 240, 310];
const SETTLE_MS = 1300;
const JUST_MS = 1500;
/** Assembly beats, from the start of the assemble phase. */
const WIRE_MS = 0;
const SLIDE_MS = 1300;
const FIRST_PIECE_MS = 2300;
const PIECE_MS = 1700;
const RUSH_MS = 70;
const FULL = 3 + RUSH_STEPS;
/** Stage widths below this keep the figure centered with words underneath. */
const WIDE_STAGE = 500;
/** Wide stage: the figure slides left by this share of the stage. */
const SLIDE_SHARE = 0.2;
/** Wide stage: where a piece's words start, as a share of the stage width. */
const LABEL_LEFT = 0.5;

/**
 * The essay's first scene: choose a state, meet an imagined person there,
 * and watch them assemble from the many pieces of a life. The person's role
 * is shuffled and settles; their outline becomes a constellation; then the
 * figure steps aside and three pieces of their life arrive one at a time,
 * each named only while it flies in from its words, before a rush of
 * countless unnamed pieces fills the rest and the figure returns to center.
 * Timed but never scroll-locking; Skip and reduced motion land on the
 * finished person.
 */
export function IntroScene({ seats, nationalAverage }: IntroSceneProps) {
  const { focus } = useStateFocus();
  const { persona, phase, setPhase, personAt } = usePersona();
  const reducedMotion = useReducedMotion();
  const [shuffleRole, setShuffleRole] = React.useState<string | null>(null);
  const [settled, setSettled] = React.useState(false);
  const [showJust, setShowJust] = React.useState(false);
  const [mode, setMode] = React.useState<FigureMode>("plain");
  const [slid, setSlid] = React.useState(false);
  const [arrived, setArrived] = React.useState(0);
  const [push, setPush] = React.useState(false);
  const [showCoda, setShowCoda] = React.useState(false);

  const stageRef = React.useRef<HTMLDivElement | null>(null);
  const figureRef = React.useRef<HTMLDivElement | null>(null);
  const [stage, setStage] = React.useState({ width: 0, figureHeight: 0 });
  React.useEffect(() => {
    const node = stageRef.current;
    if (!node) return;
    const measure = () =>
      setStage({
        width: node.clientWidth,
        figureHeight: figureRef.current?.clientHeight ?? 0,
      });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const wide = stage.width >= WIDE_STAGE;

  // Drive the timed sequence from the phase. Every timer is cleared when the
  // phase changes (Skip, Replay, a new state), so nothing runs stale.
  React.useEffect(() => {
    if (!persona) return;
    const timers: number[] = [];
    const at = (ms: number, fn: () => void) => timers.push(window.setTimeout(fn, ms));
    const reset = () => {
      setShuffleRole(null);
      setSettled(false);
      setShowJust(false);
      setMode("plain");
      setSlid(false);
      setArrived(0);
      setPush(false);
      setShowCoda(false);
    };

    if (phase === "idle") {
      reset();
    } else if (phase === "complete") {
      setShuffleRole(persona.role.id);
      setSettled(true);
      setShowJust(true);
      setMode("assembled");
      setSlid(false);
      setArrived(FULL);
      setPush(false);
      if (reducedMotion) setShowCoda(true);
      else at(1400, () => setShowCoda(true));
    } else if (phase === "shuffle") {
      reset();
      const random = mulberry32(persona.seed ^ 0xa11);
      const others = ROLES.filter((r) => r.id !== persona.role.id);
      let t = 0;
      SHUFFLE_DELAYS.forEach((delay, i) => {
        const last = i === SHUFFLE_DELAYS.length - 1;
        const role = last ? persona.role : others[Math.floor(random() * others.length)];
        at(t, () => setShuffleRole(role.id));
        t += delay;
      });
      at(t + 200, () => setSettled(true));
      at(t + 200 + SETTLE_MS, () => setShowJust(true));
      at(t + 200 + SETTLE_MS + JUST_MS, () => setPhase("assemble"));
    } else if (phase === "assemble") {
      at(WIRE_MS, () => setMode("wire"));
      at(SLIDE_MS, () => setSlid(true));
      for (let k = 1; k <= 3; k++) at(FIRST_PIECE_MS + (k - 1) * PIECE_MS, () => setArrived(k));
      // The named pieces are done: back to center while the rest rush in.
      const rushStart = FIRST_PIECE_MS + 3 * PIECE_MS;
      at(rushStart, () => {
        setSlid(false);
        setPush(true);
      });
      for (let k = 4; k <= FULL; k++) at(rushStart + (k - 4) * RUSH_MS, () => setArrived(k));
      at(rushStart + RUSH_STEPS * RUSH_MS + 900, () => setPhase("complete"));
    }
    return () => timers.forEach((id) => window.clearTimeout(id));
  }, [phase, persona, reducedMotion, setPhase]);

  const begin = () => setPhase(reducedMotion ? "complete" : "shuffle");
  const running = phase === "shuffle" || phase === "assemble";
  const described = persona && focus && settled ? personaDescription(persona, focus.name) : null;
  const readable = persona ? persona.readable : null;
  const readableCategories = React.useMemo(
    () => readable?.map((piece) => piece.category),
    [readable]
  );
  /** The named piece now arriving: its words show only until the next one. */
  const current = phase === "assemble" && arrived >= 1 && arrived <= 3 ? arrived - 1 : null;

  // Geometry of the wide layout: how far the figure slides, and where each
  // piece's words sit, in the figure's own units (so its shard can fly from
  // them). Each label sits level with the spot its shard lands.
  const scale = stage.figureHeight / VIEW.height || 1;
  const shift = wide && slid ? stage.width * SLIDE_SHARE : 0;
  const sources = React.useMemo(() => {
    if (!wide || stage.figureHeight === 0) {
      return READABLE_ROWS.map(() => [VIEW.width / 2, VIEW.height + 70] as const);
    }
    const figureLeft = stage.width / 2 - stage.width * SLIDE_SHARE - (VIEW.width / 2) * scale;
    const labelX = stage.width * LABEL_LEFT;
    return READABLE_ROWS.map((y) => [(labelX - figureLeft) / scale, y] as const);
  }, [wide, stage, scale]);

  return (
    <section
      aria-label="Select a state and meet an imagined person there"
      className="mx-auto grid max-w-6xl items-start gap-8 px-4 pt-2 pb-10 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-12"
    >
      <StateTileMap seats={seats} nationalAverage={nationalAverage} className="mx-auto w-full max-w-xl lg:pt-6" />

      <div>
        <div
          ref={stageRef}
          className="relative text-story-ink"
        >
          <div className="flex min-h-[4.5rem] items-end justify-center px-6 pt-6 text-center">
            {described ? (
              <TypeIn
                key={described}
                text={described}
                instant={phase === "complete"}
                className="max-w-md font-sans text-lg leading-snug font-semibold"
              />
            ) : (
              // A stand-in for anyone there, not the reader: named by place.
              <p className="max-w-md font-sans text-lg leading-snug font-semibold">
                {focus ? `Someone in ${focus.name}` : "Someone, somewhere"}
              </p>
            )}
          </div>

          {/* The figure, centered except while its named pieces arrive. */}
          <div className="relative mt-4 flex justify-center">
            <div
              ref={figureRef}
              data-person-source=""
              className="relative"
              style={{
                // Once the person leaves for the crowd, the handoff draws them.
                opacity: personAt === "flight" || personAt === "crowd" ? 0 : 1,
                transform: `translateX(${-shift}px) scale(${push ? 1.05 : 1})`,
                transition: reducedMotion ? "none" : "transform 1000ms cubic-bezier(0.65, 0, 0.35, 1)",
              }}
            >
              <PersonFigure
                roleId={shuffleRole}
                mode={mode}
                arrived={arrived}
                highlight={current}
                readableCategories={readableCategories}
                sources={sources}
                seed={persona?.seed ?? 1}
                className="relative h-60 w-auto sm:h-72"
                title={described ?? "A generic person"}
              />
            </div>

            {/* The call to action sits on the figure itself, like a play button. */}
            {focus && phase === "idle" ? (
              <div className="absolute inset-x-0 top-[46%] z-10 flex -translate-y-1/2 justify-center">
                <span className="relative inline-flex">
                  <span
                    aria-hidden="true"
                    className="absolute inset-0 rounded-full bg-[color-mix(in_srgb,var(--story-ink)_55%,transparent)] opacity-0 motion-safe:animate-[story-pulse_2.6s_ease-out_infinite]"
                  />
                  <button
                    type="button"
                    onClick={begin}
                    className="relative flex items-center gap-2.5 rounded-full bg-story-ink py-3.5 pr-7 pl-5 font-sans text-lg font-semibold tracking-wide text-story-page shadow-md ring-1 ring-story-page/40 transition-transform hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-story-accent"
                  >
                    <Play aria-hidden="true" className="h-5 w-5 fill-current" />
                    Begin
                  </button>
                </span>
              </div>
            ) : null}

            {/* Decorative: it overlaps the Begin button, so it must never take clicks. */}
            {readable && wide ? (
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-y-0 right-[4%]"
                style={{ left: `${LABEL_LEFT * 100}%` }}
              >
                {readable.map((piece, i) => (
                  <PieceLabel
                    key={piece.text}
                    piece={piece}
                    visible={current === i}
                    top={(READABLE_ROWS[i] / VIEW.height) * stage.figureHeight}
                  />
                ))}
              </div>
            ) : null}
          </div>

          <div className="mt-1 h-5 text-center font-mono text-xs tracking-wide text-story-muted" aria-hidden="true">
            {phase === "shuffle" && !settled && shuffleRole
              ? ROLES.find((r) => r.id === shuffleRole)?.noun
              : null}
          </div>

          {/* Narration: real text, announced politely as it appears. */}
          <div
            className="mx-auto min-h-[9.5rem] max-w-md px-6 pt-2 pb-6 text-center font-story-serif text-xl leading-snug"
            aria-live="polite"
          >
            {!focus ? (
              <p className="text-story-ink-2">
                <span aria-hidden="true" className="hidden lg:inline">← </span>
                <span aria-hidden="true" className="lg:hidden">↑ </span>
                Select a state to begin.
              </p>
            ) : phase === "idle" ? (
              <>
                <p>Imagine a life in {focus.name}.</p>
                <p className="mt-1 font-sans text-sm text-story-muted">
                  A fictional person in a real congressional district.
                </p>
              </>
            ) : phase === "complete" ? (
              <>
                <p>A life full of responsibilities, convictions, contradictions, and hopes.</p>
                <p
                  className={cn(
                    "mt-2 text-story-ink-2 opacity-0 transition-opacity duration-700",
                    showCoda && "opacity-100"
                  )}
                >
                  And every person around them has a life just as full.
                </p>
              </>
            ) : showJust && persona ? (
              <p>But nobody is just {withArticle(persona.role.noun)}.</p>
            ) : null}
            {/* Narrow stage: the arriving piece's words under the figure. */}
            {readable && !wide && current !== null ? (
              <p
                key={readable[current].text}
                className="mt-3 flex items-center justify-center gap-2 font-sans text-sm"
                aria-hidden="true"
              >
                <span className="h-2.5 w-2.5 rounded-sm" style={{ background: PIECE_COLORS[readable[current].category] }} />
                <TypeIn text={readable[current].text} />
              </p>
            ) : null}
            {/* Screen readers: each piece as it arrives. */}
            {readable && current !== null ? <p className="sr-only">{readable[current].text}</p> : null}
          </div>
        </div>

        <div className="mt-3 flex min-h-10 items-center justify-center gap-3 font-sans text-sm">
          {focus && phase === "idle" ? (
            <>
              <button
                type="button"
                onClick={() => setPhase("complete")}
                className="px-2 py-2 text-story-ink-2 underline underline-offset-4 hover:text-story-ink"
              >
                Skip animation
              </button>
            </>
          ) : running ? (
            <button
              type="button"
              onClick={() => setPhase("complete")}
              className="px-2 py-2 text-story-ink-2 underline underline-offset-4 hover:text-story-ink"
            >
              Skip animation
            </button>
          ) : phase === "complete" ? (
            <>
              <span className="text-story-muted">Keep scrolling</span>
              {!reducedMotion ? (
                <button
                  type="button"
                  onClick={() => setPhase("shuffle")}
                  className="px-2 py-2 text-story-ink-2 underline underline-offset-4 hover:text-story-ink"
                >
                  Replay
                </button>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}

/**
 * One named piece beside the figure, level with where its shard lands: a
 * color key, then its words typed in. Shown only while that piece arrives.
 */
function PieceLabel({ piece, visible, top }: { piece: PersonaPiece; visible: boolean; top: number }) {
  return (
    <div
      className="absolute inset-x-0 flex -translate-y-1/2 items-center gap-2.5 font-sans text-sm leading-snug transition-opacity duration-300"
      style={{ top, opacity: visible ? 1 : 0 }}
    >
      <span
        className="h-3 w-3 shrink-0 rounded-[3px] transition-transform duration-500"
        style={{
          background: PIECE_COLORS[piece.category],
          transform: visible ? "scale(1)" : "scale(0)",
        }}
      />
      {visible ? <TypeIn text={piece.text} /> : <span className="invisible">{piece.text}</span>}
    </div>
  );
}

/**
 * Text typed in character by character with a caret. The full text holds
 * the layout from the start, and assistive tech reads it whole.
 */
function TypeIn({
  text,
  instant = false,
  className,
}: {
  text: string;
  instant?: boolean;
  className?: string;
}) {
  const reducedMotion = useReducedMotion();
  const [count, setCount] = React.useState(instant || reducedMotion ? text.length : 0);
  React.useEffect(() => {
    if (instant || reducedMotion) {
      setCount(text.length);
      return;
    }
    const perChar = Math.max(14, Math.min(32, 900 / text.length));
    const id = window.setInterval(() => {
      setCount((n) => {
        if (n >= text.length) window.clearInterval(id);
        return Math.min(text.length, n + 1);
      });
    }, perChar);
    return () => window.clearInterval(id);
  }, [text, instant, reducedMotion]);
  const typing = count < text.length;

  return (
    <span className={cn("relative inline-block", className)}>
      <span className="invisible">{text}</span>
      <span aria-hidden="true" className="absolute inset-0">
        {text.slice(0, count)}
        {typing ? <span className="ml-px inline-block h-[1em] w-[2px] translate-y-[0.15em] bg-current" /> : null}
      </span>
      <span className="sr-only">{text}</span>
    </span>
  );
}
