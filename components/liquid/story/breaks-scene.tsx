"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import * as React from "react";

import { useElementWidth } from "@/components/story/chart";
import { StoryFigure } from "@/components/story/story-figure";
import { district, pct, resident, share } from "@/lib/liquid/format";
import { levelKey, topicLabel, type BallotCode } from "@/lib/liquid/story-types";
import { INK, seriesColor } from "@/lib/story/palette";
import { cn } from "@/lib/utils";

import { BallotLegend, CityDots, OUTCOME_COLOR, ballotLook, type DotLook } from "./city-dots";
import { ClaimLabel, type Claim } from "./claim-label";
import {
  Edge,
  Orb,
  OrbDefs,
  Person,
  ReplayButton,
  along,
  easeInOut,
  lerp,
  span,
  trimmed,
  useScenePlayer,
  type Point,
} from "./stage";
import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

/*
 * Part 1 of the story, "where the machinery breaks", on the shared stage
 * (prompts/demo-5-walkthrough.md, items 11, 17, 10 and 18, described by Ben):
 * a delegate who does not vote drops the vote and it cracks, then the reader
 * swipes through the fixes that could catch it; residents with no record
 * grey out, then the same fixes; and a chain that ends in a loop, with loops
 * multiplying as turnout rises. Drawn from the illustrative city with the
 * frozen code; R2 (the fallback study) supplies the evidence for the
 * representative as default.
 */

// ---------------------------------------------------------------------------
// The fixes, and a picker to swipe through them
// ---------------------------------------------------------------------------

export type Fix = "problem" | "you" | "backup" | "representative" | "agent";

const FIXES: ReadonlyArray<{ key: Fix; label: string; claim: Claim | null }> = [
  { key: "problem", label: "The problem", claim: null },
  { key: "you", label: "You catch it", claim: null },
  { key: "backup", label: "A backup delegate", claim: "proposal" },
  { key: "representative", label: "The representative", claim: "exploratory" },
  { key: "agent", label: "A personal agent", claim: "proposal" },
];

