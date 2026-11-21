"use client";

import * as React from "react";

import { AxisX, AxisY, useElementWidth } from "@/components/story/chart";
import { StoryFigure } from "@/components/story/story-figure";
import { observeThemeChanges, resolveCssColor } from "@/lib/canvas-color";
import { dec, pct } from "@/lib/liquid/format";
import type { RouterExample } from "@/lib/liquid/story-types";
import { INK, SEQUENTIAL, seriesColor } from "@/lib/story/palette";
import { cn } from "@/lib/utils";

import { ReplayButton, along, easeInOut, easeOut, lerp, span, useScenePlayer, type Point } from "./stage";
import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

/*
 * Part 4 of the story, "where it still struggles", on the shared stage
 * (prompts/demo-5-walkthrough.md, items 21, 20, 27, 26 and 22, "as
 * proposed"): a question routed against a voter's written categories; the
 * cold start as a timeline; the personal agent against its bars; the
 * per-voter ceiling walking the handover curve; and votes borrowed from
 * people who rarely vote. Every number comes from the generated data.
 */

// ---------------------------------------------------------------------------
// Item 21: routing a question against a voter's own categories
// ---------------------------------------------------------------------------

const VERDICT: Record<RouterExample["verdict"], { tab: string; result: (e: RouterExample, t: number) => string }> = {
  correct_delegation: {
    tab: "Sent to the right delegate",
    result: (e) => `Sent to the delegate for “${text(e, e.chosen)}”, the right topic.`,
  },
  false_keep: {
    tab: "Kept by mistake",
    result: (e, t) => {
      const right = e.categories.find((c) => c.acceptable);
      return `Kept: “${right?.text}” is the right topic, but scored ${dec(right?.probability ?? 0, 2)}, under ${t}.`;
    },
  },
  false_delegation: {
    tab: "Sent to the wrong delegate",
    result: (e) => `Sent to the delegate for “${text(e, e.chosen)}”, which the question is not about.`,
  },
};

function text(example: RouterExample, key: string | null): string {
  return example.categories.find((c) => c.key === key)?.text ?? "";
}

const ROUTE = { bar: 520, stagger: 160, threshold: 300, settle: 600 } as const;

