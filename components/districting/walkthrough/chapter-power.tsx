"use client";

import * as React from "react";
import { Pause, Play } from "lucide-react";

import { useReducedMotion } from "@/components/story/chart";
import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";
import type { ExplainerData, PowerFrame } from "@/lib/districting-explainer";
import { MAP_COLORS } from "@/lib/districts-palette";
import { ChapterConsole, type ChapterStep } from "./chapter-console";
import { ExplainerStage, type StageBounds } from "./explainer-stage";
import { Silhouette } from "./layers";
import { unitsPerPixel } from "./stage-layers";
import { PopulationBars, RoundTrace, PowerCells, PowerCenters, ReachCircles, StateClip } from "./power-layers";

const number = (value: number) => value.toLocaleString();
const gap = (frame: PowerFrame) => `±${number(Math.round(frame.maxDeviation))}`;
const distance = (meters: number | null) => meters === null ? "—" : meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${meters.toFixed(1)} m`;
/** Slow while the early rounds move centers by kilometers, quicker once moves shrink to meters. */
const frameMs = (round: number) => Math.max(110, Math.round(800 * 0.86 ** (round - 1)));
/** From this round on, the camera closes in on southeast Michigan's small districts (view width in km). */
const ZOOMS = [[12, 150]] as const;
/** From this round on, the camera frames one center's remaining path, so its meter-scale moves show. */
const FOCUS_FROM = 30;
/** Near the junction of three districts in western Wayne County; the nearest final-frame vertex is used. */
const JUNCTION_NEAR: [number, number] = [-83.34, 42.39];
const PLAYER = 3;

/** A ring and label on the one center the closest zoom follows. */
function FocusMark({ point, label, projection, unit }: { point: [number, number]; label: string; projection: BlockMapProjection; unit: number }) {
  const [x, y] = projection.projectPoint(point);
  const d = `M${x} ${y}l0 0`;
  return <g strokeLinecap="round">
    <path d={d} stroke={MAP_COLORS.selectionCasing} strokeWidth={30} vectorEffect="non-scaling-stroke" />
    <path d={d} stroke={MAP_COLORS.selection} strokeWidth={26} vectorEffect="non-scaling-stroke" />
    <path d={d} stroke={MAP_COLORS.selectionCasing} strokeWidth={21} vectorEffect="non-scaling-stroke" />
    <path d={d} stroke={MAP_COLORS.line} strokeWidth={8} vectorEffect="non-scaling-stroke" />
    <text x={x + 20 * unit} y={y + 4.5 * unit} fontSize={13 * unit} fontWeight={600} fontFamily="var(--dd-mono)" fill={MAP_COLORS.selection}
      stroke={MAP_COLORS.selectionCasing} strokeWidth={3.5 * unit} strokeLinejoin="round" paintOrder="stroke">{label}</text>
  </g>;
}

function Metrics({ rows }: { rows: [string, React.ReactNode][] }) {
  return <dl className="dd-card-metrics">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

/** The recorded balanced power diagram, round by round, from the verified rerun of Michigan's solve. */
export function PowerChapter({ data, projection, overview, coast }: {
  data: ExplainerData; projection: BlockMapProjection; overview: BlockMapCollection; coast: BlockMapCollection | null;
}) {
  const { power, stats } = data;
  const { frames, settings, seeds } = power;
  const last = frames.length - 1;
  const reduced = useReducedMotion();
  const [step, setStep] = React.useState(0);
  const [round, setRound] = React.useState(1);
  const [playing, setPlaying] = React.useState(false);
  const clipId = `dd-clip-${React.useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;

  React.useEffect(() => {
    if (!playing) return;
    if (round >= last) { setPlaying(false); return; }
    const timer = window.setTimeout(() => setRound(round + 1), frameMs(round));
    return () => window.clearTimeout(timer);
  }, [playing, round, last]);

  const onStep = (next: number) => {
    setStep(next);
    // The time-lapse starts itself on arrival unless the viewer prefers reduced motion.
    if (next === PLAYER && step !== PLAYER) { setRound(1); setPlaying(!reduced); }
    else if (next !== PLAYER) setPlaying(false);
  };
  const toggle = () => {
    if (!playing && round >= last) setRound(1);
    setPlaying(!playing);
  };

  const first = frames[1], final = frames[last], seedCells = frames[0];
  // The final frame's vertex shared by three or more cells nearest the chosen spot.
  const zooms = React.useMemo(() => {
    const owners = new Map<string, { point: [number, number]; cells: Set<number> }>();
    final.cells.forEach((ring, district) => ring.forEach((point) => {
      const key = `${point[0].toFixed(3)},${point[1].toFixed(3)}`;
      const entry = owners.get(key) ?? { point, cells: new Set<number>() };
      entry.cells.add(district);
      owners.set(key, entry);
    }));
    const junctions = [...owners.values()].filter((entry) => entry.cells.size >= 3).map((entry) => entry.point);
    const [x, y] = junctions.reduce((best, point) =>
      Math.hypot(point[0] - JUNCTION_NEAR[0], point[1] - JUNCTION_NEAR[1]) < Math.hypot(best[0] - JUNCTION_NEAR[0], best[1] - JUNCTION_NEAR[1]) ? point : best);
    const levels: { from: number; km: number; bounds: StageBounds; focus?: number }[] = ZOOMS.map(([from, km]) => {
      const halfLon = km / 2 / (111.195 * Math.cos((y * Math.PI) / 180)), halfLat = (km / 2) * 0.62 / 111.195;
      return { from, km, bounds: [x - halfLon, y - halfLat, x + halfLon, y + halfLat] as StageBounds };
    });
    // The center that travels farthest after FOCUS_FROM, framed around its whole remaining path.
    const { metersPerDegreeLon: mx, metersPerDegreeLat: my } = power.plane;
    const late = frames.slice(FOCUS_FROM, last);
    const travel = (district: number) => late.slice(1).reduce((sum, item, index) => {
      const [a, b] = [late[index].centers[district], item.centers[district]];
      return sum + Math.hypot((b[0] - a[0]) * mx, (b[1] - a[1]) * my);
    }, 0);
    const focus = final.centers.map((_, district) => district).reduce((best, district) => travel(district) > travel(best) ? district : best);
    const lons = late.map((item) => item.centers[focus][0]), lats = late.map((item) => item.centers[focus][1]);
    const cx = (Math.min(...lons) + Math.max(...lons)) / 2, cy = (Math.min(...lats) + Math.max(...lats)) / 2;
    const widthM = Math.max(500, ((Math.max(...lons) - Math.min(...lons)) * mx) * 1.8, ((Math.max(...lats) - Math.min(...lats)) * my * 1.8) / 0.62);
    const halfLon = widthM / 2 / mx, halfLat = (widthM / 2) * 0.62 / my;
    levels.push({ from: FOCUS_FROM, km: Math.round(widthM / 100) / 10, focus, bounds: [cx - halfLon, cy - halfLat, cx + halfLon, cy + halfLat] });
    return levels;
  }, [final, frames, last, power.plane]);
  const zoom = step === PLAYER ? [...zooms].reverse().find((level) => round >= level.from) : undefined;

  const roundLabel = (frame: PowerFrame) => frame.final ? "Final balance" : `Round ${frame.iteration} / ${settings.max_outer_iterations}`;
  const county = (district: number) => stats.countyNames[seeds[district].geoid.slice(2, 5)] ?? "Michigan";
  const largest = seedCells.populations.indexOf(Math.max(...seedCells.populations));
  const smallest = seedCells.populations.indexOf(Math.min(...seedCells.populations));
  const farthest = final.reachKm.indexOf(Math.max(...final.reachKm));
  const lastMove = frames[last - 1].maxMoveM;
  const moves = React.useMemo(() => frames.slice(1, last).map((item) => item.maxMoveM ?? 0), [frames, last]);
  const frameIndex = step === 0 ? 0 : step <= 2 ? 1 : step === PLAYER ? round : last;
  const frame = frames[frameIndex];

  const steps: ChapterStep[] = [
    { title: "Why the seeds aren't enough",
      body: <><p>Chapter 5 ended with nearest-seed cells, and they ignore population: the {county(largest)} cell holds {number(seedCells.populations[largest])} people and the {county(smallest)} cell {number(seedCells.populations[smallest])}, against a target of {number(Math.round(power.target))}.</p>
        <p className="mt-2">Moving the seeds cannot fix that on its own, because a border between nearest-seed cells always sits exactly halfway between two seeds. Each center needs a way to push its borders out or pull them in.</p></> },
    { title: "Weights move the borders",
      body: <><p>Each center c<sub>i</sub> gets a weight w<sub>i</sub>, and a block at x joins the district with the smallest <em>power distance</em>:</p>
        <p className="dd-formula">|x − c<sub>i</sub>|² − w<sub>i</sub></p>
        <p>A larger weight claims more blocks. Borders stay straight: districts i and j split along the line</p>
        <p className="dd-formula">2(c<sub>j</sub> − c<sub>i</sub>)·x<br />= |c<sub>j</sub>|² − |c<sub>i</sub>|² − (w<sub>j</sub> − w<sub>i</sub>)</p>
        <p className="dd-meta mt-2">Adding the same amount to every weight changes nothing, so each circle draws a weight above the smallest as a radius, √(w<sub>i</sub> − min w).</p></> },
    { title: "Solving for the weights",
      body: <><p>The weights come from maximizing a single concave function, the dual of the balancing problem, where T<sub>i</sub> is each district&rsquo;s target:</p>
        <p className="dd-formula">D(w) = Σ<sub>j</sub> p<sub>j</sub>·min<sub>i</sub>(|x<sub>j</sub> − c<sub>i</sub>|² − w<sub>i</sub>) + Σ<sub>i</sub> T<sub>i</sub>·w<sub>i</sub></p>
        <p>Its slope along each weight is the target minus the cell&rsquo;s current population:</p>
        <p className="dd-formula">∂D/∂w<sub>i</sub> = T<sub>i</sub> − P<sub>i</sub>(w)</p>
        <p>Climbing it raises every underfilled cell&rsquo;s weight and lowers every overfilled one. L-BFGS-B, a quasi-Newton method, climbs in at most {settings.inner_max_iterations} steps; one solve takes the largest gap from {gap(seedCells)} to {gap(first)}.</p></> },
    { title: "Balance, recenter, repeat",
      body: <><p>Each round solves the weights, then moves each center to its cell&rsquo;s population center. That makes districts more compact but unbalances them, so the next round solves the weights again.</p>
        <p className="mt-2">Early rounds move centers by kilometers and play slowly; later rounds move them by meters, so partway through, the view zooms in on southeast Michigan, where districts are smallest, then onto a single center to follow its last, meter-scale moves.</p>
        <div className="dd-player">
          <button type="button" className="dd-tool" onClick={toggle}>{playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}{playing ? "Pause" : "Play"}</button>
          <input type="range" className="dd-scrub" min={1} max={last} value={round} aria-label="Round" aria-valuetext={roundLabel(frames[round])}
            onChange={(event) => { setPlaying(false); setRound(Number(event.target.value)); }} />
        </div></> },
    { title: "Sparse districts reach farther",
      body: <p>By the end, the northern district, which takes in the whole Upper Peninsula, has the longest reach: {final.reachKm[farthest].toFixed(0)} km. The Detroit district has none. A thinly settled district needs a large weight to gather enough people; a dense one needs almost none.</p> },
    { title: "Where it stops",
      body: <p>The centers&rsquo; moves shrink from {distance(first.maxMoveM)} in round 1 to a few meters, but never reach the {settings.center_tolerance_m * 1000} mm tolerance, so the run stops at its {settings.max_outer_iterations}-round cap. A last weight solve leaves every cell within {gap(final)} people of the target. The power diagram never looked at the block graph, though: {power.detachedPieces} pieces ended up cut off from the rest of their district. Repairing them comes next.</p> },
  ];

  const card = step === 0 ? <div className="grid gap-2">
    <p className="dd-label">Nearest-seed cell populations vs target</p>
    <PopulationBars populations={seedCells.populations} target={power.target} />
    <Metrics rows={[["Largest gap", gap(seedCells)], ["Target", number(Math.round(power.target))]]} />
  </div>
    : step === 1 ? <Metrics rows={[["After round 1", `${gap(first)} people`], ["Before weights", gap(seedCells)]]} />
      : step === 2 ? <div className="grid gap-2">
        <p className="dd-label">After one weight solve</p>
        <PopulationBars populations={first.populations} target={power.target} />
        <Metrics rows={[["Largest gap", gap(first)], ["Was", gap(seedCells)]]} />
      </div>
        : step === PLAYER ? <div className="grid gap-2">
          <Metrics rows={[["Round", roundLabel(frame).replace("Round ", "")], ["Largest gap", gap(frame)], ["Centers moved", distance(frame.maxMoveM)], ["View", zoom ? `${zoom.km} km wide` : "Whole state"]]} />
          <PopulationBars populations={frame.populations} target={power.target} />
          <RoundTrace values={moves} current={Math.min(round, moves.length) - 1} label="center moves, log scale" />
        </div>
          : step === 4 ? <Metrics rows={[["Longest reach", `${final.reachKm[farthest].toFixed(0)} km`], ["Shortest", `${Math.min(...final.reachKm).toFixed(0)} km`]]} />
            : <Metrics rows={[["Rounds", `${settings.max_outer_iterations} (cap)`], ["Last move", distance(lastMove)], ["Largest gap", gap(final)], ["Cut-off pieces", String(power.detachedPieces)]]} />;

  return (
    <ChapterConsole number={6} title="The power diagram, running" steps={steps} step={step} onStep={onStep}>
      <ExplainerStage projection={projection} bounds={zoom?.bounds ?? null} card={card} cardLive={!playing}
        label={`Michigan power diagram, step ${step + 1}: ${steps[step].title}, ${roundLabel(frame)}`}>
        <StateClip id={clipId} overview={overview} projection={projection} />
        <Silhouette overview={overview} coast={coast} projection={projection} />
        <PowerCells frame={frame} projection={projection} clipId={clipId} highlight={step === 4 ? farthest : undefined} />
        {(step === 1 || step === 4) && <ReachCircles frame={frame} projection={projection} plane={power.plane} highlight={step === 4 ? farthest : undefined} />}
        <PowerCenters frames={frames} current={frameIndex} projection={projection} trails={step === PLAYER} />
        {zoom?.focus !== undefined && zoom.bounds && <FocusMark point={frame.centers[zoom.focus]} label={`District ${zoom.focus + 1} center`} projection={projection} unit={unitsPerPixel(zoom.bounds, projection)} />}
      </ExplainerStage>
    </ChapterConsole>
  );
}
