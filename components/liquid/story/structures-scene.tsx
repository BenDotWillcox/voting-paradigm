"use client";

import * as React from "react";

import { useElementWidth } from "@/components/story/chart";
import { StoryFigure } from "@/components/story/story-figure";
import { observeThemeChanges, resolveCssColor } from "@/lib/canvas-color";
import { pct, resident } from "@/lib/liquid/format";
import { ARRANGEMENT_LABEL, topicLabel, type Arrangement } from "@/lib/liquid/story-types";
import { DIVERGING, INK, seriesColor } from "@/lib/story/palette";

import {
  Ballot,
  Edge,
  Orb,
  OrbDefs,
  Person,
  ReplayButton,
  Segments,
  along,
  easeInOut,
  easeOut,
  lerp,
  span,
  trimmed,
  useScenePlayer,
  type Point,
} from "./stage";
import { useStoryData } from "./story-data";

/*
 * Part 1 of the story, "the idea", on the shared stage
 * (prompts/demo-5-walkthrough.md, items 1, 2 and 3, described by Ben): a
 * vote from question to winner, then the four arrangements as structures,
 * one per beat, each sending the same resident's eight topic votes to
 * whoever decides them. Drawn from the illustrative city with everyone
 * voting (the R1 setting); the shares under each structure are R1's
 * averages over the 200 cities. Illustrations, except those shares.
 */

const SOURCE = "Primary city 1 with everyone voting (the R1 setting), recomputed with the frozen code";
const YES = DIVERGING.positive;
const NO = DIVERGING.negative;

// ---------------------------------------------------------------------------
// Item 1: a vote, end to end
// ---------------------------------------------------------------------------

const END_TO_END = { card: [0, 500], reach: [500, 1300], fly: 900, spread: 1800, start: 1300, tail: 700 } as const;