/** Arrows and tabs through the fixes; arrow keys step through them too. */
function FixPicker({ value, onChange }: { value: Fix; onChange: (fix: Fix) => void }) {
  const index = FIXES.findIndex((f) => f.key === value);
  const step = (delta: number) => onChange(FIXES[(index + delta + FIXES.length) % FIXES.length].key);
  return (
    <div className="mb-3 flex items-center gap-2 font-sans text-xs">
      <button
        type="button"
        aria-label="Previous fix"
        onClick={() => step(-1)}
        className="rounded-md p-1 text-story-ink-2 ring-1 ring-story-rule hover:text-story-ink"
      >
        <ChevronLeft aria-hidden="true" className="h-4 w-4" />
      </button>
      <div
        role="tablist"
        aria-label="Ways to catch the vote"
        className="flex flex-1 flex-wrap gap-1.5"
        onKeyDown={(event) => {
          if (event.key === "ArrowRight") {
            event.preventDefault();
            step(1);
          } else if (event.key === "ArrowLeft") {
            event.preventDefault();
            step(-1);
          }
        }}
      >
        {FIXES.map((fix) => (
          <button
            key={fix.key}
            type="button"
            role="tab"
            aria-selected={fix.key === value}
            tabIndex={fix.key === value ? 0 : -1}
            onClick={() => onChange(fix.key)}
            className={cn(
              "rounded-md px-2.5 py-1 ring-1 ring-story-rule",
              fix.key === value ? "bg-story-ink font-medium text-story-page" : "text-story-ink-2 hover:text-story-ink"
            )}
          >
            {fix.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        aria-label="Next fix"
        onClick={() => step(1)}
        className="rounded-md p-1 text-story-ink-2 ring-1 ring-story-rule hover:text-story-ink"
      >
        <ChevronRight aria-hidden="true" className="h-4 w-4" />
      </button>
    </div>
  );
}

/** The chosen fix's label and what we know about it. */
function FixNote({ fix, children }: { fix: Fix; children: React.ReactNode }) {
  const claim = FIXES.find((f) => f.key === fix)?.claim;
  return (
    <p className="mt-3 font-sans text-sm text-story-ink-2">
      {claim ? (
        <span className="mr-1.5 inline-block align-middle">
          <ClaimLabel claim={claim} />
        </span>
      ) : null}
      {children}
    </p>
  );
}

/** Replays the scene whenever the reader picks another fix. */
function useFix(player: { replay: () => void }): [Fix, (fix: Fix) => void] {
  const [fix, setFix] = React.useState<Fix>("problem");
  const choose = React.useCallback(
    (next: Fix) => {
      setFix(next);
      player.replay();
    },
    [player]
  );
  return [fix, choose];
}

// ---------------------------------------------------------------------------
// Item 11: a delegate who does not vote
// ---------------------------------------------------------------------------

const LOST = { hop: 600, fall: 800, appear: 400, catchMove: 600, crack: 450, tail: 500 } as const;
const OUTCOME_TEXT = { m: "and it votes your way", c: "but it votes against you this time", n: "but it does not vote either: still lost" } as const;

export function LostVoteFigure() {
  const { city, measures, exploratory } = useStoryData();
  const lost = city.mechanism.lost;
  const swiss = measures.protocol.swiss_marker;
  const atSwiss = measures.levels[levelKey(swiss)].liquid;
  const fallbackSwiss = exploratory.fallback.levels[levelKey(swiss)].liquid_default;
  const bars = exploratory.agent_bars.levels[levelKey(swiss)];
  const path = lost?.path ?? [];
  const hops = Math.max(0, path.length - 1);
  const dropAt = LOST.hop * hops;
  const duration = dropAt + LOST.fall + LOST.crack + LOST.tail;
  const player = useScenePlayer(duration);
  const [fix, setFix] = useFix(player);
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const glow = `orb-${React.useId().replace(/:/g, "")}`;
  const t = player.t;
  if (!lost) return null;

  const color = seriesColor(lost.topic);
  const W = Math.max(width, 280);
  const H = 250;
  const top = 64;
  const ground = H - 28;
  const x0 = Math.max(44, W * 0.12);
  const x1 = W * (W < 480 ? 0.6 : 0.55);
  const node = (i: number): Point => ({ x: hops > 0 ? lerp(x0, x1, i / hops) : x0, y: top });
  const quitter = node(hops);
  const catcherAt: Point = fix === "you" ? node(0) : { x: Math.min(W - 52, x1 + 96), y: 150 };
  const representative = city.representatives[city.district[lost.voter]];
  const catcher = {
    you: { name: "You", person: lost.voter },
    backup: { name: "Your backup", person: lost.backup },
    representative: { name: "Your representative", person: representative },
    agent: { name: "Your personal agent", person: -1 },
  } as const;

  // The orb: along the path, then it falls from the delegate who did not vote
  let orb: Point = node(0);
  for (let i = 0; i < hops; i++) {
    if (t >= LOST.hop * i) orb = along(node(i), node(i + 1), easeInOut(span(t, LOST.hop * i, LOST.hop * (i + 1))));
  }
  const fall = span(t, dropAt, dropAt + LOST.fall);
  const caughtAt = 0.45;
  const catches = fix !== "problem";
  if (t >= dropAt) {
    const f = catches ? Math.min(fall, caughtAt) : fall;
    orb = { x: quitter.x, y: lerp(quitter.y, ground - 6, f * f) };
    if (catches && fall > caughtAt) {
      const mid = { x: quitter.x, y: lerp(quitter.y, ground - 6, caughtAt * caughtAt) };
      const x = span(t, dropAt + LOST.fall * caughtAt, dropAt + LOST.fall * caughtAt + LOST.catchMove);
      orb = along(mid, catcherAt, easeInOut(x));
    }
  }
  const crack = !catches ? span(t, dropAt + LOST.fall, dropAt + LOST.fall + LOST.crack) : 0;
  const catcherIn = catches ? span(t, dropAt - LOST.appear, dropAt) : 0;
  const settled = t >= duration - LOST.tail;
  const outcome = fix === "you" || fix === "backup" || fix === "representative" ? lost.catch[fix] : null;
  const missed = outcome === "n";
  const overheadBase = atSwiss.overhead;
  const overheadCaught = atSwiss.overhead + (atSwiss.lost_share ?? 0) * (atSwiss.delegated_share ?? 0);
  const caughtByYou = fix === "you" && settled;

  const rows = path.map((person, i) => ({
    step: i,
    who: resident(person),
    role: i === 0 ? "Hands the vote on" : i === hops ? "Does not vote" : "Hands it on",
  }));

  return (
    <StoryFigure
      title="A delegate who does not vote"
      subtitle={`${resident(lost.voter)}'s vote on ${topicLabel(city.topics[lost.topic]).toLowerCase()} reaches ${resident(lost.resolver)}, who does not vote. Swipe through the ways it could be caught.`}
      source="Primary city 1 at Swiss turnout, recomputed with the frozen code; the representative's evidence: eval/benchmarks/delegation_fallback_v1 (exploratory)"
      table={{
        caption: `The path of ${resident(lost.voter)}'s vote, and what each fix would have cast for them`,
        columns: [
          { key: "step", label: "Step", numeric: true },
          { key: "who", label: "Resident" },
          { key: "role", label: "What happens" },
        ],
        rows: [
          ...rows,
          { step: "", who: `Backup: ${resident(lost.backup)}`, role: describe(lost.catch.backup) },
          { step: "", who: `Representative: ${resident(representative)}`, role: describe(lost.catch.representative) },
          { step: "", who: `Themself: ${resident(lost.voter)}`, role: describe(lost.catch.you) },
        ],
      }}
    >
      <FixPicker value={fix} onChange={setFix} />
      <div ref={player.ref}>
        <div ref={measure}>
          {width > 0 ? (
            <svg width={W} height={H} role="img" aria-label={`A vote handed on and dropped by a delegate who does not vote; fix shown: ${FIXES.find((f) => f.key === fix)?.label}`} className="block font-sans">
              <OrbDefs id={glow} />
              <line x1={8} x2={W - 8} y1={ground} y2={ground} style={{ stroke: INK.grid }} strokeDasharray="4 4" />
              <text x={8} y={ground + 16} fontSize={10} style={{ fill: INK.muted }}>
                no ballot counts
              </text>
              {path.slice(0, -1).map((_, i) => (
                <Edge key={i} {...trimmed(node(i), node(i + 1), 10, 10)} color={color} progress={span(t, LOST.hop * i, LOST.hop * (i + 1))} />
              ))}
              {path.map((person, i) => (
                <Person
                  key={person}
                  {...node(i)}
                  r={i === 0 ? 13 : 10}
                  label={i === 0 ? `You: ${resident(person)}` : i === hops ? `${resident(person)}: does not vote` : String(person)}
                  labelAt={i === hops && i > 0 ? "below" : "above"}
                  emphasis={i === 0 || i === hops}
                />
              ))}
              {/* the delegate who did not vote, crossed out once the vote reaches them */}
              {t >= dropAt ? (
                <g transform={`translate(${quitter.x},${quitter.y})`} style={{ stroke: INK.secondary }} strokeWidth={1.6}>
                  <line x1={-6} y1={-6} x2={6} y2={6} />
                  <line x1={6} y1={-6} x2={-6} y2={6} />
                </g>
              ) : null}
              {catches && fix !== "you" ? (
                <g opacity={catcherIn}>
                  {fix === "agent" ? (
                    <rect x={catcherAt.x - 12} y={catcherAt.y - 12} width={24} height={24} rx={6} fill="none" style={{ stroke: INK.secondary }} strokeWidth={1.5} strokeDasharray="3 2" />
                  ) : (
                    <Person {...catcherAt} r={11} color={INK.secondary} />
                  )}
                  <text x={catcherAt.x} y={catcherAt.y + 28} textAnchor="middle" fontSize={11} fontWeight={600} style={{ fill: INK.primary }}>
                    {catcher[fix].name}
                  </text>
                  {catcher[fix].person >= 0 ? (
                    <text x={catcherAt.x} y={catcherAt.y + 42} textAnchor="middle" fontSize={11} style={{ fill: INK.secondary }}>
                      {resident(catcher[fix].person)}
                    </text>
                  ) : null}
                </g>
              ) : null}
              {crack > 0 ? <Shards at={{ x: quitter.x, y: ground - 4 }} progress={crack} color={color} /> : null}
              {crack === 0 ? (
                <Orb x={orb.x} y={orb.y} r={6} color={color} glowId={glow} opacity={missed && settled ? 0.35 : 1} />
              ) : null}
              {settled && catches ? (
                <text x={W - 8} y={22} textAnchor="end" fontSize={12} fontWeight={600} style={{ fill: INK.primary }}>
                  {fix === "agent" ? "Caught: accuracy unknown" : `Caught, ${OUTCOME_TEXT[outcome ?? "n"]}`}
                </text>
              ) : null}
              {settled && !catches ? (
                <text x={W - 8} y={22} textAnchor="end" fontSize={12} fontWeight={600} style={{ fill: INK.primary }}>
                  Lost: no ballot counts for {resident(lost.voter)}
                </text>
              ) : null}
            </svg>
          ) : (
            <div style={{ height: H }} />
          )}
        </div>
        {fix === "you" ? (
          <HealthBar label="Overhead at Swiss turnout" from={overheadBase} to={overheadCaught} grown={caughtByYou} />
        ) : null}
        <FixNote fix={fix}>
          {fix === "problem"
            ? `At Swiss turnout ${pct(atSwiss.lost_share ?? 0)} of delegated votes are lost this way. Whoever holds someone's vote casts it ${pct(atSwiss.resolver_attendance ?? 0, 0)} of the time.`
            : fix === "you"
              ? `Voting yourself always counts your own ballot, but it is work. If every resident caught their own dropped votes, overhead at Swiss turnout would rise from ${pct(overheadBase)} to ${pct(overheadCaught)}.`
              : fix === "backup"
                ? "Your second choice, from the same record: an existing idea known as ranked delegation. Untested here; the fallback study left it for a later declaration."
                : fix === "representative"
                  ? `Tested in the fallback study: with the representative as default, the share of votes with no ballot at Swiss turnout falls from ${pct(atSwiss.none_share)} to ${pct(fallbackSwiss.none_share ?? 0)}.`
                  : `A model of you, built from one interview (demo 2), casts the ballot. No accuracy is claimed: to beat the representative here it must match you more than ${pct(bars.representative)} of the time.`}
        </FixNote>
        <ReplayButton player={player} className="mt-3" />
      </div>
    </StoryFigure>
  );
}

function describe(code: "m" | "c" | "n"): string {
  return code === "m" ? "Would have cast a ballot that matches them" : code === "c" ? "Would have cast a ballot against them" : "Would not have voted either";
}

/** A cracked orb: shards flying apart. */
function Shards({ at, progress, color }: { at: Point; progress: number; color: string }) {
  const pieces = 7;
  return (
    <g pointerEvents="none" opacity={1 - progress * 0.4}>
      {Array.from({ length: pieces }, (_, i) => {
        const a = Math.PI + (i * Math.PI) / (pieces - 1);
        const d = 4 + progress * 18;
        const x = at.x + Math.cos(a) * d;
        const y = at.y + Math.sin(a) * d * 0.7;
        return <path key={i} d="M0,-3 L2.6,2 L-2.6,2 Z" transform={`translate(${x},${y}) rotate(${(i * 53) % 360})`} style={{ fill: color }} />;
      })}
    </g>
  );
}

/** Overhead, drawn like a health bar: it bumps up when you take on the work. */
function HealthBar({ label, from, to, grown }: { label: string; from: number; to: number; grown: boolean }) {
  const value = grown ? to : from;
  return (
    <div className="mt-3 font-sans text-xs">
      <div className="flex justify-between text-story-ink-2">
        <span>{label}</span>
        <span className="font-medium text-story-ink tabular-nums">{pct(value)}</span>
      </div>
      <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-story-rule">
        <span
          className="block h-full rounded-full transition-[width] duration-500"
          style={{ width: `${Math.min(1, value * 4) * 100}%`, background: INK.secondary }}
        />
      </div>
      <div className="mt-0.5 text-[0.7rem] text-story-muted">Drawn to a quarter of the scale, so the bump shows.</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Item 17: nobody to delegate to
// ---------------------------------------------------------------------------

const EMPTY = { greyOut: [300, 900], fixIn: [1100, 1700], tail: 300 } as const;
const UNKNOWN: DotLook = { color: INK.secondary, ring: true };
const GREY: DotLook = { color: INK.empty, ring: false };

export function EmptyRecordFigure() {
  const { city, measures, exploratory } = useStoryData();
  const { key, level, everyone } = useTurnout();
  const player = useScenePlayer(EMPTY.fixIn[1] + EMPTY.tail);
  const [fix, setFix] = useFix(player);
  const t = player.t;
  // With everyone voting every resident has a record, so the break cannot happen
  const at = everyone ? city.everyone : city.levels[key];
  const setting = everyone ? "with everyone voting" : `at turnout ${level}`;
  const empty = React.useMemo(
    () => Array.from(at.liquid_reason).flatMap((code, voter) => (code === "e" ? [voter] : [])),
    [at.liquid_reason]
  );
  const isEmpty = React.useMemo(() => new Set(empty), [empty]);
  const greyed = t >= EMPTY.greyOut[1] || span(t, EMPTY.greyOut[0], EMPTY.greyOut[1]) > 0.5;
  const fixed = fix !== "problem" && t >= EMPTY.fixIn[0];

  const outcomeOf = React.useCallback(
    (voter: number): DotLook => {
      if (fix === "you") return ballotLook(at.codes.direct[voter] as BallotCode);
      if (fix === "representative") return ballotLook(at.codes.representative[voter] as BallotCode);
      if (fix === "agent") return UNKNOWN;
      return GREY;
    },
    [fix, at.codes]
  );
  const looks = React.useMemo<DotLook[]>(
    () =>
      Array.from(at.codes.liquid, (code, voter) => {
        if (!isEmpty.has(voter)) return { ...ballotLook(code as BallotCode), color: INK.grid };
        if (fixed) return outcomeOf(voter);
        return greyed ? GREY : ballotLook(code as BallotCode);
      }),
    [at.codes.liquid, isEmpty, fixed, greyed, outcomeOf]
  );
  const counts = (looksFor: (voter: number) => DotLook) => {
    const tally = { match: 0, contrary: 0, none: 0 };
    for (const voter of empty) {
      const look = looksFor(voter);
      if (look.color === OUTCOME_COLOR.match) tally.match++;
      else if (look.color === OUTCOME_COLOR.contrary) tally.contrary++;
      else tally.none++;
    }
    return tally;
  };
  const now = counts(fix === "problem" ? () => GREY : outcomeOf);
  const frozen = measures.levels[key].liquid;
  const withDefault = exploratory.fallback.levels[key].liquid_default;

  return (
    <StoryFigure
      title={`Nobody to delegate to, ${setting}`}
      subtitle={
        everyone
          ? "With everyone voting, every resident has a record to choose a delegate by, so this break cannot happen. Move the dial to a turnout level to see it."
          : `${empty.length} of ${city.design.residents} residents have never voted, so they have no record to choose a delegate by. They keep the question, and rarely vote on it.`
      }
      source={
        everyone
          ? "Primary city 1 with everyone voting (exploratory)"
          : "Primary city 1, recomputed with the frozen code; the representative's evidence: eval/benchmarks/delegation_fallback_v1 (exploratory)"
      }
      table={{
        caption: `The ${empty.length} residents with no record, on one question, ${setting}`,
        columns: [
          { key: "fix", label: "Fix" },
          { key: "match", label: "Ballot matches them", numeric: true },
          { key: "contrary", label: "Ballot against them", numeric: true },
          { key: "none", label: "No ballot or unknown", numeric: true },
        ],
        rows: FIXES.map((f) => {
          const tally = counts(
            f.key === "problem"
              ? () => GREY
              : (voter) =>
                  f.key === "you"
                    ? ballotLook(at.codes.direct[voter] as BallotCode)
                    : f.key === "representative"
                      ? ballotLook(at.codes.representative[voter] as BallotCode)
                      : f.key === "agent"
                        ? UNKNOWN
                        : GREY
          );
          return { fix: f.label, match: tally.match, contrary: tally.contrary, none: tally.none };
        }),
      }}
    >
      {everyone ? null : <FixPicker value={fix} onChange={setFix} />}
      <div ref={player.ref}>
        <CityDots
          city={city}
          looks={looks}
          ariaLabel={
            everyone
              ? `With everyone voting, all ${city.design.residents} residents have a record.`
              : `Residents with no record on one question: ${now.match} ballots match them, ${now.contrary} are against them, ${now.none} have no ballot.`
          }
          tooltip={(voter) => (
            <div className="font-sans">
              <div className="font-semibold">
                {resident(voter)} · {district(city.district[voter])}
              </div>
              <div>{isEmpty.has(voter) ? "No record: has never voted" : "Has a record"}</div>
            </div>
          )}
        />
        <p className="mt-2 font-sans text-xs text-story-ink-2 tabular-nums">
          {everyone
            ? "Every resident has a record, so all are drawn faint: nobody is left without one to choose by."
            : fix === "problem"
              ? `Residents with a record are drawn faint. The ${empty.length} with none have no ballot from a delegate.`
              : `Under this fix, of the ${empty.length}: ${now.match} ballots match them, ${now.contrary} are against them, ${now.none} ${fix === "agent" ? "are unknown" : "have no ballot"}.`}
        </p>
        {everyone ? null : <BallotLegend className="mt-2" compact />}
        {everyone ? null : (
        <FixNote fix={fix}>
          {fix === "problem"
            ? `Under liquid delegation their fidelity is ${pct(frozen.empty_record_fidelity ?? 0)} at this turnout.`
            : fix === "you"
              ? "They decide for themselves, as under direct voting. They almost never vote, so almost no ballot counts."
              : fix === "backup"
                ? "A backup is chosen from the same record. With no record there is no backup either."
                : fix === "representative"
                  ? `Tested in the fallback study: with the representative as default, their fidelity at this turnout rises from ${pct(frozen.empty_record_fidelity ?? 0)} to ${pct(withDefault.empty_record_fidelity ?? 0)}.`
                  : "A model of them built from one interview casts their ballots. It needs no voting record, but no accuracy is claimed, so its ballots are shown as unknown."}
        </FixNote>
        )}
        <TurnoutDial className="mt-4 max-w-xl" />
        <ReplayButton player={player} className="mt-3" />
      </div>
    </StoryFigure>
  );
}

// ---------------------------------------------------------------------------
// Items 10 and 18: loops
// ---------------------------------------------------------------------------

const LOOP = { hop: 520, circle: 2, tail: 700 } as const;

export function LoopFigure() {
  const { city, measures, exploratory } = useStoryData();
  const { key, level, levels, swiss, everyone } = useTurnout();
  const { chain, handed_pairs: handed, handed_pairs_ending_on_loop: onLoop } = city.mechanism;
  const loop = chain.cycle;
  const color = seriesColor(chain.topic);
  const hops = chain.path.length - 1;
  const around = loop.length * LOOP.circle;
  const duration = (hops + around) * LOOP.hop + LOOP.tail;
  const player = useScenePlayer(duration);
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const glow = `orb-${React.useId().replace(/:/g, "")}`;
  const t = player.t;

  const W = Math.max(width, 280);
  const H = 230;
  const loopCenter: Point = { x: W - Math.min(80, W * 0.18), y: H / 2 };
  const loopRadius = 34;
  const loopNode = (j: number): Point => {
    const a = Math.PI + (j * 2 * Math.PI) / loop.length;
    return { x: loopCenter.x + Math.cos(a) * loopRadius, y: loopCenter.y + Math.sin(a) * loopRadius };
  };
  const chainEnd = loopNode(0).x;
  const start = 34;
  const node = (i: number): Point =>
    i >= hops
      ? loopNode(0)
      : { x: lerp(start, chainEnd - 40, hops > 1 ? i / (hops - 1) : 0), y: H / 2 + (i % 2 === 0 ? -24 : 24) };

  // Along the chain, round the loop twice, then the loop rule stops it
  const steps = [...chain.path.map((_, i) => node(i)), ...Array.from({ length: around }, (_, j) => loopNode((j + 1) % loop.length))];
  const step = Math.min(steps.length - 1, Math.floor(t / LOOP.hop));
  const within = span(t, step * LOOP.hop, (step + 1) * LOOP.hop);
  const orb = step < steps.length - 1 ? along(steps[step], steps[step + 1], easeInOut(within)) : steps[steps.length - 1];
  const ruled = t >= duration - LOOP.tail;

  const meter = [
    ...levels.map((l) => ({ label: String(l), value: measures.levels[levelKey(l)].liquid.loop_share ?? 0, current: !everyone && levelKey(l) === key, swiss: l === swiss })),
    { label: "Everyone", value: exploratory.everyone_votes.measures.liquid.loop_share ?? 0, current: everyone, swiss: false },
  ];
  const most = Math.max(...meter.map((m) => m.value));

  return (
    <StoryFigure
      title="Loops"
      subtitle={`When nearly everyone hands a topic over, chains have nowhere to end but a loop. At Swiss turnout ${share(onLoop, handed)} of handed-over votes in this city end at one.`}
      source="Primary city 1 at Swiss turnout, recomputed with the frozen code (the chain); eval/benchmarks/delegation_frontier_v1 and delegation_everyone_votes_v1 (the loop shares)"
      table={{
        caption: "Share of voter-question pairs on a loop, by turnout",
        columns: [
          { key: "turnout", label: "Turnout" },
          { key: "loop", label: "On a loop", numeric: true },
        ],
        rows: meter.map((m) => ({ turnout: m.label === "Everyone" ? "Everyone votes (exploratory)" : m.label, loop: pct(m.value) })),
      }}
    >
      <div ref={player.ref}>
        <div ref={measure}>
          {width > 0 ? (
            <svg width={W} height={H} role="img" aria-label={`A vote passes along ${chain.path.length} residents into a loop of ${loop.length}; everyone on the loop decides for themself.`} className="block font-sans">
              <OrbDefs id={glow} />
              {chain.path.slice(0, -1).map((_, i) => (
                <Edge key={i} {...trimmed(node(i), node(i + 1), 8, 8)} color={color} width={1.3} progress={span(t, i * LOOP.hop, (i + 1) * LOOP.hop)} />
              ))}
              {loop.map((_, j) => {
                const a = loopNode(j);
                const b = loopNode((j + 1) % loop.length);
                const bend = { x: loopCenter.x + (a.x + b.x - 2 * loopCenter.x) * 0.9, y: loopCenter.y + (a.y + b.y - 2 * loopCenter.y) * 0.9 };
                const shown = t >= hops * LOOP.hop;
                return shown ? (
                  <path
                    key={j}
                    d={`M${a.x},${a.y} Q${bend.x + (j === 0 ? 0 : 0)},${bend.y + (j === 0 ? -28 : 28)} ${b.x},${b.y}`}
                    fill="none"
                    style={{ stroke: color }}
                    strokeWidth={1.5}
                  />
                ) : null;
              })}
              {chain.path.slice(0, -1).map((person, i) => (
                <Person key={person} {...node(i)} r={i === 0 ? 10 : 7} label={i === 0 ? resident(person) : undefined} labelAt="above" emphasis={i === 0} />
              ))}
              {loop.map((person, j) => (
                <Person
                  key={person}
                  {...loopNode(j)}
                  r={9}
                  color={ruled ? color : undefined}
                  ring={ruled ? color : undefined}
                  label={W < 520 ? String(person) : resident(person)}
                  labelAt={j % 2 === 0 ? "below" : "above"}
                  emphasis={ruled}
                />
              ))}
              <Orb x={orb.x} y={orb.y} r={5.5} color={color} glowId={glow} opacity={ruled ? 0 : 1} />
              {ruled ? (
                <text x={W - 8} y={18} textAnchor="end" fontSize={12} fontWeight={600} style={{ fill: INK.primary }}>
                  The loop rule: everyone on a loop decides for themself
                </text>
              ) : null}
            </svg>
          ) : (
            <div style={{ height: H }} />
          )}
        </div>
        <ReplayButton player={player} className="mt-1" />
        <div className="mt-5 font-sans text-xs">
          <div className="mb-1.5 font-medium text-story-ink-2">Loops multiply as turnout rises: share of voter-question pairs on a loop</div>
          <div className="space-y-1">
            {meter.map((m) => (
              <div key={m.label} className="grid grid-cols-[4.5rem_minmax(0,1fr)_3rem] items-center gap-2">
                <span className={cn("tabular-nums", m.current ? "font-semibold text-story-ink" : "text-story-ink-2")}>
                  {m.label}
                  {m.swiss ? " CH" : ""}
                </span>
                <span className="h-2 overflow-hidden rounded-full bg-story-rule">
                  <span
                    className="block h-full rounded-full"
                    style={{ width: `${(m.value / most) * 100}%`, background: m.current ? color : INK.secondary }}
                  />
                </span>
                <span className={cn("text-right tabular-nums", m.current ? "font-semibold text-story-ink" : "text-story-ink-2")}>
                  {pct(m.value)}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-story-muted">
            The highlighted row follows the dial ({everyone ? "everyone votes" : `turnout ${level}`}); &ldquo;Everyone&rdquo; is
            the exploratory everyone-votes run.
          </p>
        </div>
        <TurnoutDial className="mt-4 max-w-xl" />
      </div>
    </StoryFigure>
  );
}
