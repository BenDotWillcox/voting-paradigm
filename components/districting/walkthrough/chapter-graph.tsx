"use client";

import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";
import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";
import type { ExplainerBlock, ExplainerCore } from "@/lib/districting-explainer";
import { DD_PALETTE, MAP_COLORS } from "@/lib/districts-palette";
import { ChapterConsole, type ChapterStep } from "./chapter-console";
import { ExplainerStage, StageLayer, type StageBounds } from "./explainer-stage";
import { BlockShapes, GraphEdges, GraphNodes, MICHIGAN_COUNTIES, Silhouette, WALKTHROUGH_COLORS, boundsOf } from "./layers";
import { unitsPerPixel } from "./stage-layers";

const number = (value: number) => value.toLocaleString();

function Metrics({ rows }: { rows: [string, string][] }) {
  return <dl className="dd-card-metrics">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

const RINGS = 7;

/**
 * The graph growing out of the blocks: each block's point appears, then the
 * links between neighbors, in rings spreading out from the featured block.
 * Before the first play everything waits hidden; reduced motion shows it at once.
 */
function GraphBuild({ blocks, edges, projection, origin, playing }: {
  blocks: ExplainerBlock[]; edges: readonly (readonly [number, number])[]; projection: BlockMapProjection; origin: [number, number]; playing: boolean;
}) {
  const rings = React.useMemo(() => {
    const at = new Map(blocks.map((block) => [block.i, projection.projectPoint(block.point)]));
    const [ox, oy] = projection.projectPoint(origin);
    const far = Math.max(...[...at.values()].map(([x, y]) => Math.hypot(x - ox, y - oy)), 1e-9);
    const ring = (x: number, y: number) => Math.min(RINGS - 1, Math.floor((Math.hypot(x - ox, y - oy) / far) * RINGS));
    const nodes = Array<string>(RINGS).fill(""), links = Array<string>(RINGS).fill("");
    for (const [x, y] of at.values()) nodes[ring(x, y)] += `M${x.toFixed(4)} ${y.toFixed(4)}l0 0`;
    for (const [a, b] of edges) {
      const p = at.get(a), q = at.get(b);
      if (p && q) links[ring((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)] += `M${p[0].toFixed(4)} ${p[1].toFixed(4)}L${q[0].toFixed(4)} ${q[1].toFixed(4)}`;
    }
    return { nodes, links };
  }, [blocks, edges, projection, origin]);
  return <g className={playing ? "dd-graph-build" : "dd-graph-hold"} fill="none" strokeLinecap="round">
    {rings.links.map((d, index) => <path key={`link-${index}`} d={d} className="dd-grow" style={{ animationDelay: `${900 + index * 170}ms` }}
      stroke={WALKTHROUGH_COLORS.edge} strokeOpacity={0.7} strokeWidth={0.8} vectorEffect="non-scaling-stroke" />)}
    {rings.nodes.map((d, index) => <path key={`node-${index}`} d={d} className="dd-grow" style={{ animationDelay: `${400 + index * 170}ms` }}
      stroke={WALKTHROUGH_COLORS.edge} strokeWidth={3} vectorEffect="non-scaling-stroke" />)}
  </g>;
}

export function GraphChapter({ data, projection, overview, coast }: {
  data: ExplainerCore; projection: BlockMapProjection; overview: BlockMapCollection; coast: BlockMapCollection | null;
}) {
  const [step, setStep] = React.useState(0);
  const reduced = useReducedMotion();
  // Each visit to step 1 replays the graph growing out of the blocks.
  const [build, setBuild] = React.useState(0);
  const onStep = (next: number) => { if (next === 0 && step !== 0) setBuild((run) => run + 1); setStep(next); };
  // Once it has played, the build repeats while step 1 is open: about 2.6 s to grow, then a hold.
  React.useEffect(() => {
    if (step !== 0 || reduced || build === 0) return;
    const timer = window.setTimeout(() => setBuild((run) => run + 1), 5600);
    return () => window.clearTimeout(timer);
  }, [step, reduced, build]);
  const { stats, windows: { windows: { detroit, straits }, multipart } } = data;
  const featured = detroit.blocks.find((block) => block.geoid === detroit.featured)!;

  const corner = React.useMemo(() => {
    const ids = new Set(detroit.corner.blocks);
    const blocks = detroit.blocks.filter((block) => ids.has(block.geoid));
    const index = new Set(blocks.map((block) => block.i));
    const pair = detroit.corner.cornerPair.map((geoid) => blocks.find((block) => block.geoid === geoid)!);
    const bounds = blocks.map((block) => boundsOf(block.geometry));
    return {
      blocks, pair, pairSet: new Set(detroit.corner.cornerPair),
      edges: detroit.edges.filter(([a, b]) => index.has(a) && index.has(b)),
      bounds: [Math.min(...bounds.map((b) => b[0])), Math.min(...bounds.map((b) => b[1])), Math.max(...bounds.map((b) => b[2])), Math.max(...bounds.map((b) => b[3]))] as const,
    };
  }, [detroit]);

  const chain = React.useMemo(() => {
    const byId = new Map(straits.blocks.map((block) => [block.geoid, block]));
    const blocks = straits.path.map((geoid) => byId.get(geoid)!);
    // The shortest line through the chain, crossing each shared boundary once.
    const route = straits.route.map((point) => projection.projectPoint(point));
    const lons = straits.route.map(([lon]) => lon), lats = straits.route.map(([, lat]) => lat);
    return { blocks, water: blocks.filter((block) => block.landM2 === 0).length,
      bounds: [Math.min(...lons) - 0.085, Math.min(...lats) - 0.04, Math.max(...lons) + 0.085, Math.max(...lats) + 0.04] as const,
      d: route.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(5)} ${y.toFixed(5)}`).join(""),
      dots: route.map(([x, y]) => `M${x.toFixed(5)} ${y.toFixed(5)}l0 0`).join(""),
      // Shore blocks can be tiny (the Upper Peninsula one is about 80 m across), so each gets a marker.
      shores: blocks.map((block, order) => ({ order, block })).filter(({ block }) => block.landM2 > 0)
        .map(({ order, block }) => {
          const [x, y] = projection.projectPoint(block.point);
          // Chains run from the Upper Peninsula, so the first shore block is the north one.
          return { order, x, y, d: `M${x.toFixed(5)} ${y.toFixed(5)}l0 0`, label: order === 0 ? "Upper Peninsula land" : "Lower Peninsula land" };
        }) };
  }, [straits, projection]);
  // The chain lights one block at a time, then the line through it, then repeats.
  const [tick, setTick] = React.useState(0);
  const cycle = chain.blocks.length + 4;
  React.useEffect(() => {
    if (step !== 2 || reduced) return;
    setTick(0);
    const timer = window.setInterval(() => setTick((value) => (value + 1) % cycle), 700);
    return () => window.clearInterval(timer);
  }, [step, reduced, cycle]);
  const lit = reduced ? chain.blocks.length : Math.min(tick + 1, chain.blocks.length);
  const litSet = React.useMemo(() => new Set(straits.path.slice(0, lit)), [straits.path, lit]);
  const lineOn = reduced || tick >= chain.blocks.length;
  // Labels keep a fixed screen size at the Straits view.
  const labelUnit = React.useMemo(() => unitsPerPixel(chain.bounds, projection), [chain.bounds, projection]);
  const multipartSet = React.useMemo(() => new Set([multipart.geoid]), [multipart.geoid]);
  const [cornerX, cornerY] = projection.projectPoint(detroit.corner.point);

  const steps: (ChapterStep & { bounds: StageBounds; padding?: number })[] = [
    { title: "Neighbors share an edge", bounds: boundsOf(featured.geometry), padding: 3.2,
      body: <p>Districts have to be connected, so the first job is recording which blocks touch. Each line joins the points of two neighboring blocks. In this slice of Detroit, {number(detroit.blocks.length)} blocks have {number(detroit.edges.length)} neighbor links.</p> },
    { title: "Corners don't count", bounds: corner.bounds, padding: 0.18,
      body: <><p>The two highlighted blocks meet at a single point, so they are not neighbors. The test is exact: their interiors may not overlap, and their boundaries must share a line of positive length.</p><p className="dd-meta mt-2">DE-9IM pattern <code className="dd-code">{stats.graph.de9im_pattern}</code>. Statewide, {number(stats.graph.excluded_corner_pair_count)} pairs that touched only at a point were rejected.</p></> },
    { title: "Water joins the peninsulas", bounds: chain.bounds, padding: 0,
      body: <><p>The Upper and Lower Peninsulas never touch on land. They connect because open water is divided into blocks too, and no single water block touches both shores: the straits are split into water blocks along county lines.</p><p className="mt-2">The fewest blocks that connect the peninsulas are {chain.blocks.length}: a shore block on each side and {chain.water} water blocks between, west of the Mackinac Bridge. No connection is invented.</p><p className="dd-meta mt-2">{straits.chainCount} chains tie at {chain.blocks.length} blocks; shown is the shortest one whose shore blocks read clearly as mainland.</p></> },
    { title: "Some blocks come in pieces", bounds: boundsOf(multipart.geometry), padding: 0.3,
      body: <p>{number(stats.multipartBlocks)} Michigan blocks are made of separate polygons, like this {MICHIGAN_COUNTIES[multipart.geoid.slice(2, 5)]} County block: {multipart.parts} separate pieces of land, no residents. Pieces are not assumed connected just because they share an ID; the final maps are validated polygon by polygon.</p> },
    { title: "One connected graph", bounds: null,
      body: <p>Together, Michigan is a single connected graph: {number(stats.blocks)} blocks and {number(stats.graph.edge_count)} neighbor links, with no block left isolated. For every district, &ldquo;contiguous&rdquo; means connected in this graph.</p> },
  ];
  const current = steps[step];

  const card = step === 0 ? <Metrics rows={[["Blocks in view", number(detroit.blocks.length)], ["Neighbor links", number(detroit.edges.length)]]} />
    : step === 1 ? <Metrics rows={[["Shared edges", String(corner.edges.length)], ["Corner contact", "Rejected"]]} />
      : step === 2 ? <Metrics rows={[["Chain length", `${chain.blocks.length} blocks`], ["Water blocks", String(chain.water)], ["Touch both shores", String(straits.waterTouchingBothShores)], ["Invented links", "0"]]} />
        : step === 3 ? <Metrics rows={[["Pieces", String(multipart.parts)], ["Residents", number(multipart.population)], ["Multipart blocks", number(stats.multipartBlocks)]]} />
          : <Metrics rows={[["Blocks", number(stats.blocks)], ["Neighbor links", number(stats.graph.edge_count)], ["Connected parts", String(stats.graph.component_count)], ["Isolated blocks", String(stats.graph.isolated_node_count)]]} />;

  return (
    <ChapterConsole number={2} title="The block graph" steps={steps} step={step} onStep={onStep}
      onEnter={() => { if (step === 0) setBuild((run) => run + 1); }}>
      <ExplainerStage projection={projection} bounds={current.bounds} padding={current.padding} points={data.points} showPoints={step === 4} card={card}
        label={`Michigan block graph, step ${step + 1}: ${current.title}`}>
        <Silhouette overview={overview} coast={coast} projection={projection} />
        <StageLayer visible={step <= 1}>
          <g key={`blocks-${build}`} className={step === 0 && build > 0 ? "dd-recede" : undefined}>
            <BlockShapes blocks={detroit.blocks} projection={projection} highlight={step === 1 ? corner.pairSet : undefined} />
          </g>
          <StageLayer visible={step === 0}>
            <GraphBuild key={build} blocks={detroit.blocks} edges={detroit.edges} projection={projection} origin={featured.point} playing={build > 0 || reduced} />
          </StageLayer>
          <StageLayer visible={step === 1}>
            <GraphEdges blocks={corner.blocks} edges={corner.edges} projection={projection} width={2.4} opacity={1} />
            <GraphEdges blocks={corner.pair} edges={[[corner.pair[0].i, corner.pair[1].i]]} projection={projection} width={2} opacity={0.9} dash="2 6" />
            <GraphNodes blocks={corner.blocks} projection={projection} size={9} />
            <path d={`M${cornerX} ${cornerY}l0 0`} stroke={MAP_COLORS.selection} strokeWidth={13} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            <path d={`M${cornerX} ${cornerY}l0 0`} stroke={MAP_COLORS.casing} strokeWidth={7} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          </StageLayer>
        </StageLayer>
        <StageLayer visible={step === 2}>
          <BlockShapes blocks={straits.blocks} projection={projection} highlight={litSet} landHighlight={WALKTHROUGH_COLORS.highlightLand} strong />
          {chain.shores.filter((shore) => shore.order < lit).map((shore) => <g key={shore.order} strokeLinecap="round">
            <path d={shore.d} stroke={MAP_COLORS.casing} strokeWidth={16} vectorEffect="non-scaling-stroke" />
            <path d={shore.d} stroke={WALKTHROUGH_COLORS.edge} strokeWidth={12} vectorEffect="non-scaling-stroke" />
            <path d={shore.d} stroke={DD_PALETTE.peridot} strokeWidth={7} vectorEffect="non-scaling-stroke" />
            <text x={shore.x + 14 * labelUnit} y={shore.y + 4.5 * labelUnit} fontSize={13 * labelUnit} fontWeight={600} fontFamily="var(--dd-mono)"
              fill={MAP_COLORS.selection} stroke={MAP_COLORS.selectionCasing} strokeWidth={3.5 * labelUnit} strokeLinejoin="round" paintOrder="stroke">{shore.label}</text>
          </g>)}
          <StageLayer visible={lineOn}>
            <path d={chain.d} fill="none" stroke={MAP_COLORS.casing} strokeWidth={5.5} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            <path d={chain.d} fill="none" stroke={WALKTHROUGH_COLORS.edge} strokeWidth={2.4} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            <path d={chain.dots} stroke={WALKTHROUGH_COLORS.edge} strokeWidth={8} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          </StageLayer>
        </StageLayer>
        <StageLayer visible={step === 3}>
          <BlockShapes blocks={multipart.neighbors} projection={projection} />
          <BlockShapes blocks={[multipart]} projection={projection} highlight={multipartSet} landHighlight={WALKTHROUGH_COLORS.highlightLand} strong />
        </StageLayer>
      </ExplainerStage>
    </ChapterConsole>
  );
}
