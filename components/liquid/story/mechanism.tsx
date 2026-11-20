"use client";

import * as React from "react";

import { Annotation, AxisX, AxisY, useElementWidth } from "@/components/story/chart";
import { useScrollyStep } from "@/components/story/scrolly";
import { StoryFigure } from "@/components/story/story-figure";
import { dec, district, pct, resident, share } from "@/lib/liquid/format";
import { topicLabel, type Candidate } from "@/lib/liquid/story-types";
import { INK, seriesColor } from "@/lib/story/palette";
import { cn } from "@/lib/utils";

import { OUTCOME_COLOR } from "./city-dots";
import { useStoryData } from "./story-data";

/** §3's steps, in order: what the pinned figure shows at each. */
export const MECHANISM_STEPS = ["choose", "short", "route", "chain", "loop", "lost", "calibrate"] as const;
type MechanismStep = (typeof MECHANISM_STEPS)[number];

const CHOSEN = seriesColor(0);

/**
 * On a phone the figure pins above the step text, which already says what
 * a subtitle or note would; these hide there so the figure leaves the text
 * room. The source moves into the note slot to hide with its "Source:".
 */
function wide(node: React.ReactNode) {
  return <span className="max-lg:hidden">{node}</span>;
}
const SOURCE_NOTE = wide("Source: primary city 1 at Swiss turnout, recomputed with the frozen code.");

/**
 * §3, how it works: the mechanism acted out on the illustrative city at
 * Swiss turnout. Every resident, count and value is the frozen code's own
 * (scripts/build_liquid_example_city.py); the figure makes no claim of its own.
 */
