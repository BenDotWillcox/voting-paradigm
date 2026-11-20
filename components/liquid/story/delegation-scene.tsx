"use client";

import * as React from "react";

import { useElementWidth } from "@/components/story/chart";
import { StoryFigure } from "@/components/story/story-figure";
import { observeThemeChanges, resolveCssColor } from "@/lib/canvas-color";
import { resident } from "@/lib/liquid/format";
import { topicLabel } from "@/lib/liquid/story-types";
import { INK, seriesColor } from "@/lib/story/palette";

import {
  Ballot,
  Edge,
  Orb,
  OrbDefs,
  Person,
  ReplayButton,
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
 * Part 2 of the story, "the basic version", as one scene in three stages
 * (prompts/demo-5-walkthrough.md, items 8, 9 and 13, described by Ben):
 * a ballot becomes an orb and is sorted by topic colour to the resident's
 * delegates; one delegate passes it on; and the whole city's votes flow to
 * whoever decides them. Drawn from the illustrative city with everyone
 * voting (the R1 setting): every resident, delegation and count is the
 * frozen code's own. Illustrations: they make no claim.
 */

const SOURCE = "Primary city 1 with everyone voting (the R1 setting), recomputed with the frozen code";

/** Each topic's colour: the validated categorical slots, in topic order. */
function topicColor(topic: number): string {
  return seriesColor(topic);
}

// ---------------------------------------------------------------------------
// Stage 1: a ballot arrives
// ---------------------------------------------------------------------------

const ARRIVE = {
  cardIn: [0, 500],
  shrink: [900, 1500],
  toResident: [1500, 2300],
  toDelegate: [2300, 3100],
  crowdStart: 3200,
  crowdGap: 110,
  crowdIn: 650,
  crowdOut: 750,
  settle: 250,
} as const;

/** Orbs after the first, two per topic, topics interleaved. */
const PER_TOPIC = 2;

export function BallotArrivesFigure() {
  const { city } = useStoryData();
  const { typical } = city.everyone;
  const topics = city.topics.length;
  const first = typical.chain.topic;
  const crowd = React.useMemo(
    () => Array.from({ length: PER_TOPIC * topics }, (_, i) => ({ topic: i % topics, index: i })),
    [topics]
  );
  const duration =
    ARRIVE.crowdStart + crowd.length * ARRIVE.crowdGap + ARRIVE.crowdIn + ARRIVE.crowdOut + ARRIVE.settle;
  const player = useScenePlayer(duration);
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const glow = `orb-${React.useId().replace(/:/g, "")}`;
  const t = player.t;

  const H = 300;
  const W = Math.max(width, 280);
  const card: Point = { x: Math.max(36, W * 0.09), y: H / 2 };
  const you: Point = { x: W * 0.4, y: H / 2 };
  const delegateX = W - 92;
  const kept = (topic: number) => typical.delegates[topic] < 0;
  // One node per delegate, in the order of the first topic each holds: a
  // delegate trusted with two topics is one person with two edges
  const people = [...new Set(typical.delegates.filter((d) => d >= 0))];
  const slot = (person: number): Point => ({
    x: delegateX,
    y: people.length > 1 ? 22 + (people.indexOf(person) * (H - 44)) / (people.length - 1) : H / 2,
  });
  const at = (topic: number): Point => slot(typical.delegates[topic]);
  const topicsOf = (person: number) => typical.delegates.flatMap((d, k) => (d === person ? [k] : []));
  const youR = 15;
  const delegateR = 9;
  /** A topic's edge; edges to one delegate sit side by side, a few pixels apart. */
  const edge = (topic: number) => {
    const { from, to } = trimmed(you, at(topic), youR, delegateR);
    const siblings = topicsOf(typical.delegates[topic]);
    const shift = (siblings.indexOf(topic) - (siblings.length - 1) / 2) * 3.5;
    const length = Math.hypot(to.x - from.x, to.y - from.y) || 1;
    const nx = -(to.y - from.y) / length;
    const ny = (to.x - from.x) / length;
    return {
      from: { x: from.x + nx * shift, y: from.y + ny * shift },
      to: { x: to.x + nx * shift, y: to.y + ny * shift },
    };
  };

  // When each topic's first orb leaves the resident: its edge draws with it
  const departs = (i: number) => ARRIVE.crowdStart + i * ARRIVE.crowdGap + ARRIVE.crowdIn;
  const firstDepart = (topic: number) =>
    topic === first ? ARRIVE.toDelegate[0] : departs(crowd.findIndex((o) => o.topic === topic));

  /** An orb's position: from the left to the resident, then along its topic's edge. */
  function orbAt(topic: number, enter: number, from: Point): { p: Point; a: number } | null {
    const arrive = enter + ARRIVE.crowdIn;
    const leave = arrive + ARRIVE.crowdOut;
    if (t < enter) return null;
    if (t < arrive) return { p: along(from, you, easeInOut(span(t, enter, arrive))), a: span(t, enter, enter + 150) };
    if (kept(topic)) return { p: you, a: 1 - span(t, arrive, arrive + ARRIVE.settle) };
    const { from: a, to: b } = edge(topic);
    if (t < leave) return { p: along(a, b, easeInOut(span(t, arrive, leave))), a: 1 };
    return { p: b, a: 1 - span(t, leave, leave + ARRIVE.settle) };
  }

  // The first orb: the ballot shrinks into it
  const shrink = easeInOut(span(t, ARRIVE.shrink[0], ARRIVE.shrink[1]));
  const cardIn = easeOut(span(t, ARRIVE.cardIn[0], ARRIVE.cardIn[1]));
  let firstOrb: { p: Point; a: number; r: number } | null = null;
  if (t >= ARRIVE.shrink[0]) {
    if (t < ARRIVE.toResident[0]) firstOrb = { p: card, a: 1, r: 7 * shrink };
    else if (t < ARRIVE.toDelegate[0]) {
      firstOrb = { p: along(card, you, easeInOut(span(t, ARRIVE.toResident[0], ARRIVE.toResident[1]))), a: 1, r: 7 };
    } else if (kept(first)) firstOrb = { p: you, a: 1 - span(t, ARRIVE.toDelegate[0], ARRIVE.toDelegate[0] + 250), r: 7 };
    else {
      const { from: a, to: b } = edge(first);
      const x = span(t, ARRIVE.toDelegate[0], ARRIVE.toDelegate[1]);
      firstOrb = { p: along(a, b, easeInOut(x)), a: 1 - span(t, ARRIVE.toDelegate[1], ARRIVE.toDelegate[1] + 250), r: 7 };
    }
  }

  // A delegate rings in its colour once a vote has reached it
  const reached = (topic: number) => !kept(topic) && t >= firstDepart(topic) + ARRIVE.crowdOut;
  const rows = Array.from({ length: topics }, (_, topic) => ({
    topic,
    label: topicLabel(city.topics[topic]),
    delegate: typical.delegates[topic],
    decider: typical.resolvers[topic],
  }));

  return (
    <StoryFigure
      title="A ballot arrives"
      subtitle={`Each question on ${resident(typical.voter)}'s ballot becomes a vote in its topic's colour, and goes to their delegate for that topic.`}
      source={SOURCE}
      note="An illustration: it shows how votes are routed, and claims nothing."
      table={{
        caption: `${resident(typical.voter)}'s delegate in every topic, with everyone voting`,
        columns: [
          { key: "topic", label: "Topic" },
          { key: "delegate", label: "Handed to" },
          { key: "decider", label: "Decided in the end by" },
        ],
        rows: rows.map((r) => ({
          topic: r.label,
          delegate: r.delegate < 0 ? "Kept" : resident(r.delegate),
          decider: r.decider === typical.voter ? "Themself" : resident(r.decider),
        })),
      }}
    >
      <div ref={player.ref}>
        <div ref={measure}>
          {width > 0 ? (
            <svg width={W} height={H} role="img" aria-label={`A ballot becomes a vote and is sorted by topic to ${resident(typical.voter)}'s delegates`} className="block font-sans">
              <OrbDefs id={glow} />
              {rows.map((r) => {
                if (kept(r.topic)) return null;
                const { from, to } = edge(r.topic);
                const start = firstDepart(r.topic);
                return (
                  <React.Fragment key={r.topic}>
                    <Edge from={from} to={to} color={INK.grid} width={1} arrow={false} />
                    <Edge
                      from={from}
                      to={to}
                      color={topicColor(r.topic)}
                      progress={span(t, start, start + ARRIVE.crowdOut)}
                    />
                  </React.Fragment>
                );
              })}
              {people.map((person) => {
                const held = topicsOf(person);
                const p = slot(person);
                const reachedAll = held.every(reached);
                return (
                  <g key={person}>
                    <Person
                      {...p}
                      r={delegateR}
                      color={held.length === 1 ? topicColor(held[0]) : undefined}
                      ring={reachedAll ? (held.length === 1 ? topicColor(held[0]) : INK.secondary) : undefined}
                      label={resident(person)}
                      labelAt="right"
                    />
                    {held.length > 1 ? <Segments at={p} r={delegateR} colors={held.map(topicColor)} /> : null}
                  </g>
                );
              })}
              <Person {...you} r={youR} label={resident(typical.voter)} labelAt="left" emphasis />
              <Ballot x={card.x} y={card.y} scale={(1 - shrink) * lerp(0.6, 1, cardIn)} opacity={cardIn} accent={topicColor(first)} />
              {firstOrb ? <Orb x={firstOrb.p.x} y={firstOrb.p.y} r={firstOrb.r} color={topicColor(first)} glowId={glow} opacity={firstOrb.a} /> : null}
              {crowd.map((o) => {
                const enter = ARRIVE.crowdStart + o.index * ARRIVE.crowdGap;
                const from = { x: card.x, y: H / 2 + (((o.index * 37) % 120) - 60) };
                const s = orbAt(o.topic, enter, from);
                return s ? <Orb key={o.index} x={s.p.x} y={s.p.y} r={6} color={topicColor(o.topic)} glowId={glow} opacity={s.a} /> : null;
              })}
            </svg>
          ) : (
            <div style={{ height: H }} />
          )}
        </div>
        <ul className="mt-3 grid gap-x-6 gap-y-1 font-sans text-xs text-story-ink-2 sm:grid-cols-2">
          {rows.map((r) => (
            <li key={r.topic} className="flex items-center gap-2">
              <span aria-hidden="true" className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: topicColor(r.topic) }} />
              <span>
                {r.label}: {r.delegate < 0 ? "kept" : resident(r.delegate)}
              </span>
            </li>
          ))}
        </ul>
        <ReplayButton player={player} className="mt-3" />
      </div>
    </StoryFigure>
  );
}

