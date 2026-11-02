"use client";

import * as React from "react";
import { Pause, Play } from "lucide-react";

import { useReducedMotion } from "@/components/story/chart";
import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";
import type { ExplainerData } from "@/lib/districting-explainer";
import { ChapterConsole, type ChapterStep } from "./chapter-console";
import { ExplainerStage, StageLayer } from "./explainer-stage";
import { Silhouette } from "./layers";
import { oneIn, sci } from "./math";
import { PopulationBars, PowerCells, SeedMarks, StateClip } from "./power-layers";

const number = (value: number) => value.toLocaleString();
/** Light to dark: each shade holds a fifth of the chance of the draw. */
const HEAT = ["#cfd8dc", "#c9d08f", "#adb948", "#86922c", "#4f560c"] as const;
const DRAW_MS = 1700;

function Metrics({ rows }: { rows: [string, React.ReactNode][] }) {
  return <dl className="dd-card-metrics">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

function HeatLegend() {
  return <>
    <div className="dd-heat" aria-hidden="true">{HEAT.map((color) => <span key={color} style={{ background: color }} />)}</div>
    <p className="dd-meta flex justify-between font-mono"><span>less likely</span><span>more likely</span></p>
    <p className="dd-meta">Each shade holds 20% of this draw&rsquo;s total chance.</p>
  </>;
}

/** Population-weighted k-means++, draw by draw: where the 13 districts start. */
export function SeedsChapter({ data, projection, overview, coast }: {
  data: ExplainerData; projection: BlockMapProjection; overview: BlockMapCollection; coast: BlockMapCollection | null;
}) {
  const { stats, points, power } = data;
  const { seeds, draws } = power;
  const reduced = useReducedMotion();
  const [step, setStep] = React.useState(0);
  // Seeds 2–13: `next` is the 0-based index of the seed being drawn.
  const [next, setNext] = React.useState(1);
  const [playing, setPlaying] = React.useState(false);
  const clipId = `dd-clip-${React.useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const voronoi = power.frames[0];
  const county = (block: number) => stats.countyNames[seeds.find((seed) => seed.block === block)?.geoid.slice(2, 5) ?? ""] ?? "Michigan";

  React.useEffect(() => {
    if (!playing) return;
    if (next >= seeds.length - 1) { setPlaying(false); return; }
    const timer = window.setTimeout(() => setNext(next + 1), DRAW_MS);
    return () => window.clearTimeout(timer);
  }, [playing, next, seeds.length]);

  const onStep = (target: number) => {
    setStep(target);
    if (target === 2 && step !== 2) { setNext(1); setPlaying(!reduced); }
    else if (target !== 2) setPlaying(false);
  };
  const toggle = () => {
    if (!playing && next >= seeds.length - 1) setNext(1);
    setPlaying(!playing);
  };

  // The chance map behind one draw: residents × squared distance to the nearest
  // seed so far, ranked and cut into five shades of equal total chance. The
  // shades use the published (rounded) points; the card's numbers are exact.
  const heat = React.useMemo(() => {
    const cache = new Map<number, Uint8Array>();
    const { metersPerDegreeLon: mx, metersPerDegreeLat: my } = power.plane;
    return (index: number) => {
      const hit = cache.get(index);
      if (hit) return hit;
      const nearest = new Float64Array(points.count).fill(Infinity);
      for (const seed of seeds.slice(0, index)) {
        for (let i = 0; i < points.count; i++) {
          const dx = (points.lon[i] - seed.point[0]) * mx, dy = (points.lat[i] - seed.point[1]) * my;
          nearest[i] = Math.min(nearest[i], dx * dx + dy * dy);
        }
      }
      const weight = new Float64Array(points.count);
      let total = 0;
      for (let i = 0; i < points.count; i++) { weight[i] = points.population[i] * nearest[i]; total += weight[i]; }
      const order = Array.from({ length: points.count }, (_, i) => i).filter((i) => weight[i] > 0).sort((a, b) => weight[a] - weight[b]);
      const bins = new Uint8Array(points.count);
      let running = 0;
      for (const i of order) { running += weight[i]; bins[i] = Math.min(HEAT.length, 1 + Math.floor((running / total) * HEAT.length)); }
      cache.set(index, bins);
      return bins;
    };
  }, [points, power.plane, seeds]);

  const first = draws[0], draw = draws[next];
  const likeliest = draws.reduce((best, item) => item.rank < best.rank ? item : best);
  const unlikeliest = draws.reduce((worst, item) => item.rank > worst.rank ? item : worst);
  const largest = voronoi.populations.indexOf(Math.max(...voronoi.populations));
  const smallest = voronoi.populations.indexOf(Math.min(...voronoi.populations));

  const steps: ChapterStep[] = [
    { title: "Start where people live",
      body: <><p>The solver works with points, not shapes: each of Michigan&rsquo;s {number(stats.blocks)} blocks becomes one point x<sub>i</sub>, its Census internal point, weighted by its residents p<sub>i</sub>.</p>
        <p className="dd-formula">Σ<sub>i</sub> p<sub>i</sub> = {number(stats.residents)}</p></> },
    { title: "The first seed",
      body: <><p>A district starts from a seed. The first is drawn with chances proportional to population:</p>
        <p className="dd-formula">P(i) = p<sub>i</sub> / Σ<sub>j</sub> p<sub>j</sub></p>
        <p>Line up every block&rsquo;s chance end to end from 0 to 1. A seeded random number u picks the block whose stretch it lands in: u = {first.u.toFixed(4)} landed on a {first.residents}-resident block in {county(first.block)}.</p></> },
    { title: "Then spread out",
      body: <><p>Each later seed is drawn with chances proportional to residents times the squared distance D<sub>i</sub> to the nearest seed already placed:</p>
        <p className="dd-formula">P(i) = p<sub>i</sub>·D<sub>i</sub>² / Σ<sub>j</sub> p<sub>j</sub>·D<sub>j</sub>²</p>
        <p>Squaring the distance makes far-off crowds much likelier than nearby ones, so the seeds spread out across where people live.</p>
        <div className="dd-player">
          <button type="button" className="dd-tool" onClick={toggle}>{playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}{playing ? "Pause" : "Play"}</button>
          <input type="range" className="dd-scrub" min={1} max={seeds.length - 1} value={next} aria-label="Seed" aria-valuetext={`Seed ${next + 1} of ${seeds.length}`}
            onChange={(event) => { setPlaying(false); setNext(Number(event.target.value)); }} />
        </div></> },
    { title: `${seeds.length} seeds`,
      body: <p>Repeating the draw places all {seeds.length} seeds. The random numbers come from a generator fixed by the run&rsquo;s seed, {power.seed}: the same seed draws the same u values, picks the same blocks, and so produces the same map for anyone who reruns it.</p> },
    { title: "Nearest seed wins",
      body: <><p>Suppose every block simply joined its nearest seed:</p>
        <p className="dd-formula">district(i) = argmin<sub>k</sub> |x<sub>i</sub> − c<sub>k</sub>|²</p>
        <p>The cells would be wildly unequal: {number(voronoi.populations[largest])} people around the {county(seeds[largest].block)} seed and {number(voronoi.populations[smallest])} around the {county(seeds[smallest].block)} seed, against a target of {number(Math.round(power.target))}. Distance alone cannot balance population.</p></> },
  ];

  const card = step === 0 ? <Metrics rows={[["Points", number(stats.blocks)], ["Residents", number(stats.residents)]]} />
    : step === 1 ? <Metrics rows={[["Residents", String(first.residents)], ["Chance", oneIn(first.chance)], ["Rank", `${number(first.rank)} of ${number(stats.blocks)}`], ["u", first.u.toFixed(4)]]} />
      : step === 2 ? <div className="grid gap-2">
        <Metrics rows={[["Seed", `${next + 1} of ${seeds.length}`], ["Residents × D²", `${draw.residents} × (${draw.distanceKm} km)²`], ["Chance", oneIn(draw.chance)], ["Rank", number(draw.rank)]]} />
        <p className="dd-meta font-mono">Σ p·D² = {sci(draw.total)} person·km² · u = {draw.u.toFixed(4)}</p>
        <HeatLegend />
      </div>
        : step === 3 ? <Metrics rows={[["Seeds", String(seeds.length)], ["Random seed", String(power.seed)], ["Likeliest pick", `seed ${likeliest.order}, rank ${number(likeliest.rank)}`], ["Least likely", `seed ${unlikeliest.order}, rank ${number(unlikeliest.rank)}`]]} />
          : <div className="grid gap-2">
            <p className="dd-label">Cell population vs target</p>
            <PopulationBars populations={voronoi.populations} target={power.target} />
            <Metrics rows={[["Largest gap", `±${number(Math.round(voronoi.maxDeviation))}`], ["Target", number(Math.round(power.target))]]} />
          </div>;

  return (
    <ChapterConsole number={5} title="Seeds" steps={steps} step={step} onStep={onStep}>
      <ExplainerStage projection={projection} bounds={null} points={points} showPoints={step <= 2}
        pointBins={step === 2 ? heat(next) : undefined} binColors={step === 2 ? HEAT : undefined} card={card} cardLive={!playing} cardWide={step === 2}
        label={`Michigan seeds, step ${step + 1}: ${steps[step].title}${step === 2 ? `, seed ${next + 1}` : ""}`}
        overlay={<StageLayer visible={step >= 1}>
          <SeedMarks seeds={seeds} count={step === 1 ? 1 : step === 2 ? next + 1 : seeds.length} projection={projection}
            numbered={step >= 2} latest={step === 2 ? next + 1 : undefined} />
        </StageLayer>}>
        <StateClip id={clipId} overview={overview} projection={projection} />
        <Silhouette overview={overview} coast={coast} projection={projection} />
        <StageLayer visible={step === 4}><PowerCells frame={voronoi} projection={projection} clipId={clipId} /></StageLayer>
      </ExplainerStage>
    </ChapterConsole>
  );
}