export function MechanismGraphic() {
  const { step } = useScrollyStep();
  const current: MechanismStep = MECHANISM_STEPS[Math.min(step, MECHANISM_STEPS.length - 1)];
  const group =
    current === "choose" || current === "short"
      ? "choose"
      : current === "chain" || current === "loop" || current === "lost"
        ? "chain"
        : current;
  return (
    <div key={group} className="motion-safe:animate-[story-swap-in_480ms_cubic-bezier(0.2,0.7,0.2,1)_both]">
      {group === "choose" ? <CandidatesFigure short={current === "short"} /> : null}
      {group === "route" ? <RoutingFigure /> : null}
      {group === "chain" ? <ChainFigure mode={current as "chain" | "loop" | "lost"} /> : null}
      {group === "calibrate" ? <CalibrationFigure /> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Choosing a delegate from the record
// ---------------------------------------------------------------------------

interface CandidateRow {
  candidate: Candidate;
  kind: "showcase" | "short";
  chosen: boolean;
}

function CandidatesFigure({ short }: { short: boolean }) {
  const { city } = useStoryData();
  const { showcase, short_record: shortRecord, acceptance, credible_mass: mass, empty_records: empty } = city.mechanism;
  const topic = topicLabel(city.topics[showcase.topic]).toLowerCase();
  const delegate = showcase.delegates[showcase.topic];
  const rows: CandidateRow[] = [
    ...showcase.candidates.map((candidate) => ({
      candidate,
      kind: "showcase" as const,
      chosen: candidate.person === delegate,
    })),
    ...(short
      ? shortRecord.candidates.map((candidate) => ({ candidate, kind: "short" as const, chosen: false }))
      : []),
  ];

  const [ref, width] = useElementWidth<HTMLDivElement>();
  const narrow = width < 480;
  const labelWidth = narrow ? 112 : 188;
  const rowHeight = narrow ? 34 : 40;
  const gap = short ? 30 : 0;
  const top = 26;
  const plotWidth = Math.max(60, width - labelWidth - 12);
  const values = [...showcase.candidates, ...shortRecord.candidates].flatMap((c) => [c.lower, c.mean]);
  const lo = Math.floor((Math.min(...values, acceptance) - 0.02) * 20) / 20;
  const hi = Math.ceil((Math.max(...values, acceptance) + 0.02) * 20) / 20;
  const x = (value: number) => labelWidth + ((value - lo) / (hi - lo)) * plotWidth;
  const rowY = (index: number) =>
    top + index * rowHeight + (index >= showcase.candidates.length ? gap : 0) + rowHeight / 2;
  const height = top + rows.length * rowHeight + gap + 34;
  const ticks = Array.from({ length: Math.round((hi - lo) / 0.05) + 1 }, (_, i) => Number((lo + i * 0.05).toFixed(2)));

  return (
    <StoryFigure
      bare
      title={`Who should decide ${topic} for ${resident(showcase.voter)}?`}
      subtitle={wide(`${resident(showcase.voter)} has voted on ${showcase.record} of the ${city.design.history_per_topic} past questions on ${topic}. Each candidate's past votes are lined up against theirs.`)}
      note={SOURCE_NOTE}
      table={{
        caption: "Candidates ranked by the lower bound of their agreement",
        columns: [
          { key: "who", label: "Candidate" },
          { key: "matches", label: "Votes matching", numeric: true },
          { key: "mean", label: "Agreement estimate", numeric: true },
          { key: "lower", label: "Lower bound", numeric: true },
        ],
        rows: rows.map(({ candidate, kind }) => ({
          who: `${resident(candidate.person)}${kind === "short" ? ` (for ${resident(shortRecord.voter)})` : ""}`,
          matches: `${candidate.matches} of ${candidate.trials}`,
          mean: dec(candidate.mean),
          lower: dec(candidate.lower),
        })),
      }}
    >
      <div ref={ref}>
        {width > 0 ? (
          <svg width={width} height={height} className="block overflow-visible font-sans">
            <AxisX x={x} ticks={ticks} format={(v) => v.toFixed(2)} y={height - 34} grid />
            <line
              x1={x(acceptance)}
              x2={x(acceptance)}
              y1={top - 8}
              y2={height - 34}
              stroke={INK.primary}
              strokeWidth={1.25}
              strokeDasharray="4 3"
            />
            <text x={x(acceptance)} y={top - 13} textAnchor="middle" fontSize={11} fill={INK.primary}>
              Acceptance level {dec(acceptance)}
            </text>
            {short ? (
              <text x={0} y={rowY(showcase.candidates.length) - rowHeight / 2 - 6} fontSize={11} fill={INK.muted}>
                A resident with one ballot in the whole record
              </text>
            ) : null}
            {rows.map(({ candidate, kind, chosen }, index) => {
              const y = rowY(index);
              const color = chosen ? CHOSEN : kind === "short" ? OUTCOME_COLOR.contrary : INK.secondary;
              const label =
                kind === "short"
                  ? `${resident(shortRecord.voter)}'s best: ${candidate.person}`
                  : narrow
                    ? `${resident(candidate.person)}`
                    : `${resident(candidate.person)} · ${district(candidate.district)}`;
              const detail =
                kind === "short"
                  ? `${shortRecord.total_record} ballot in the record`
                  : `${candidate.matches} of ${candidate.trials} match`;
              return (
                <g key={`${kind}-${candidate.person}`}>
                  <text x={0} y={y - 3} fontSize={12} fontWeight={chosen ? 600 : 400} fill={INK.primary}>
                    {label}
                  </text>
                  <text x={0} y={y + 11} fontSize={11} fill={INK.muted}>
                    {detail}
                  </text>
                  <line x1={x(candidate.lower)} x2={x(candidate.mean)} y1={y} y2={y} stroke={color} strokeWidth={2} />
                  <line x1={x(candidate.lower)} x2={x(candidate.lower)} y1={y - 7} y2={y + 7} stroke={color} strokeWidth={2} />
                  <circle cx={x(candidate.mean)} cy={y} r={4.5} fill={color} stroke={INK.surface} strokeWidth={2} />
                  {chosen ? (
                    <text x={x(candidate.mean) + 9} y={y + 4} fontSize={11} fontWeight={600} fill={INK.primary}>
                      chosen
                    </text>
                  ) : null}
                  {kind === "short" ? (
                    <text x={x(candidate.mean) + 9} y={y + 4} fontSize={11} fill={INK.primary}>
                      keeps it
                    </text>
                  ) : null}
                </g>
              );
            })}
          </svg>
        ) : (
          <div style={{ height }} />
        )}
      </div>
      <p className="mt-2 font-sans text-xs leading-relaxed text-story-ink-2">
        Dot: the estimated share of votes they agree on. Tick: the lower end of its {pct(mass, 0)} credible
        interval, which ranks the candidates. Each estimate also borrows from the pair&apos;s agreement on the
        other topics, so the order can differ from the raw counts.
        {short
          ? ` ${empty.count} residents have no ballot at all to compare; they keep every topic.`
          : ""}
      </p>
    </StoryFigure>
  );
}

// ---------------------------------------------------------------------------
// A ballot arrives
// ---------------------------------------------------------------------------

function RoutingFigure() {
  const { city } = useStoryData();
  const { showcase, ballot } = city.mechanism;
  const onBallot = new Map(ballot.map((entry, order) => [entry.topic, order]));

  return (
    <StoryFigure
      bare
      title={`A ballot arrives for ${resident(showcase.voter)}`}
      subtitle={wide("Each question is filed under its topic and goes where they send that topic: to their delegate, or back to them.")}
      note={wide(
        "The study files every question under its true topic; a real router can err, which comes later. Source: primary city 1 at Swiss turnout, recomputed with the frozen code."
      )}
      table={{
        caption: `Where ${resident(showcase.voter)} sends each topic`,
        columns: [
          { key: "topic", label: "Topic" },
          { key: "delegate", label: "Handed to" },
          { key: "decides", label: "Decided by" },
        ],
        rows: city.topics.map((name, k) => ({
          topic: topicLabel(name),
          delegate: showcase.delegates[k] < 0 ? "Keeps it" : resident(showcase.delegates[k]),
          decides: resident(showcase.resolvers[k]),
        })),
      }}
    >
      <ul className="space-y-1 font-sans text-xs sm:space-y-1.5 sm:text-sm">
        {city.topics.map((name, k) => {
          const order = onBallot.get(k);
          const kept = showcase.delegates[k] < 0;
          const resolver = showcase.resolvers[k];
          const onward = !kept && resolver !== showcase.delegates[k];
          return (
            <li
              key={name}
              className={cn(
                "grid grid-cols-[4.75rem_minmax(0,1fr)] items-center gap-2 rounded-md px-2 py-1 sm:grid-cols-[7rem_minmax(0,1fr)] sm:gap-3 sm:py-1.5",
                order !== undefined ? "bg-story-page ring-1 ring-story-rule" : "opacity-60"
              )}
            >
              <span className="relative h-5 sm:h-6">
                {order !== undefined ? (
                  <span
                    className="absolute inset-y-0 left-0 inline-flex items-center rounded bg-story-ink px-1.5 text-[0.7rem] font-medium text-story-page motion-safe:animate-[story-swap-in_520ms_cubic-bezier(0.2,0.7,0.2,1)_both]"
                    style={{ animationDelay: `${order * 280}ms` }}
                  >
                    Question {order + 1}
                  </span>
                ) : null}
              </span>
              <span className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-medium text-story-ink">{topicLabel(name)}</span>
                <span className="text-story-muted" aria-hidden="true">
                  →
                </span>
                <span className={kept ? "font-semibold text-story-ink" : "text-story-ink-2"}>
                  {kept ? "keeps it: votes themself" : resident(showcase.delegates[k])}
                  {onward ? ` · decided by ${resident(resolver)}` : ""}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </StoryFigure>
  );
}

// ---------------------------------------------------------------------------
// Votes travel on, loops send them back, absent resolvers lose them
// ---------------------------------------------------------------------------

function Person({
  index,
  tone = "plain",
  delay,
  note,
}: {
  index: number;
  tone?: "plain" | "decides" | "absent";
  delay?: number;
  note?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex flex-col items-center rounded-full px-2.5 py-1 text-xs ring-1 motion-safe:animate-[story-swap-in_420ms_cubic-bezier(0.2,0.7,0.2,1)_both]",
        tone === "decides" && "bg-story-ink font-semibold text-story-page ring-story-ink",
        tone === "absent" && "bg-story-page text-story-muted ring-story-axis",
        tone === "plain" && "bg-story-surface text-story-ink ring-story-rule"
      )}
      style={delay !== undefined ? { animationDelay: `${delay}ms` } : undefined}
    >
      <span className="tabular-nums">{index}</span>
      {note ? <span className="text-[0.62rem] font-normal opacity-80">{note}</span> : null}
    </span>
  );
}

function Arrow({ delay, symbol = "→" }: { delay?: number; symbol?: string }) {
  return (
    <span
      aria-hidden="true"
      className="text-story-muted motion-safe:animate-[story-swap-in_420ms_both]"
      style={delay !== undefined ? { animationDelay: `${delay}ms` } : undefined}
    >
      {symbol}
    </span>
  );
}

function ChainFigure({ mode }: { mode: "chain" | "loop" | "lost" }) {
  const { city } = useStoryData();
  const { chain, loop, lost, loops_per_topic: loops, handed_pairs: handed, handed_pairs_ending_on_loop: onLoop } =
    city.mechanism;
  const step = 140;

  if (mode === "chain") {
    const end = chain.path[chain.path.length - 1];
    return (
      <StoryFigure
        bare
        title={`One resident's vote on ${topicLabel(city.topics[chain.topic]).toLowerCase()} passes through ${chain.path.length} people`}
        subtitle={wide("Each person applies their own delegation to the votes they receive, so a vote keeps moving until it reaches someone who decides.")}
        note={SOURCE_NOTE}
        table={{
          caption: "The chain, in order",
          columns: [
            { key: "step", label: "Step", numeric: true },
            { key: "who", label: "Resident" },
          ],
          rows: chain.path.map((person, index) => ({ step: index + 1, who: resident(person) })),
        }}
      >
        <p className="mb-2 font-sans text-xs text-story-muted">Residents, by number</p>
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-2 font-sans">
          {chain.path.map((person, index) => (
            <React.Fragment key={person}>
              {index > 0 ? <Arrow delay={index * step - 60} /> : null}
              <Person
                index={person}
                tone={person === end ? "decides" : "plain"}
                note={index === 0 ? "starts" : person === end ? "decides" : undefined}
                delay={index * step}
              />
            </React.Fragment>
          ))}
          {/* The loop the chain ends on: a pair hands the topic back and forth */}
          {chain.cycle.slice(1).map((person, index) => (
            <React.Fragment key={`loop-${person}`}>
              <Arrow symbol={chain.cycle.length === 2 ? "⇄" : "→"} delay={(chain.path.length + index) * step} />
              <Person index={person} note="loop" delay={(chain.path.length + index) * step + 60} />
            </React.Fragment>
          ))}
          {chain.cycle.length > 2 ? <Arrow symbol="↩" delay={(chain.path.length + chain.cycle.length) * step} /> : null}
        </div>
        {chain.ends === "loop" ? (
          <p
            className="mt-4 font-sans text-sm leading-relaxed text-story-ink-2 motion-safe:animate-[story-swap-in_480ms_both]"
            style={{ animationDelay: `${chain.path.length * step}ms` }}
          >
            {resident(end)}&apos;s own delegation leads round to them again
            {chain.cycle.length > 1 ? ` (through ${chain.cycle.slice(1).map(resident).join(", ")})` : ""}: a loop.
            Everyone on a loop decides for themself, so {resident(end)} casts the ballot for the whole chain.
          </p>
        ) : null}
      </StoryFigure>
    );
  }

  if (mode === "loop") {
    const [a, b] = loop.members;
    const total = loops.reduce((sum, n) => sum + n, 0);
    return (
      <StoryFigure
        bare
        title="Loops send votes back to their owners"
        subtitle={wide(`In ${topicLabel(city.topics[loop.topic]).toLowerCase()}, ${resident(a)} hands the topic to ${resident(b)}, and ${resident(b)} hands it straight back. Both decide for themselves.`)}
        note={SOURCE_NOTE}
        table={{
          caption: "Loops per topic",
          columns: [
            { key: "topic", label: "Topic" },
            { key: "loops", label: "Loops", numeric: true },
          ],
          rows: city.topics.map((name, k) => ({ topic: topicLabel(name), loops: loops[k] })),
        }}
      >
        <div className="flex items-center justify-center gap-3 py-4 font-sans">
          <Person index={a} tone="decides" note="decides" />
          <Arrow symbol="⇄" />
          <Person index={b} tone="decides" note="decides" />
        </div>
        <div className="mt-2 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="text-4xl font-semibold tracking-tight text-story-ink tabular-nums">{share(onLoop, handed)}</div>
            <p className="mt-1 font-sans text-xs leading-relaxed text-story-ink-2">
              of handed-over votes in this city end with someone on a loop ({onLoop.toLocaleString("en-US")} of{" "}
              {handed.toLocaleString("en-US")}). Nearly everyone delegates, so following delegates leads round in a
              circle.
            </p>
          </div>
          <div>
            <div className="text-4xl font-semibold tracking-tight text-story-ink tabular-nums">{total}</div>
            <p className="mt-1 font-sans text-xs leading-relaxed text-story-ink-2">
              loops across the {city.topics.length} topics: between {Math.min(...loops)} and {Math.max(...loops)} per
              topic.
            </p>
          </div>
        </div>
      </StoryFigure>
    );
  }

  return (
    <StoryFigure
      bare
      title="A delegate who does not vote leaves an empty ballot"
      subtitle={wide(
        lost
          ? `${resident(lost.resolver)} decides ${topicLabel(city.topics[city.question.topic]).toLowerCase()} for ${resident(lost.voter)}, but did not vote on this question. ${resident(lost.voter)} has no ballot on it.`
          : "Every resolver voted on the featured question."
      )}
      note={SOURCE_NOTE}
    >
      {lost ? (
        <div className="flex items-center justify-center gap-3 py-6 font-sans">
          <Person index={lost.voter} note="hands it on" />
          <Arrow />
          <Person index={lost.resolver} tone="absent" note="did not vote" delay={step} />
          <Arrow delay={2 * step} />
          <span
            className="rounded-md px-2 py-1 text-xs text-story-muted ring-1 ring-story-axis motion-safe:animate-[story-swap-in_420ms_both]"
            style={{ animationDelay: `${3 * step}ms` }}
          >
            no ballot counted
          </span>
        </div>
      ) : null}
      <p className="font-sans text-xs leading-relaxed text-story-ink-2">
        Delegates vote at their own rate, like everyone else. Representatives vote at the office-holder rate,{" "}
        {pct(city.design.office_rate, 0)}.
      </p>
    </StoryFigure>
  );
}

// ---------------------------------------------------------------------------
// The calibration
// ---------------------------------------------------------------------------

function CalibrationFigure() {
  const { city } = useStoryData();
  const { calibration, acceptance, cap, history_overhead: atLevel } = city.mechanism;
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const margin = { top: 16, right: 16, bottom: 40, left: 44 };
  const height = width < 480 ? 220 : 280;
  const plotWidth = Math.max(80, width - margin.left - margin.right);
  const plotHeight = height - margin.top - margin.bottom;
  const maxX = calibration[calibration.length - 1].acceptance;
  const x = (value: number) => (value / maxX) * plotWidth;
  const y = (value: number) => plotHeight - value * plotHeight;
  const path = calibration.map((p, i) => `${i ? "L" : "M"}${x(p.acceptance)},${y(p.overhead)}`).join("");

  return (
    <StoryFigure
      bare
      title="Each city's acceptance level: the strictest that keeps overhead at or under 10%"
      subtitle={wide("A stricter level hands over fewer topics, so more people decide for themselves. The rule takes the highest level at which overhead on the past questions stays at or under the cap.")}
      note={SOURCE_NOTE}
      table={{
        caption: "Overhead on past questions at each acceptance level",
        columns: [
          { key: "acceptance", label: "Acceptance level", numeric: true },
          { key: "overhead", label: "Overhead", numeric: true },
        ],
        rows: calibration.map((p) => ({ acceptance: dec(p.acceptance), overhead: pct(p.overhead) })),
      }}
    >
      <div ref={ref}>
        {width > 0 ? (
          <svg width={width} height={height} className="block overflow-visible font-sans">
            <g transform={`translate(${margin.left},${margin.top})`}>
              <AxisY y={y} ticks={[0, 0.25, 0.5, 0.75, 1]} format={(v) => pct(v, 0)} width={plotWidth} />
              <AxisX
                x={x}
                ticks={[0, 0.2, 0.4, 0.6, 0.8]}
                format={(v) => v.toFixed(1)}
                y={plotHeight}
                label="Acceptance level"
                width={plotWidth}
              />
              <line
                x1={0}
                x2={plotWidth}
                y1={y(cap)}
                y2={y(cap)}
                stroke={INK.primary}
                strokeWidth={1.25}
                strokeDasharray="4 3"
              />
              <text x={4} y={y(cap) - 6} fontSize={11} fill={INK.primary}>
                {pct(cap, 0)} cap
              </text>
              <path d={path} fill="none" stroke={CHOSEN} strokeWidth={2} />
              <circle cx={x(acceptance)} cy={y(atLevel)} r={5} fill={CHOSEN} stroke={INK.surface} strokeWidth={2} />
              <Annotation
                x={x(acceptance)}
                y={y(atLevel)}
                dx={-14}
                dy={-48}
                detail={`overhead ${pct(atLevel)}`}
              >
                {`Chosen: ${dec(acceptance)}`}
              </Annotation>
            </g>
          </svg>
        ) : (
          <div style={{ height }} />
        )}
      </div>
    </StoryFigure>
  );
}