export function VoteEndToEndFigure() {
  const { city } = useStoryData();
  const votes = city.everyone.featured_votes;
  const n = votes.length;
  const yes = Array.from(votes).filter((v) => v === "y").length;
  const no = n - yes;
  const winner = city.everyone.winners.direct[city.question.index] === "y" ? "Yes" : "No";
  const duration = END_TO_END.start + END_TO_END.spread + END_TO_END.fly + END_TO_END.tail;
  const player = useScenePlayer(duration);
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const canvas = React.useRef<HTMLCanvasElement | null>(null);
  const [colors, setColors] = React.useState<Record<string, string> | null>(null);
  const glow = `orb-${React.useId().replace(/:/g, "")}`;
  const t = player.t;

  const W = Math.max(width, 280);
  const H = 360;
  const columns = 20;
  const rows = Math.ceil(n / columns);
  const spacing = Math.min(11, (W * 0.58) / columns, (H - 96) / rows);
  const grid = { x: 14, y: 84 };
  const dot = (i: number): Point => ({
    x: grid.x + (i % columns) * spacing + spacing / 2,
    y: grid.y + Math.floor(i / columns) * spacing + spacing / 2,
  });
  const option = (choice: "y" | "n"): Point => ({ x: W - 58, y: choice === "y" ? H * 0.36 : H * 0.74 });
  const cardAt: Point = { x: grid.x + (columns * spacing) / 2, y: 40 };
  const startOf = (i: number) => END_TO_END.start + (i / n) * END_TO_END.spread;

  React.useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const resolve = () =>
      setColors({
        quiet: resolveCssColor(node, INK.muted),
        yes: resolveCssColor(node, YES),
        no: resolveCssColor(node, NO),
      });
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
    // The question reaches everyone: a sweep from the top row down
    const reach = span(t, END_TO_END.reach[0], END_TO_END.reach[1]);
    for (let i = 0; i < n; i++) {
      const p = dot(i);
      const lit = Math.floor(i / columns) / rows <= reach;
      const voted = t >= startOf(i);
      ctx.globalAlpha = voted ? 0.35 : lit ? 1 : 0.35;
      ctx.fillStyle = lit ? (votes[i] === "y" ? colors.yes : colors.no) : colors.quiet;
      ctx.beginPath();
      ctx.arc(p.x, p.y, spacing * 0.32, 0, Math.PI * 2);
      ctx.fill();
    }
    // Each ballot goes to the option it chooses
    for (let i = 0; i < n; i++) {
      const start = startOf(i);
      if (t < start || t >= start + END_TO_END.fly) continue;
      const choice = votes[i] as "y" | "n";
      const p = along(dot(i), option(choice), easeInOut(span(t, start, start + END_TO_END.fly)));
      ctx.fillStyle = choice === "y" ? colors.yes : colors.no;
      ctx.globalAlpha = 0.3;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 2.2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    // `W`, `H`, `spacing` and the helpers derive from width
  }, [t, colors, width, n, votes]); // eslint-disable-line react-hooks/exhaustive-deps

  const arrived = (choice: "y" | "n") => {
    let count = 0;
    for (let i = 0; i < n; i++) if (votes[i] === choice && t >= startOf(i) + END_TO_END.fly) count++;
    return count;
  };
  const shown = { y: arrived("y"), n: arrived("n") };
  const card = easeOut(span(t, END_TO_END.card[0], END_TO_END.card[1]));
  const shrink = easeInOut(span(t, END_TO_END.reach[0], END_TO_END.reach[1]));
  const decided = span(t, duration - END_TO_END.tail, duration);
  const total = Math.max(1, Math.max(yes, no));

  return (
    <StoryFigure
      title="A vote, from question to winner"
      subtitle={`One question reaches all ${n} residents of one city. With everyone voting, each ballot goes to the option it chooses, and the tally picks the winner.`}
      source={SOURCE}
      note="An illustration of how any arrangement turns ballots into a decision; here everyone votes for themself."
      table={{
        caption: `The ${n} residents' votes on the featured question (${topicLabel(city.topics[city.question.topic])})`,
        columns: [
          { key: "option", label: "Option" },
          { key: "votes", label: "Votes", numeric: true },
        ],
        rows: [
          { option: "Yes", votes: yes },
          { option: "No", votes: no },
        ],
      }}
    >
      <div ref={player.ref}>
        <div ref={measure} className="relative">
          {width > 0 ? (
            <>
              <canvas ref={canvas} aria-hidden="true" style={{ width: W, height: H }} className="block" />
              <svg
                width={W}
                height={H}
                role="img"
                aria-label={`${n} residents vote: ${yes} yes and ${no} no. ${winner} wins.`}
                className="absolute inset-0 font-sans"
              >
                <OrbDefs id={glow} />
                <Ballot x={cardAt.x} y={cardAt.y} scale={lerp(0.6, 1, card) * (1 - 0.55 * shrink)} opacity={card * (1 - shrink)} accent={INK.secondary} />
                {(["y", "n"] as const).map((choice) => {
                  const p = option(choice);
                  const count = shown[choice];
                  const wins = (choice === "y" ? "Yes" : "No") === winner;
                  const radius = 8 + 18 * Math.sqrt(count / total);
                  return (
                    <g key={choice}>
                      {wins && decided > 0 ? (
                        <circle cx={p.x} cy={p.y} r={radius + 6} fill="none" style={{ stroke: INK.primary }} strokeWidth={2} opacity={decided} />
                      ) : null}
                      <circle cx={p.x} cy={p.y} r={radius} style={{ fill: choice === "y" ? YES : NO }} opacity={0.9} />
                      <text x={p.x} y={p.y - radius - 10} textAnchor="middle" fontSize={12} fontWeight={600} style={{ fill: INK.primary }}>
                        {choice === "y" ? "Yes" : "No"}
                      </text>
                      <text x={p.x} y={p.y + radius + 16} textAnchor="middle" fontSize={12} style={{ fill: INK.secondary }} className="tabular-nums">
                        {count}
                        {wins && decided > 0.5 ? " · wins" : ""}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </>
          ) : (
            <div style={{ height: H }} />
          )}
        </div>
        <ReplayButton player={player} className="mt-3" />
      </div>
    </StoryFigure>
  );
}

// ---------------------------------------------------------------------------
// Items 2 and 3: the four structures, one per beat
// ---------------------------------------------------------------------------

export type Structure = "direct" | "representative" | "proxy" | "liquid";

const STRUCTURE_TIMING = { appear: [0, 300], travel: 400, stagger: 70, move: 800, neighbours: [500, 1700], tail: 300 } as const;
/** How many of the district's other residents are drawn, standing for all of them. */
const NEIGHBOURS = 24;

const CAPTION: Record<Structure, string> = {
  direct: "You decide every topic yourself.",
  representative:
    "Dilution: you share one representative with everyone in your district. Bundling: they stand for you on every topic.",
  proxy: "Your own person, so no dilution. Still one person for every topic: bundling.",
  liquid: "A person for each topic: no dilution, and no bundling.",
};

export function StructureFigure({ kind }: { kind: Structure }) {
  const { city, exploratory } = useStoryData();
  const { typical } = city.everyone;
  const topics = city.topics.length;
  const shares = exploratory.everyone_votes.measures[kind as Arrangement];
  const duration =
    STRUCTURE_TIMING.travel + topics * STRUCTURE_TIMING.stagger + STRUCTURE_TIMING.move + STRUCTURE_TIMING.tail +
    (kind === "representative" ? 400 : 0);
  const player = useScenePlayer(duration);
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const glow = `orb-${React.useId().replace(/:/g, "")}`;
  const t = player.t;

  const W = Math.max(width, 280);
  const H = 190;
  const you: Point = { x: Math.max(56, W * 0.2), y: H / 2 - 6 };
  const youR = 14;
  const right = W - Math.min(110, W * 0.28);
  const single: Point = { x: right, y: H / 2 - 6 };

  // Where each topic's vote ends up, and the people drawn there
  const people =
    kind === "liquid" ? [...new Set(typical.delegates.filter((d) => d >= 0))] : [];
  const slot = (person: number): Point => ({
    x: right,
    y: people.length > 1 ? 16 + (people.indexOf(person) * (H - 44)) / (people.length - 1) : H / 2,
  });
  /** Where a topic's vote comes to rest: gathered round whoever decides it. */
  const target = (topic: number): Point => {
    if (kind === "direct") return { x: you.x + 46 + (topic % 4) * 12, y: you.y - 8 + Math.floor(topic / 4) * 16 };
    if (kind === "liquid") {
      const person = typical.delegates[topic];
      if (person < 0) return you;
      const held = typical.delegates.flatMap((d, k) => (d === person ? [k] : []));
      const p = slot(person);
      return { x: p.x - 16, y: p.y + (held.indexOf(topic) - (held.length - 1) / 2) * 9 };
    }
    const a = -Math.PI / 2 + (topic * 2 * Math.PI) / topics;
    return { x: single.x + Math.cos(a) * 22, y: single.y + Math.sin(a) * 22 };
  };
  const ring = (topic: number): Point => {
    const a = -Math.PI / 2 + (topic * 2 * Math.PI) / topics;
    return { x: you.x + Math.cos(a) * (youR + 9), y: you.y + Math.sin(a) * (youR + 9) };
  };
  const leave = (topic: number) => STRUCTURE_TIMING.travel + topic * STRUCTURE_TIMING.stagger;
  const orbAt = (topic: number): Point =>
    along(ring(topic), target(topic), easeInOut(span(t, leave(topic), leave(topic) + STRUCTURE_TIMING.move)));
  const appear = span(t, STRUCTURE_TIMING.appear[0], STRUCTURE_TIMING.appear[1]);

  // The district: other residents whose votes also go to the representative
  const neighbour = (i: number): Point => ({
    x: Math.max(14, you.x - 44) + (i % 6) * 9,
    y: H - 34 + Math.floor(i / 6) * 9 - 12,
  });
  const neighbourAt = (i: number): Point => {
    const start = STRUCTURE_TIMING.neighbours[0] + (i / NEIGHBOURS) * 600;
    const a = Math.PI / 2 + ((i + 0.5) * 2 * Math.PI) / NEIGHBOURS;
    const rest = { x: single.x + Math.cos(a) * 33, y: single.y + Math.sin(a) * 33 };
    return along(neighbour(i), rest, easeInOut(span(t, start, start + 900)));
  };

  const who: Record<Exclude<Structure, "direct" | "liquid">, { name: string; person: number }> = {
    representative: { name: "Your representative", person: typical.representative },
    proxy: { name: "Your proxy", person: typical.proxy },
  };
  const rows = Array.from({ length: topics }, (_, topic) => ({
    topic: topicLabel(city.topics[topic]),
    decides:
      kind === "direct"
        ? "Kept"
        : kind === "liquid"
          ? typical.delegates[topic] < 0
            ? "Kept"
            : resident(typical.delegates[topic])
          : resident(who[kind].person),
  }));

  return (
    <StoryFigure
      title={`${ARRANGEMENT_LABEL[kind as Arrangement]}: who decides ${resident(typical.voter)}'s eight topics`}
      subtitle={CAPTION[kind]}
      source={`${SOURCE}; fidelity and overhead: eval/benchmarks/delegation_everyone_votes_v1, mean over 200 cities (exploratory)`}
      table={{
        caption: `Who ${resident(typical.voter)} hands each topic to under ${ARRANGEMENT_LABEL[kind as Arrangement].toLowerCase()}`,
        columns: [
          { key: "topic", label: "Topic" },
          { key: "decides", label: "Handed to" },
        ],
        rows,
      }}
    >
      <div ref={player.ref}>
        <div ref={measure}>
          {width > 0 ? (
            <svg width={W} height={H} role="img" aria-label={`${ARRANGEMENT_LABEL[kind as Arrangement]}: ${CAPTION[kind]}`} className="block font-sans">
              <OrbDefs id={glow} />
              {kind === "representative"
                ? Array.from({ length: NEIGHBOURS }, (_, i) => {
                    const p = neighbour(i);
                    return <circle key={i} cx={p.x} cy={p.y} r={2.6} style={{ fill: INK.muted }} />;
                  })
                : null}
              {kind === "liquid"
                ? Array.from({ length: topics }, (_, topic) => {
                    if (typical.delegates[topic] < 0) return null;
                    const { from, to } = trimmed(you, slot(typical.delegates[topic]), youR, 9);
                    return (
                      <Edge
                        key={topic}
                        from={from}
                        to={to}
                        color={seriesColor(topic)}
                        progress={span(t, leave(topic), leave(topic) + STRUCTURE_TIMING.move)}
                        width={1.3}
                      />
                    );
                  })
                : null}
              {kind === "representative" || kind === "proxy" ? (
                <Edge
                  {...trimmed(you, single, youR, 13)}
                  color={INK.secondary}
                  progress={span(t, leave(0), leave(0) + STRUCTURE_TIMING.move)}
                />
              ) : null}
              {kind === "representative" || kind === "proxy" ? (
                <g>
                  <Person {...single} r={13} color={INK.secondary} />
                  <text x={single.x} y={single.y - (kind === "representative" ? 46 : 32)} textAnchor="middle" fontSize={11} fontWeight={600} style={{ fill: INK.primary }}>
                    {who[kind].name}
                  </text>
                  <text x={single.x} y={single.y + (kind === "representative" ? 54 : 40)} textAnchor="middle" fontSize={11} style={{ fill: INK.secondary }}>
                    {resident(who[kind].person)}
                  </text>
                </g>
              ) : null}
              {kind === "liquid"
                ? people.map((person) => {
                    const held = typical.delegates.flatMap((d, k) => (d === person ? [k] : []));
                    const p = slot(person);
                    return (
                      <g key={person}>
                        <Person {...p} r={8} color={held.length === 1 ? seriesColor(held[0]) : undefined} label={String(person)} labelAt="right" />
                        {held.length > 1 ? <Segments at={p} r={8} colors={held.map(seriesColor)} /> : null}
                      </g>
                    );
                  })
                : null}
              {kind === "direct" ? (
                <text x={you.x + 46} y={you.y + 34} fontSize={11} style={{ fill: INK.secondary }}>
                  decided by you
                </text>
              ) : null}
              <Person {...you} r={youR} label={`You: ${resident(typical.voter)}`} labelAt="above" emphasis />
              {kind === "representative"
                ? Array.from({ length: NEIGHBOURS }, (_, i) => {
                    const p = neighbourAt(i);
                    const start = STRUCTURE_TIMING.neighbours[0] + (i / NEIGHBOURS) * 600;
                    return t >= start ? <circle key={i} cx={p.x} cy={p.y} r={2.4} style={{ fill: INK.secondary }} opacity={0.75} /> : null;
                  })
                : null}
              {Array.from({ length: topics }, (_, topic) => {
                const p = orbAt(topic);
                return <Orb key={topic} x={p.x} y={p.y} r={4.5} color={seriesColor(topic)} glowId={glow} opacity={appear} />;
              })}
            </svg>
          ) : (
            <div style={{ height: H }} />
          )}
        </div>
        <ShareBars fidelity={shares.fidelity} overhead={shares.overhead} />
        <ReplayButton player={player} className="mt-3" />
      </div>
    </StoryFigure>
  );
}

/** Fidelity, and overhead drawn like a health bar: the work it asks of you. */
function ShareBars({ fidelity, overhead }: { fidelity: number; overhead: number }) {
  return (
    <dl className="mt-3 grid gap-2 font-sans text-xs sm:grid-cols-2">
      {[
        { label: "Fidelity: your ballot matches you", value: fidelity, color: seriesColor(0) },
        { label: "Overhead: questions you decide yourself", value: overhead, color: INK.secondary },
      ].map((bar) => (
        <div key={bar.label}>
          <dt className="flex justify-between text-story-ink-2">
            <span>{bar.label}</span>
            <span className="font-medium text-story-ink tabular-nums">{pct(bar.value)}</span>
          </dt>
          <dd className="mt-1 h-2 overflow-hidden rounded-full bg-story-rule">
            <span className="block h-full rounded-full" style={{ width: `${bar.value * 100}%`, background: bar.color }} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
