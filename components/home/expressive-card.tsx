"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";
import { scalarPresentationScore } from "@/lib/expressive-scalar-graph";
import sample from "@/lib/expressive-home-card.json";
import { cn } from "@/lib/utils";
import type { ScalarBallotState } from "@/types/expressive-scalar";

import { useCanHover, useInView } from "./card-hooks";
import { statusLabel, type ShowcaseDemo } from "./demo-types";
import styles from "./expressive-card.module.css";

type Vote = "yes" | "no" | "abstain";
type Voter = (typeof sample.voters)[number] & { binary_vote: Vote };
type Shape = Pick<ScalarBallotState, "ideal" | "lower_half_width" | "upper_half_width" | "approval_min" | "approval_max">;

const VOTERS = sample.voters as Voter[];
const STEP_MS = 1800;
/** First step after the pointer arrives: start promptly, not after a hold. */
const START_MS = 350;
const MORPH_MS = 650;
/** Rest on a voter near the 2022 rates, whose curve still says a lot. */
const REST = 3;

const W = 400, H = 168, LEFT = 8, RIGHT = W - 8, TOP = 14, BOTTOM = H - 22, DOMAIN = 10;
const px = (value: number) => LEFT + (RIGHT - LEFT) * Math.min(DOMAIN, Math.max(0, value)) / DOMAIN;
const py = (score: number) => BOTTOM - (BOTTOM - TOP) * score;
const r1 = (value: number) => Math.round(value * 10) / 10;
const pct = (value: number) => `${value.toFixed(2)}%`;
const GRID = Array.from({ length: 161 }, (_, index) => index * DOMAIN / 160);