export function RoutingScene() {
  const { results } = useStoryData();
  const { examples, operating, model } = results.router;
  const [index, setIndex] = React.useState(0);
  const example = examples[index];
  const n = example.categories.length;
  const barsDone = n * ROUTE.stagger + ROUTE.bar;
  const duration = barsDone + ROUTE.threshold + ROUTE.settle;
  const player = useScenePlayer(duration);
  const t = player.t;
  const threshold = operating.threshold;
  const thresholdIn = span(t, barsDone, barsDone + ROUTE.threshold);
  const settled = span(t, barsDone + ROUTE.threshold, duration);

  return (
    <StoryFigure
      title="A question meets a voter's own categories"
      subtitle={`The decision model scores how far the question is about each category the voter wrote. Anything under ${threshold} drops out; the highest score left wins, or the voter keeps it.`}
      source={`eval/benchmarks/delegation_router_v1: scores recorded from ${model}; the categories, questions and right answers were written by one author`}
      note="Three cases from the benchmark's 544, chosen by a fixed rule: the first sent right with three or more categories, the first kept by mistake and the first sent wrong."
      table={{
        caption: `Scores for “${example.question.title}”`,
        columns: [
          { key: "category", label: "Voter's category" },
          { key: "score", label: "Score", numeric: true },
          { key: "right", label: "Right topic" },
        ],
        rows: example.categories.map((c) => ({ category: c.text, score: dec(c.probability, 2), right: c.acceptable ? "Yes" : "No" })),
      }}
    >
      <div role="tablist" aria-label="Routing cases" className="mb-4 flex flex-wrap gap-1.5 font-sans text-xs">
        {examples.map((e, i) => (
          <button
            key={e.verdict}
            type="button"
            role="tab"
            aria-selected={i === index}
            onClick={() => {
              setIndex(i);
              player.replay();
            }}
            className={cn(
              "rounded-md px-2.5 py-1 ring-1 ring-story-rule",
              i === index ? "bg-story-ink font-medium text-story-page" : "text-story-ink-2 hover:text-story-ink"
            )}
          >
            {VERDICT[e.verdict].tab}
          </button>
        ))}
      </div>
      <div ref={player.ref} className="font-sans">
        <div className="rounded-lg p-3 ring-1 ring-story-rule">
          <div className="text-xs font-medium text-story-muted uppercase">Ballot question</div>
          <div className="mt-1 text-sm font-semibold text-story-ink">{example.question.title}</div>
          <div className="mt-0.5 text-xs text-story-ink-2">{example.question.summary}</div>
        </div>
        <div className="relative mt-4 space-y-2.5">
          {example.categories.map((c, i) => {
            const grown = easeOut(span(t, i * ROUTE.stagger, i * ROUTE.stagger + ROUTE.bar));
            const out = c.probability < threshold;
            const chosen = c.key === example.chosen;
            return (
              <div key={c.key} className={cn("text-xs transition-opacity", out && settled > 0 ? "opacity-45" : "opacity-100")}>
                <div className="flex justify-between gap-3">
                  <span className={cn("text-story-ink-2", chosen && settled > 0 && "font-semibold text-story-ink")}>
                    {chosen && settled > 0 ? "→ " : ""}
                    {c.text}
                    {c.acceptable ? <span className="ml-1.5 text-story-muted">(right topic)</span> : null}
                  </span>
                  <span className="tabular-nums text-story-ink">{dec(c.probability * grown, 2)}</span>
                </div>
                <div className="relative mt-1 h-2 rounded-full bg-story-rule">
                  <span
                    className="absolute inset-y-0 left-0 rounded-full"
                    style={{
                      width: `${c.probability * grown * 100}%`,
                      background: chosen && settled > 0 ? seriesColor(0) : INK.secondary,
                    }}
                  />
                </div>
              </div>
            );
          })}
          {/* the threshold, down through every bar */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-1 -bottom-1"
            style={{ left: `${threshold * 100}%`, opacity: thresholdIn }}
          >
            <div className="h-full border-l-2 border-dashed" style={{ borderColor: INK.primary }} />
            <div className="absolute -top-4 -translate-x-1/2 text-[0.7rem] font-medium whitespace-nowrap text-story-ink">
              threshold {threshold}
            </div>
          </div>
        </div>
        <p className="mt-4 text-sm font-medium text-story-ink" style={{ opacity: settled }}>
          {VERDICT[example.verdict].result(example, threshold)}
        </p>
        <ReplayButton player={player} className="mt-3" />
      </div>
    </StoryFigure>
  );
}

// ---------------------------------------------------------------------------
// Item 20: the cold start
// ---------------------------------------------------------------------------

export function ColdStartScene() {
  const { city, measures } = useStoryData();
  const swiss = measures.protocol.swiss_marker;
  const at = measures.levels[String(swiss)].liquid;
  const history = city.design.history_per_topic * city.design.topics;
  const evaluation = city.design.evaluation_per_topic * city.design.topics;
  const total = history + evaluation;
  const duration = 3200;
  const player = useScenePlayer(duration);
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const t = player.t;

  const W = Math.max(width, 280);
  const H = 150;
  const margin = { left: 8, right: 8, top: 26, bottom: 30 };
  const plotW = W - margin.left - margin.right;
  const plotH = H - margin.top - margin.bottom;
  const x = (q: number) => margin.left + (q / total) * plotW;
  const y = (share: number) => margin.top + (1 - share) * plotH;
  const shown = easeInOut(span(t, 200, duration - 400)) * total;
  const average = shown > 0 ? (Math.min(shown, history) + Math.max(0, shown - history) * at.overhead) / shown : 1;
  const done = t >= duration - 400;

  return (
    <StoryFigure
      title="The cold start, as a timeline"
      subtitle={`Before anyone can choose by record, the record is built: ${history} questions on which everyone decides everything. Then delegation brings the work down to ${pct(at.overhead)}.`}
      source="eval/benchmarks/delegation_frontier_v1 (lifecycle overhead at Swiss turnout); the city's design"
      table={{
        caption: "Overhead over the city's life, at Swiss turnout",
        columns: [
          { key: "period", label: "Period" },
          { key: "questions", label: "Questions", numeric: true },
          { key: "overhead", label: "Overhead", numeric: true },
        ],
        rows: [
          { period: "Building the record", questions: history, overhead: "100%" },
          { period: "Delegating", questions: evaluation, overhead: pct(at.overhead) },
          { period: "Over both", questions: total, overhead: pct(at.lifecycle_overhead ?? 0) },
        ],
      }}
    >
      <div ref={player.ref}>
        <div ref={measure}>
          {width > 0 ? (
            <svg width={W} height={H} role="img" aria-label={`Overhead over the city's life: 100% for ${history} questions, then ${pct(at.overhead)}; ${pct(at.lifecycle_overhead ?? 0)} over both.`} className="block font-sans">
              <rect x={x(0)} y={y(1)} width={x(Math.min(shown, history)) - x(0)} height={y(0) - y(1)} style={{ fill: INK.secondary }} opacity={0.75} />
              {shown > history ? (
                <rect x={x(history)} y={y(at.overhead)} width={x(shown) - x(history)} height={y(0) - y(at.overhead)} style={{ fill: seriesColor(0) }} />
              ) : null}
              <line x1={x(0)} x2={x(total)} y1={y(0)} y2={y(0)} style={{ stroke: INK.axis }} />
              <line x1={x(history)} x2={x(history)} y1={y(1) - 6} y2={y(0)} style={{ stroke: INK.muted }} strokeDasharray="3 3" />
              <text x={x(0)} y={y(1) - 8} fontSize={11} style={{ fill: INK.secondary }}>
                Building the record: everyone decides everything
              </text>
              <text x={x(total)} y={y(at.overhead) - 6} textAnchor="end" fontSize={11} style={{ fill: INK.secondary }}>
                Delegating
              </text>
              <text x={x(0)} y={H - 10} fontSize={11} style={{ fill: INK.muted }}>
                Questions over time →
              </text>
              <text x={x(total)} y={H - 10} textAnchor="end" fontSize={12} fontWeight={600} style={{ fill: INK.primary }} className="tabular-nums">
                {done ? `Over both: ${pct(at.lifecycle_overhead ?? 0)}` : `So far: ${pct(average)}`}
              </text>
            </svg>
          ) : (
            <div style={{ height: H }} />
          )}
        </div>
        <p className="mt-2 font-sans text-xs text-story-ink-2">
          The longer a city runs after its history, the closer its overhead comes to {pct(at.overhead)}; the study
          scores {evaluation} questions after it.
        </p>
        <ReplayButton player={player} className="mt-3" />
      </div>
    </StoryFigure>
  );
}

// ---------------------------------------------------------------------------
// Item 27: the personal agent
// ---------------------------------------------------------------------------

const INTERVIEW = ["Should the city borrow to fix roads?", "How much would you pay for faster buses?", "Which matters more: rents or green space?"];

export function AgentScene() {
  const { exploratory } = useStoryData();
  const { key, level } = useTurnout();
  const bars = exploratory.agent_bars.levels[key];
  const duration = 3400;
  const player = useScenePlayer(duration);
  const t = player.t;
  const lo = 0.5;
  const at = (value: number) => `${((value - lo) / (1 - lo)) * 100}%`;

  return (
    <StoryFigure
      title="A personal agent, against its bars"
      subtitle="One interview builds a model of the voter; the model casts the ballots they would leave empty. How often those ballots would match them is unknown."
      source="Demo 2's preference interview (the model); the bars from eval/benchmarks/delegation_frontier_v1, at the dial's turnout (proposal arithmetic)"
      note="The interview questions are illustrations, not demo 2's bank. No accuracy is claimed."
      table={{
        caption: `What a personal agent's ballots must match at turnout ${level}`,
        columns: [
          { key: "bar", label: "To beat" },
          { key: "value", label: "Ballots matching more than", numeric: true },
        ],
        rows: [
          { bar: "A representative default", value: pct(bars.representative) },
          { bar: "A chosen delegate", value: pct(bars.delegate) },
        ],
      }}
    >
      <div ref={player.ref} className="font-sans text-xs">
        <div className="grid gap-4 sm:grid-cols-[1.3fr_auto_1fr_auto_1fr] sm:items-center">
          <div className="space-y-1.5">
            <div className="font-medium text-story-ink-2">1. One interview</div>
            {INTERVIEW.map((q, i) => (
              <div
                key={q}
                className="rounded-lg rounded-bl-sm bg-story-rule/60 px-2.5 py-1.5 text-story-ink-2 transition-opacity"
                style={{ opacity: span(t, 200 + i * 350, 500 + i * 350) }}
              >
                {q}
              </div>
            ))}
          </div>
          <div aria-hidden="true" className="hidden text-story-muted sm:block" style={{ opacity: span(t, 1300, 1500) }}>
            →
          </div>
          <div style={{ opacity: span(t, 1400, 1800) }}>
            <div className="font-medium text-story-ink-2">2. A model of the voter</div>
            <div className="mt-1.5 rounded-lg border border-dashed px-3 py-4 text-center text-story-ink" style={{ borderColor: INK.secondary }}>
              their preferences, as a model
            </div>
          </div>
          <div aria-hidden="true" className="hidden text-story-muted sm:block" style={{ opacity: span(t, 1900, 2100) }}>
            →
          </div>
          <div style={{ opacity: span(t, 2000, 2400) }}>
            <div className="font-medium text-story-ink-2">3. Ballots they would skip</div>
            <div className="mt-1.5 flex gap-1.5">
              {[0, 1, 2, 3].map((i) => (
                <span
                  key={i}
                  className="flex h-9 w-7 items-center justify-center rounded ring-1 ring-story-rule text-story-ink"
                  style={{ opacity: span(t, 2100 + i * 150, 2300 + i * 150) }}
                >
                  ?
                </span>
              ))}
            </div>
          </div>
        </div>
        <div className="mt-6" style={{ opacity: span(t, 2600, 3200) }}>
          <div className="mb-1 font-medium text-story-ink-2">How often its ballots must match the voter</div>
          <div className="relative h-8 rounded bg-story-rule/50">
            <div
              className="absolute inset-y-1 rounded"
              style={{ left: at(lo), right: "0%", background: "repeating-linear-gradient(45deg, transparent 0 6px, rgba(127,127,127,0.18) 6px 12px)" }}
            />
            {[
              { value: bars.representative, label: "beats a representative default" },
              { value: bars.delegate, label: "beats a chosen delegate" },
            ].map((bar, i) => (
              <div key={bar.label} className="absolute inset-y-0" style={{ left: at(bar.value) }}>
                <div className="h-full border-l-2" style={{ borderColor: INK.primary }} />
                <div className={cn("absolute whitespace-nowrap text-[0.7rem] text-story-ink", i === 0 ? "top-full mt-0.5 -translate-x-1/2" : "bottom-full mb-0.5 -translate-x-1/2")}>
                  {pct(bar.value)} {bar.label}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-6 flex justify-between text-[0.7rem] text-story-muted">
            <span>50% (a coin flip)</span>
            <span>The hatched band: its accuracy, unknown</span>
            <span>100%</span>
          </div>
        </div>
        <TurnoutDial className="mt-4 max-w-xl" />
        <ReplayButton player={player} className="mt-3" />
      </div>
    </StoryFigure>
  );
}

// ---------------------------------------------------------------------------
// Item 26: the per-voter ceiling on the handover curve
// ---------------------------------------------------------------------------

const CEILING = { step: 420, tail: 700 } as const;

export function CeilingScene() {
  const { exploratory } = useStoryData();
  const { key, level } = useTurnout();
  const curve = exploratory.handover.levels[key];
  const depths = curve.length - 1;
  const duration = (depths + 1) * CEILING.step + CEILING.tail;
  const player = useScenePlayer(duration);
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const t = player.t;
  const best = curve.reduce((b, p) => (p.fidelity > b.fidelity ? p : b), curve[0]);

  const W = Math.max(width, 280);
  const H = 230;
  const margin = { left: 44, right: 16, top: 20, bottom: 40 };
  const plotW = W - margin.left - margin.right;
  const plotH = H - margin.top - margin.bottom;
  const lowY = Math.floor(Math.min(...curve.map((p) => p.fidelity)) * 20) / 20;
  const highY = Math.ceil(Math.max(...curve.map((p) => p.fidelity)) * 20) / 20;
  const x = (depth: number) => (depth / depths) * plotW;
  const y = (f: number) => plotH - ((f - lowY) / Math.max(0.05, highY - lowY)) * plotH;
  const walked = Math.min(depths, Math.floor(t / CEILING.step));
  const within = span(t, walked * CEILING.step, (walked + 1) * CEILING.step);
  const marker: Point =
    walked < depths
      ? along({ x: x(walked), y: y(curve[walked].fidelity) }, { x: x(walked + 1), y: y(curve[walked + 1].fidelity) }, easeInOut(within))
      : { x: x(depths), y: y(curve[depths].fidelity) };
  const at = curve[Math.min(depths, Math.round(lerp(0, depths, Math.min(1, t / (depths * CEILING.step)))))];
  const done = t >= duration - CEILING.tail;
  const path = curve
    .filter((p) => p.depth <= walked + 1)
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.depth)},${y(p.fidelity)}`)
    .join(" ");

  return (
    <StoryFigure
      title={`Handing over one topic at a time, at turnout ${level}`}
      subtitle={`Each voter hands over their best topics first. A point walks the curve from voting on everything (0) to handing over all ${depths}; where it peaks is the most a voter should hand over at this turnout.`}
      source="eval/benchmarks/delegation_handover_v1 (exploratory), mean over the 200 primary cities"
      table={{
        caption: `Fidelity and overhead by topics handed over, at turnout ${level}`,
        columns: [
          { key: "depth", label: "Topics handed over", numeric: true },
          { key: "fidelity", label: "Fidelity", numeric: true },
          { key: "overhead", label: "Overhead", numeric: true },
        ],
        rows: curve.map((p) => ({ depth: p.depth, fidelity: dec(p.fidelity), overhead: pct(p.overhead) })),
      }}
    >
      <div ref={player.ref}>
        <div ref={measure}>
          {width > 0 ? (
            <svg width={W} height={H} role="img" aria-label={`Fidelity by topics handed over at turnout ${level}; it peaks at ${best.depth}.`} className="block font-sans">
              <g transform={`translate(${margin.left},${margin.top})`}>
                <AxisY y={y} ticks={[lowY, (lowY + highY) / 2, highY]} format={(v) => dec(v, 2)} width={plotW} />
                <AxisX x={x} ticks={Array.from({ length: depths + 1 }, (_, d) => d)} format={(v) => String(v)} y={plotH} label="Topics handed over" width={plotW} />
                <path d={path} fill="none" style={{ stroke: seriesColor(0) }} strokeWidth={2} />
                {done ? (
                  <g transform={`translate(${x(best.depth)},${y(best.fidelity)})`}>
                    <circle r={9} fill="none" style={{ stroke: INK.primary }} strokeWidth={1.5} />
                    <text y={-14} textAnchor={best.depth > depths / 2 ? "end" : "start"} fontSize={11} fontWeight={600} style={{ fill: INK.primary }}>
                      {best.depth === 0 ? "Peak: keep everything" : best.depth === depths ? "Peak: hand over everything" : `Peak: hand over ${best.depth}`}
                    </text>
                  </g>
                ) : null}
                <circle cx={marker.x} cy={marker.y} r={5} style={{ fill: seriesColor(0), stroke: INK.surface }} strokeWidth={2} />
              </g>
            </svg>
          ) : (
            <div style={{ height: H }} />
          )}
        </div>
        <p className="mt-1 font-sans text-xs text-story-ink-2 tabular-nums">
          At {at.depth} {at.depth === 1 ? "topic" : "topics"}: fidelity {dec(at.fidelity)}, overhead {pct(at.overhead)}.
        </p>
        <TurnoutDial className="mt-4 max-w-xl" />
        <ReplayButton player={player} className="mt-3" />
      </div>
    </StoryFigure>
  );
}

// ---------------------------------------------------------------------------
// Item 22: engagement, borrowed
// ---------------------------------------------------------------------------

const BORROW = { appear: 500, start: 600, fly: 1100, spread: 1300, tail: 600 } as const;
const BINS = [200, 400, 600, 800, 1001] as const;
const BIN_COLOR = [SEQUENTIAL[100], SEQUENTIAL[200], SEQUENTIAL[400], SEQUENTIAL[500], SEQUENTIAL[700]] as const;

export function BorrowedEngagementScene() {
  const { city } = useStoryData();
  const { key, level } = useTurnout();
  const rates = city.turnout[key];
  const resolver = city.levels[key].liquid_resolver;
  const n = rates.length;
  const order = React.useMemo(() => [...Array(n).keys()].sort((a, b) => rates[a] - rates[b] || a - b), [rates, n]);
  const slot = React.useMemo(() => {
    const at = new Array<number>(n);
    order.forEach((voter, i) => (at[voter] = i));
    return at;
  }, [order, n]);
  const handing = React.useMemo(() => [...Array(n).keys()].filter((v) => resolver[v] !== v), [resolver, n]);
  const held = React.useMemo(() => {
    const counts = new Map<number, number>();
    for (const v of handing) counts.set(resolver[v], (counts.get(resolver[v]) ?? 0) + 1);
    return counts;
  }, [handing, resolver]);
  const meanRate = (people: number[], weight?: (v: number) => number) => {
    let total = 0;
    let weights = 0;
    for (const v of people) {
      const w = weight ? weight(v) : 1;
      total += rates[v] * w;
      weights += w;
    }
    return weights ? total / weights / 1000 : 0;
  };
  const handerRate = meanRate(handing);
  const deciderRate = meanRate([...held.keys()], (v) => held.get(v) ?? 0);
  const duration = BORROW.start + BORROW.spread + BORROW.fly + BORROW.tail;
  const player = useScenePlayer(duration);
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const canvas = React.useRef<HTMLCanvasElement | null>(null);
  const [colors, setColors] = React.useState<string[] | null>(null);
  const t = player.t;

  const W = Math.max(width, 280);
  const columns = 25;
  const rows = Math.ceil(n / columns);
  const spacing = Math.min(16, (W - 16) / columns);
  const H = rows * spacing + 16;
  const dot = (voter: number): Point => ({
    x: 8 + (slot[voter] % columns) * spacing + spacing / 2,
    y: 8 + Math.floor(slot[voter] / columns) * spacing + spacing / 2,
  });

  React.useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const resolve = () => setColors([...BIN_COLOR.map((c) => resolveCssColor(node, c)), resolveCssColor(node, INK.primary)]);
    resolve();
    return observeThemeChanges(resolve);
  }, [width]);

  React.useEffect(() => {
    const node = canvas.current;
    if (!node || !colors || width === 0) return;
    const dpr = window.devicePixelRatio || 1;
    node.width = Math.round(W * dpr);
    node.height = Math.round(H * dpr);
    const ctx = node.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const binOf = (rate: number) => BINS.findIndex((b) => rate < b);
    ctx.globalAlpha = span(t, 0, BORROW.appear);
    for (let v = 0; v < n; v++) {
      const p = dot(v);
      ctx.fillStyle = colors[binOf(rates[v])];
      ctx.beginPath();
      ctx.arc(p.x, p.y, spacing * 0.3, 0, Math.PI * 2);
      ctx.fill();
    }
    // Each handed-over vote flies to whoever decides it
    const arrived = new Map<number, number>();
    ctx.fillStyle = colors[colors.length - 1];
    handing.forEach((v) => {
      const start = BORROW.start + (slot[v] / n) * BORROW.spread;
      if (t < start) return;
      const x = span(t, start, start + BORROW.fly);
      if (x >= 1) {
        arrived.set(resolver[v], (arrived.get(resolver[v]) ?? 0) + 1);
        return;
      }
      const p = along(dot(v), dot(resolver[v]), easeInOut(x));
      ctx.globalAlpha = 0.8;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 1.8, 0, Math.PI * 2);
      ctx.fill();
    });
    // Deciders ringed, growing with the votes they hold
    ctx.globalAlpha = 1;
    ctx.strokeStyle = colors[colors.length - 1];
    ctx.lineWidth = 1.5;
    for (const [d, count] of arrived) {
      const p = dot(d);
      ctx.beginPath();
      ctx.arc(p.x, p.y, spacing * 0.3 + Math.sqrt(count) * 1.2, 0, Math.PI * 2);
      ctx.stroke();
    }
    // `W`, `H`, `spacing` and the helpers derive from width and the city
  }, [t, colors, width, n, rates, handing, resolver, slot]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <StoryFigure
      title={`Engagement, borrowed, at turnout ${level}`}
      subtitle={`Residents are sorted by how often they vote, the rarest voters first. Each handed-over vote on one question flies to whoever decides it. Those who hand over vote on ${pct(handerRate)} of questions on average; whoever decides for them, ${pct(deciderRate)}.`}
      source="Primary city 1, recomputed with the frozen code"
      note="The decider's average is weighted by the votes they hold."
      table={{
        caption: `Turnout of those who hand over and of whoever decides for them, at turnout ${level}`,
        columns: [
          { key: "who", label: "Residents" },
          { key: "count", label: "Number", numeric: true },
          { key: "rate", label: "Average own turnout", numeric: true },
        ],
        rows: [
          { who: "Hand their vote over", count: handing.length, rate: pct(handerRate) },
          { who: "Decide for others", count: held.size, rate: pct(deciderRate) },
        ],
      }}
    >
      <div ref={player.ref}>
        <div ref={measure} className="flex justify-center">
          {width > 0 ? (
            <canvas
              ref={canvas}
              role="img"
              aria-label={`Votes flow from residents who vote on ${pct(handerRate)} of questions to deciders who vote on ${pct(deciderRate)}.`}
              style={{ width: W, height: H }}
            />
          ) : (
            <div style={{ height: 340 }} />
          )}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 font-sans text-xs text-story-ink-2">
          <span>Votes on:</span>
          {["Under 20%", "20–40%", "40–60%", "60–80%", "80% or more"].map((label, i) => (
            <span key={label} className="inline-flex items-center gap-1.5">
              <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: BIN_COLOR[i] }} />
              {label}
            </span>
          ))}
          <span className="inline-flex items-center gap-1.5">
            <svg width={12} height={12} aria-hidden="true">
              <circle cx={6} cy={6} r={4.5} fill="none" style={{ stroke: INK.primary }} strokeWidth={1.5} />
            </svg>
            ringed: decides for others
          </span>
        </div>
        <TurnoutDial className="mt-4 max-w-xl" />
        <ReplayButton player={player} className="mt-3" />
      </div>
    </StoryFigure>
  );
}