/** A node trusted with several topics: one segment in each topic's colour. */
function Segments({ at, r, colors }: { at: Point; r: number; colors: string[] }) {
  const step = (2 * Math.PI) / colors.length;
  return (
    <g transform={`translate(${at.x},${at.y})`} pointerEvents="none">
      {colors.map((color, i) => {
        const a0 = -Math.PI / 2 + i * step;
        const a1 = a0 + step;
        const large = step > Math.PI ? 1 : 0;
        const d = `M0,0 L${r * Math.cos(a0)},${r * Math.sin(a0)} A${r},${r} 0 ${large} 1 ${r * Math.cos(a1)},${r * Math.sin(a1)} Z`;
        return <path key={i} d={d} style={{ fill: color }} />;
      })}
    </g>
  );
}

// ---------------------------------------------------------------------------
// Stage 2: votes travel on
// ---------------------------------------------------------------------------

const TRAVEL = { appear: [0, 300], firstHop: 400, hop: 900, move: 700, zoom: [500, 1700], tail: 600 } as const;

export function VotesTravelFigure() {
  const { city } = useStoryData();
  const { typical } = city.everyone;
  const { topic, path } = typical.chain;
  const color = topicColor(topic);
  const hops = path.length - 1;
  const duration = TRAVEL.firstHop + hops * TRAVEL.hop + TRAVEL.tail;
  const player = useScenePlayer(duration);
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const glow = `orb-${React.useId().replace(/:/g, "")}`;
  const t = player.t;

  const H = 210;
  const W = Math.max(width, 280);
  const margin = 46;
  const spacing = hops > 0 ? (W - 2 * margin) / hops : 0;
  const full = spacing > 92;
  const node = (i: number): Point => ({
    x: hops > 0 ? margin + i * spacing : W / 2,
    y: H / 2 + (i % 2 === 0 ? -26 : 26),
  });
  const r = 10;
  const hopStart = (i: number) => TRAVEL.firstHop + i * TRAVEL.hop;

  // The camera starts close on the first hand-over, then pulls back
  const z = easeInOut(span(t, TRAVEL.zoom[0], TRAVEL.zoom[1]));
  const focus = hops > 0 ? along(node(0), node(1), 0.5) : node(0);
  const scale = lerp(1.6, 1, z);
  const fx = lerp(focus.x, W / 2, z);
  const fy = lerp(focus.y, H / 2, z);

  let orb: Point = node(0);
  for (let i = 0; i < hops; i++) {
    if (t >= hopStart(i)) {
      const { from, to } = trimmed(node(i), node(i + 1), 0, 0);
      orb = along(from, to, easeInOut(span(t, hopStart(i), hopStart(i) + TRAVEL.move)));
    }
  }
  const decider = path[path.length - 1];
  const decided = t >= hopStart(hops - 1) + TRAVEL.move || hops === 0;
  const name = (person: number) => (full ? resident(person) : String(person));

  return (
    <StoryFigure
      title="Votes travel on"
      subtitle={`${resident(typical.voter)}'s vote on ${topicLabel(city.topics[topic]).toLowerCase()} passes through ${hops - 1} ${hops - 1 === 1 ? "delegate" : "delegates"} before ${resident(decider)} decides it.`}
      source={SOURCE}
      note={full ? "An illustration: it claims nothing." : "Numbers are residents. An illustration: it claims nothing."}
      table={{
        caption: `The path of ${resident(typical.voter)}'s vote on ${topicLabel(city.topics[topic]).toLowerCase()}`,
        columns: [
          { key: "step", label: "Step", numeric: true },
          { key: "who", label: "Resident" },
          { key: "does", label: "What they do with it" },
        ],
        rows: path.map((person, i) => ({
          step: i,
          who: resident(person),
          does: i === 0 ? "Hands it to their delegate" : i === hops ? "Decides it" : "Hands it on to their own delegate",
        })),
      }}
    >
      <div ref={player.ref}>
        <div ref={measure} className="overflow-hidden">
          {width > 0 ? (
            <svg width={W} height={H} role="img" aria-label={`A vote passing along ${path.length} residents until one decides it`} className="block font-sans">
              <OrbDefs id={glow} />
              <g transform={`translate(${W / 2},${H / 2}) scale(${scale}) translate(${-fx},${-fy})`}>
                {path.slice(0, -1).map((_, i) => {
                  const { from, to } = trimmed(node(i), node(i + 1), r, r);
                  return (
                    <React.Fragment key={i}>
                      <Edge from={from} to={to} color={INK.grid} width={1} arrow={false} />
                      <Edge from={from} to={to} color={color} progress={span(t, hopStart(i), hopStart(i) + TRAVEL.move)} />
                    </React.Fragment>
                  );
                })}
                {path.map((person, i) => {
                  const last = i === hops;
                  const reached = i === 0 ? t >= TRAVEL.appear[1] : t >= hopStart(i - 1) + TRAVEL.move;
                  return (
                    <Person
                      key={person}
                      {...node(i)}
                      r={last ? r + 3 : r}
                      color={last && decided ? color : undefined}
                      ring={reached ? color : undefined}
                      label={last && decided ? `${name(person)} decides` : name(person)}
                      labelAt={i % 2 === 0 ? "above" : "below"}
                      emphasis={i === 0 || (last && decided)}
                    />
                  );
                })}
                <Orb x={orb.x} y={orb.y} r={6} color={color} glowId={glow} opacity={span(t, TRAVEL.appear[0], TRAVEL.appear[1])} />
              </g>
            </svg>
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
// Stage 3: who ends up deciding
// ---------------------------------------------------------------------------

const DECIDE = { fade: 700, start: 700, hop: 420, tail: 700 } as const;

interface Tree {
  /** Position of every resident, normalized to the unit disc. */
  at: Point[];
  /** Each resident's path to whoever decides for them, as resident indices. */
  paths: number[][];
  deciders: number[];
  votes: Map<number, number>;
  depth: number;
}

/**
 * A radial tree per decider: deciders on an inner ring, each given a sector
 * as wide as the votes they end up holding, and everyone else on rings
 * outward by how many hand-overs they are from their decider.
 */
function radialTree(delegateOf: number[], resolver: number[]): Tree {
  const n = resolver.length;
  const deciders = resolver.map((r, v) => (r === v ? v : -1)).filter((v) => v >= 0);
  const children = new Map<number, number[]>();
  for (let v = 0; v < n; v++) {
    if (resolver[v] === v) continue;
    const parent = delegateOf[v];
    children.set(parent, [...(children.get(parent) ?? []), v]);
  }
  const votes = new Map<number, number>();
  for (const d of resolver) votes.set(d, (votes.get(d) ?? 0) + 1);
  const paths = Array.from({ length: n }, (_, v) => {
    const steps = [v];
    while (steps[steps.length - 1] !== resolver[v]) steps.push(delegateOf[steps[steps.length - 1]]);
    return steps;
  });
  const depth = Math.max(1, ...paths.map((p) => p.length - 1));
  const leaves = (v: number): number => {
    const kids = children.get(v) ?? [];
    return kids.length ? kids.reduce((sum, k) => sum + leaves(k), 0) : 1;
  };
  const order = [...deciders].sort((a, b) => (votes.get(b) ?? 0) - (votes.get(a) ?? 0) || a - b);
  const total = order.reduce((sum, d) => sum + leaves(d), 0);
  const angle = new Array<number>(n).fill(0);
  let cursor = -Math.PI / 2;
  const place = (v: number, start: number, width: number) => {
    angle[v] = start + width / 2;
    const kids = children.get(v) ?? [];
    let at = start;
    for (const k of kids) {
      const w = (width * leaves(k)) / leaves(v);
      place(k, at, w);
      at += w;
    }
  };
  for (const d of order) {
    const width = (2 * Math.PI * leaves(d)) / total;
    place(d, cursor, width);
    cursor += width;
  }
  const inner = 0.38;
  const at = Array.from({ length: n }, (_, v) => {
    const radius = inner + ((1 - inner) * (paths[v].length - 1)) / depth;
    return { x: Math.cos(angle[v]) * radius, y: Math.sin(angle[v]) * radius };
  });
  return { at, paths, deciders, votes, depth };
}

export function WhoDecidesFigure() {
  const { city } = useStoryData();
  const { graph, liquid_resolver: resolver } = city.everyone;
  const tree = React.useMemo(() => radialTree(graph.delegate_of, resolver), [graph.delegate_of, resolver]);
  const duration = DECIDE.start + tree.depth * DECIDE.hop + DECIDE.tail;
  const player = useScenePlayer(duration);
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const canvas = React.useRef<HTMLCanvasElement | null>(null);
  const [colors, setColors] = React.useState<Record<string, string> | null>(null);

  const ranked = [...tree.deciders].sort((a, b) => (tree.votes.get(b) ?? 0) - (tree.votes.get(a) ?? 0) || a - b);
  const largest = ranked[0];
  const most = tree.votes.get(largest) ?? 1;
  const n = resolver.length;
  const size = Math.min(Math.max(width, 280), 460);

  React.useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const resolve = () =>
      setColors({
        edge: resolveCssColor(node, INK.grid),
        node: resolveCssColor(node, INK.muted),
        orb: resolveCssColor(node, INK.secondary),
        decider: resolveCssColor(node, INK.primary),
        surface: resolveCssColor(node, INK.surface),
      });
    resolve();
    return observeThemeChanges(resolve);
  }, [width]);

  const t = player.t;
  React.useEffect(() => {
    const node = canvas.current;
    if (!node || !colors || width === 0) return;
    const dpr = window.devicePixelRatio || 1;
    node.width = Math.round(size * dpr);
    node.height = Math.round(size * dpr);
    const ctx = node.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);
    const half = size / 2;
    const reach = half - 16;
    const px = (p: Point) => ({ x: half + p.x * reach, y: half + p.y * reach });
    const fade = span(t, 0, DECIDE.fade);
    const deciders = new Set(tree.deciders);

    // The fuller graph: every delegation, faint
    ctx.globalAlpha = 0.55 * fade;
    ctx.strokeStyle = colors.edge;
    ctx.lineWidth = 0.7;
    ctx.beginPath();
    for (let v = 0; v < n; v++) {
      if (deciders.has(v)) continue;
      const a = px(tree.at[v]);
      const b = px(tree.at[tree.paths[v][1]]);
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
    }
    ctx.stroke();
    ctx.globalAlpha = fade;
    ctx.fillStyle = colors.node;
    for (let v = 0; v < n; v++) {
      if (deciders.has(v)) continue;
      const a = px(tree.at[v]);
      ctx.beginPath();
      ctx.arc(a.x, a.y, 1.8, 0, Math.PI * 2);
      ctx.fill();
    }

    // The votes, uncoloured now, flowing hop by hop to whoever decides them
    const arrived = new Map<number, number>();
    ctx.fillStyle = colors.orb;
    for (let v = 0; v < n; v++) {
      const path = tree.paths[v];
      const hops = path.length - 1;
      if (hops === 0) {
        arrived.set(v, (arrived.get(v) ?? 0) + 1);
        continue;
      }
      const elapsed = (t - DECIDE.start) / DECIDE.hop;
      if (elapsed < 0) continue;
      if (elapsed >= hops) {
        arrived.set(path[hops], (arrived.get(path[hops]) ?? 0) + 1);
        continue;
      }
      const step = Math.floor(elapsed);
      const p = along(px(tree.at[path[step]]), px(tree.at[path[step + 1]]), easeInOut(elapsed - step));
      ctx.globalAlpha = 0.25;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 0.95;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 2.2, 0, Math.PI * 2);
      ctx.fill();
    }

    // Deciders grow with the votes they hold
    const grow = (reach * 0.05) / Math.sqrt(most);
    const radiusOf = (d: number) => 2 + grow * Math.sqrt(arrived.get(d) ?? 1);
    ctx.globalAlpha = 1;
    for (const d of tree.deciders) {
      const a = px(tree.at[d]);
      ctx.beginPath();
      ctx.arc(a.x, a.y, radiusOf(d), 0, Math.PI * 2);
      ctx.fillStyle = colors.decider;
      ctx.fill();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = colors.surface;
      ctx.stroke();
    }

    // Once every vote has arrived, name the largest decider at the centre
    const settled = span(t, duration - DECIDE.tail, duration);
    if (settled > 0) {
      const a = px(tree.at[largest]);
      ctx.globalAlpha = settled;
      ctx.strokeStyle = colors.decider;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(half, half);
      ctx.stroke();
      ctx.fillStyle = colors.decider;
      ctx.textAlign = "center";
      ctx.font = `600 12px ${getComputedStyle(node).fontFamily}`;
      ctx.fillText(resident(largest), half, half - 2);
      ctx.font = `12px ${getComputedStyle(node).fontFamily}`;
      ctx.fillText(`${most} votes`, half, half + 13);
      ctx.globalAlpha = 1;
    }
  }, [t, colors, width, size, tree, n, most, largest, duration]);

  return (
    <StoryFigure
      title="Who ends up deciding"
      subtitle={`Every resident's vote on one question flows to whoever decides it. ${tree.deciders.length} residents decide it for all ${n}; the largest holds ${most} votes, and a district representative would hold ${city.design.residents_per_district}.`}
      source={SOURCE}
      note="Deciders sit on the inner ring, sized by the votes they hold; everyone else sits outward by how many hand-overs they are from their decider. An illustration: it claims nothing."
      table={{
        caption: "The ten residents holding the most votes on this question",
        columns: [
          { key: "who", label: "Resident" },
          { key: "votes", label: "Votes held", numeric: true },
        ],
        rows: ranked.slice(0, 10).map((d) => ({ who: resident(d), votes: tree.votes.get(d) ?? 0 })),
      }}
    >
      <div ref={player.ref}>
        <div ref={measure} className="flex justify-center">
          <canvas
            ref={canvas}
            role="img"
            aria-label={`${tree.deciders.length} residents decide this question for all ${n}; the largest holds ${most} votes.`}
            style={{ width: size, height: size }}
          />
        </div>
        <ReplayButton player={player} className="mt-3" />
      </div>
    </StoryFigure>
  );
}