/** The demo's own presentation score, sampled with exact clip edges. */
function curvePath(shape: Shape): { line: string; fill: string } {
  const ballot = { ...shape, probe: shape.ideal };
  const edges = [shape.approval_min, shape.approval_max].flatMap((edge) => [edge - 1e-6, edge, edge + 1e-6]);
  const xs = [...GRID, shape.ideal, ...edges].filter((x) => x >= 0 && x <= DOMAIN).sort((a, b) => a - b);
  const points = xs.map((x) => `${r1(px(x))},${r1(py(scalarPresentationScore(ballot, x).score))}`);
  const line = `M${points.join(" L")}`;
  return { line, fill: `${line} L${px(DOMAIN)},${BOTTOM} L${px(0)},${BOTTOM} Z` };
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
function blend(from: Shape, to: Shape, t: number): Shape {
  return {
    ideal: lerp(from.ideal, to.ideal, t),
    lower_half_width: lerp(from.lower_half_width, to.lower_half_width, t),
    upper_half_width: lerp(from.upper_half_width, to.upper_half_width, t),
    approval_min: lerp(from.approval_min, to.approval_min, t),
    approval_max: lerp(from.approval_max, to.approval_max, t),
  };
}

/** Smoothly morph the drawn curve between voters; snaps under reduced motion. */
function useMorph(target: Shape, animate: boolean): Shape {
  const [shape, setShape] = React.useState(target);
  const current = React.useRef(target);
  React.useEffect(() => {
    if (!animate) { current.current = target; setShape(target); return; }
    const from = current.current;
    const start = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      // A frame's timestamp can precede `start`; clamp so the blend never
      // extrapolates past either voter into an invalid ballot.
      const t = Math.min(1, Math.max(0, (now - start) / MORPH_MS));
      const eased = 1 - (1 - t) ** 3;
      current.current = blend(from, target, eased);
      setShape(current.current);
      if (t < 1) frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [target, animate]);
  return shape;
}

const VOTE_TEXT: Record<Vote, string> = { yes: "Marks YES", no: "Marks NO", abstain: "No mark" };

/**
 * Demo 6's home card, in the demo's two-zone identity: a monochrome answer
 * sheet up top, a colour field of preference curves below. The card scrolls
 * through real voters from the demo's seeded electorate (ordered by ideal
 * rate, as in the voter browser). Each curve morphs into the next while the
 * answer sheet shows the single mark that curve produces: many shapes, a few
 * ovals. Curves use the demo's own scoring function; the sample is a
 * committed artifact checked against the Python fixture.
 *
 * Rests on one voter and plays while hovered or focused; leaving returns to
 * rest. Touch screens play while the card is on screen. Reduced motion holds
 * still.
 */
export function ExpressiveCard({ demo }: { demo: ShowcaseDemo }) {
  const reducedMotion = useReducedMotion();
  const canHover = useCanHover();
  const visible = useInView<HTMLAnchorElement>();
  const [hovered, setHovered] = React.useState(false);
  const [step, setStep] = React.useState(REST);
  const started = React.useRef(false);
  const playing = !reducedMotion && (canHover ? hovered : visible.inView);

  React.useEffect(() => {
    if (!playing) {
      started.current = false;
      setStep(REST);
      return;
    }
    const timer = window.setTimeout(() => {
      started.current = true;
      setStep((current) => (current + 1) % VOTERS.length);
    }, started.current ? STEP_MS : START_MS);
    return () => window.clearTimeout(timer);
  }, [step, playing]);

  const voter = VOTERS[step];
  const shape = useMorph(voter, !reducedMotion);
  const path = React.useMemo(() => curvePath(shape), [shape]);
  const ghosts = React.useMemo(() => VOTERS.map((v) => ({ id: v.id, vote: v.binary_vote, d: curvePath(v).line })), []);
  const thumbs = React.useMemo(() => VOTERS.map((v) => curvePath(v).line), []);
  const tally = sample.binary_tally;

  const card = (
    <div className={cn(styles.card, "flex h-full flex-col transition-shadow hover:shadow-md")}>
      {/* Part one: the answer sheet. */}
      <div className={styles.sheetZone}>
        <span className={styles.timingMarks} aria-hidden />
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-2xl leading-tight font-semibold tracking-[-0.025em]">{demo.title}</h2>
          <span className={styles.status}>{statusLabel[demo.status]}</span>
        </div>
        <p className="mt-2 text-lg leading-snug text-[var(--quiet)]">{demo.tagline}</p>
        <div className={styles.ballotRow} aria-live="polite">
          <span className={styles.ballotLabel}>Prop 121</span>
          {(["yes", "no"] as const).map((choice) => (
            <span key={choice} className={styles.choice}>
              {choice === "yes" ? "YES" : "NO"}
              <b className={styles.oval}>
                <em key={`${voter.id}-${choice}`} className={cn(styles.mark, voter.binary_vote === choice && styles.marked, reducedMotion && styles.still)} />
              </b>
            </span>
          ))}
          <span className={styles.voteNote}>{VOTE_TEXT[voter.binary_vote]}</span>
        </div>
      </div>
      <span className={styles.edge} aria-hidden />

      {/* Part two: the curves behind those marks. */}
      <figure className={styles.field}>
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img"
          aria-label={`${voter.label}'s rate curve: ideal ${pct(voter.ideal)}, accepts ${pct(voter.approval_min)} to ${pct(Math.min(voter.approval_max, 100))}. Their yes/no ballot: ${VOTE_TEXT[voter.binary_vote].toLowerCase()}.`}>
          <line x1={LEFT} x2={RIGHT} y1={BOTTOM} y2={BOTTOM} className={styles.axis} />
          {ghosts.map((ghost) => <path key={ghost.id} d={ghost.d} className={cn(styles.ghost, styles[ghost.vote])} />)}
          {[{ rate: sample.proposal, label: "Yes 4.40" }, { rate: sample.status_quo, label: "No 4.55" }].map(({ rate, label }, index) => (
            <g key={label}>
              <line x1={px(rate)} x2={px(rate)} y1={TOP - 4} y2={BOTTOM} className={styles.marker} />
              <text x={px(rate) + (index ? 4 : -4)} y={TOP + 2} textAnchor={index ? "start" : "end"} className={styles.markerLabel}>{label}</text>
            </g>
          ))}
          <g className={styles[voter.binary_vote]}>
            <path d={path.fill} className={styles.area} />
            <path d={path.line} className={styles.curve} />
            <circle cx={px(shape.ideal)} cy={py(1)} r={4} className={styles.peak} />
          </g>
          {[0, 2, 4, 6, 8, 10].map((value) => (
            <text key={value} x={px(value)} y={H - 6} textAnchor={value === 0 ? "start" : value === 10 ? "end" : "middle"} className={styles.tick}>{value}%</text>
          ))}
        </svg>
        <figcaption className={styles.readout}>
          <span>{voter.label}</span>
          <span>Ideal {pct(voter.ideal)}</span>
          <span>Accepts {pct(voter.approval_min)}–{voter.approval_max >= 100 ? "100%" : pct(voter.approval_max)}</span>
        </figcaption>
        <div className={styles.strip} aria-hidden>
          <div className={styles.stripTrack} style={{ transform: `translateX(-${step * 3.25 + 1.5}rem)` }}>
            {thumbs.map((d, index) => (
              <svg key={VOTERS[index].id} viewBox={`0 0 ${W} ${H}`} className={cn(styles.thumb, styles[VOTERS[index].binary_vote], index === step && styles.current)}>
                <path d={d} />
              </svg>
            ))}
          </div>
        </div>
        <p className={styles.tally}>
          {sample.electorate_size} curves collapse to <span className={styles.yes}>{tally.yes} yes</span> · <span className={styles.no}>{tally.no} no</span> · <span className={styles.abstain}>{tally.abstain} unmarked</span>
        </p>
      </figure>

      <div className="flex flex-1 flex-col px-6 pb-6">
        <p className="home-card-description text-sm leading-6 text-[var(--quiet)]">{demo.description}</p>
        <ul className="mt-4 flex flex-wrap gap-1.5">
          {demo.showcase.map((tag) => <li key={tag} className={styles.tag}>{tag}</li>)}
        </ul>
        <div className="mt-auto flex items-center gap-1 pt-4 text-sm font-medium text-[var(--teal)]">
          Try both ballots
          <ArrowRight className="h-4 w-4" />
        </div>
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
