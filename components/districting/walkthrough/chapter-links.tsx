"use client";

import * as React from "react";
import type { Feature, Geometry } from "geojson";

import { BLOCK_MAP_HEIGHT, BLOCK_MAP_WIDTH, makeStateBlockProjection } from "@/lib/block-map-projection";
import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";
import type { ExplainerCore, OutlineCase, RecordedLink, WindowCase } from "@/lib/districting-explainer";
import { MAP_COLORS } from "@/lib/districts-palette";
import { ChapterConsole, type ChapterStep } from "./chapter-console";
import { ExplainerStage } from "./explainer-stage";
import { BlockShapes, WALKTHROUGH_COLORS, usePath } from "./layers";

const number = (value: number) => value.toLocaleString();
const km = (meters: number) => `${(meters / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} km`;
/** One tint per state in the Kentucky Bend, from the wide opening view down to the blocks. */
const STATE_TINTS: Record<string, { fill: string; strong?: string }> = {
  "21": { fill: "#e4dff3", strong: "#c6bcea" }, // Kentucky; strong marks its cut-off piece
  "29": { fill: "#d9e8c8" }, // Missouri, kept apart from the water blue
  "47": { fill: "#f4e4cb" }, // Tennessee
};
const CUT_OFF_NAMES: Record<string, string> = {
  "ky-exclave-001": "Kentucky Bend", "ny-water-liberty-001": "Liberty Island", "ny-exclave-ellis-001": "Ellis Island",
};

function collection(features: Feature<Geometry>[]): BlockMapCollection {
  return { type: "FeatureCollection", features: features.map((feature) => ({ ...feature, properties: {} })) };
}
function boxFeature([w, s, e, n]: readonly number[]): Feature<Geometry> {
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } };
}

/** Recorded links as dashed lines, water in magenta and exclave in amber, with endpoint dots. */
function Links({ links, projection }: { links: RecordedLink[]; projection: BlockMapProjection }) {
  return <g fill="none" strokeLinecap="round">
    {links.map((link) => {
      const points = link.geometry.coordinates.map((point) => projection.projectPoint(point));
      const d = points.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(4)} ${y.toFixed(4)}`).join("");
      const ends = [points[0], points[points.length - 1]].map(([x, y]) => `M${x.toFixed(4)} ${y.toFixed(4)}l0 0`).join("");
      const color = link.kind === "exclave" ? MAP_COLORS.recordedExclave : MAP_COLORS.recordedWater;
      return <g key={link.id}>
        <path d={d} stroke={MAP_COLORS.casing} strokeWidth={5} vectorEffect="non-scaling-stroke" />
        <path d={d} stroke={color} strokeWidth={2.2} strokeDasharray="6 4" vectorEffect="non-scaling-stroke" />
        <path d={ends} stroke={color} strokeWidth={7} vectorEffect="non-scaling-stroke" />
      </g>;
    })}
  </g>;
}

function Label({ point, projection, children }: { point: [number, number]; projection: BlockMapProjection; children: string }) {
  const [x, y] = projection.projectPoint(point);
  return <text x={x} y={y - 12} textAnchor="middle" fontSize={15} fontWeight={600} fill={MAP_COLORS.label} stroke={MAP_COLORS.labelHalo} strokeWidth={4} paintOrder="stroke">{children}</text>;
}

function OutlineFigure({ data, projection }: { data: OutlineCase; projection: BlockMapProjection }) {
  const path = usePath(projection);
  return <g>
    <path d={path(data.outline) ?? ""} fill={WALKTHROUGH_COLORS.silhouette} fillRule="evenodd" stroke={MAP_COLORS.line} strokeOpacity={0.45} strokeWidth={0.7} vectorEffect="non-scaling-stroke" />
    <Links links={data.links} projection={projection} />
  </g>;
}

/**
 * Whole neighboring states for the opening view, with labels sized for that
 * zoomed-out camera; the labels and the target box fade as the camera flies in.
 */
function ContextStates({ data, projection }: { data: WindowCase; projection: BlockMapProjection }) {
  const path = usePath(projection);
  if (!data.context || !data.contextBounds) return null;
  const [w, s, e, n] = data.contextBounds;
  const corners = ([[w, s], [e, s], [w, n], [e, n]] as [number, number][]).map((point) => projection.projectPoint(point));
  const xs = corners.map(([x]) => x), ys = corners.map(([, y]) => y);
  const scale = Math.max(Math.max(...xs) - Math.min(...xs), ((Math.max(...ys) - Math.min(...ys)) * BLOCK_MAP_WIDTH) / BLOCK_MAP_HEIGHT) / BLOCK_MAP_WIDTH;
  const [bx0, by0] = projection.projectPoint([data.window[0], data.window[3]]);
  const [bx1, by1] = projection.projectPoint([data.window[2], data.window[1]]);
  return <g>
    {data.context.map((state) => <path key={state.stateFips} d={path({ type: "Feature", properties: {}, geometry: state.geometry }) ?? ""} fillRule="evenodd"
      fill={STATE_TINTS[state.stateFips]?.fill ?? (state.stateFips === data.stateFips ? WALKTHROUGH_COLORS.silhouette : WALKTHROUGH_COLORS.neighbor)}
      stroke={MAP_COLORS.line} strokeOpacity={0.5} strokeWidth={0.9} vectorEffect="non-scaling-stroke" />)}
    <g className="dd-fade-late">
      <rect x={bx0} y={by0} width={bx1 - bx0} height={by1 - by0} fill="none" stroke={MAP_COLORS.selection} strokeWidth={2} vectorEffect="non-scaling-stroke" />
      {data.context.map((state) => {
        const [x, y] = projection.projectPoint(state.labelPoint);
        return <text key={state.stateFips} x={x} y={y} textAnchor="middle" fontSize={17 * scale} fontWeight={600} fill={MAP_COLORS.label}
          stroke={MAP_COLORS.labelHalo} strokeWidth={4 * scale} paintOrder="stroke">{state.state}</text>;
      })}
    </g>
  </g>;
}

function WindowFigure({ data, projection }: { data: WindowCase; projection: BlockMapProjection }) {
  const path = usePath(projection);
  const highlighted = React.useMemo(() => new Set(data.blocks.filter((block) => block.endpoint || block.cutOff).map((block) => block.geoid)), [data]);
  const byId = React.useMemo(() => new Map(data.blocks.map((block) => [block.geoid, block])), [data]);
  return <g>
    <ContextStates data={data} projection={projection} />
    {data.neighbors.map((neighbor) => <path key={neighbor.stateFips} d={path({ type: "Feature", properties: {}, geometry: neighbor.geometry }) ?? ""}
      fill={STATE_TINTS[neighbor.stateFips]?.fill ?? WALKTHROUGH_COLORS.neighbor} fillRule="evenodd" stroke={MAP_COLORS.line} strokeOpacity={0.35} strokeWidth={0.8} strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />)}
    <BlockShapes blocks={data.blocks} projection={projection} highlight={highlighted} strong
      landHighlight={STATE_TINTS[data.stateFips]?.strong ?? WALKTHROUGH_COLORS.highlightLand} landFill={STATE_TINTS[data.stateFips]?.fill} />
    <Links links={data.links} projection={projection} />
    {data.links.map((link) => {
      const cut = link.endpoints.map((geoid) => byId.get(geoid)).find((block) => block?.cutOff && block.labelPoint);
      return cut?.labelPoint && CUT_OFF_NAMES[link.id] ? <Label key={link.id} point={cut.labelPoint} projection={projection}>{CUT_OFF_NAMES[link.id]}</Label> : null;
    })}
  </g>;
}

function Metrics({ rows, note, legend }: { rows: [string, string][]; note?: string; legend?: { label: string; color: string }[] }) {
  return <div className="grid gap-2">
    <dl className="dd-card-metrics">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    {note && <p className="dd-meta flex items-center gap-1.5"><span aria-hidden="true" className="inline-block h-2.5 w-4 rounded-[1px] border border-dashed border-[#454545]/40" style={{ background: WALKTHROUGH_COLORS.neighbor }} />{note}</p>}
    {legend && <p className="dd-meta flex flex-wrap items-center gap-x-3 gap-y-1">{legend.map((item) => <span key={item.label} className="inline-flex items-center gap-1.5">
      <span aria-hidden="true" className="inline-block h-2.5 w-4 rounded-[1px] border border-[#454545]/40" style={{ background: item.color }} />{item.label}</span>)}</p>}
  </div>;
}

/** Where the block graph alone cannot connect a state: recorded links. */
export function LinksChapter({ data }: { data: ExplainerCore }) {
  const [step, setStep] = React.useState(0);
  const { hawaii, kentucky, newYork, alaska, summary } = data.special;
  const projections = React.useMemo(() => ({
    hawaii: makeStateBlockProjection(collection([hawaii.outline]), hawaii.stateFips),
    kentucky: makeStateBlockProjection(collection([boxFeature(kentucky.window)]), kentucky.stateFips),
    newYork: makeStateBlockProjection(collection([boxFeature(newYork.window)]), newYork.stateFips),
    alaska: makeStateBlockProjection(collection([alaska.outline]), alaska.stateFips),
  }), [hawaii, kentucky, newYork, alaska]);
  const liberty = newYork.links.find((link) => link.kind === "water")!;
  const ellis = newYork.links.find((link) => link.kind === "exclave")!;

  const steps: (ChapterStep & { key: keyof typeof projections; figure: React.ReactNode; card: React.ReactNode; cardAt?: "top-left"; startBounds?: [number, number, number, number] })[] = [
    { key: "hawaii", title: "Hawaii: open ocean",
      body: <><p>Michigan&rsquo;s water blocks connect it, but {summary.statesWithLinks} of {summary.states} states needed help: {summary.links} recorded links in all. In Hawaii, no chain of census blocks crosses the channels between islands, so {hawaii.links.length} recorded links name the endpoint blocks to join. The longest spans {km(hawaii.longestLinkM)}.</p><p className="dd-meta mt-2">A recorded link is one extra edge in the graph. The polygons never change, nothing is built across the gap, and a link counts only when both endpoints are in the same district.</p></>,
      figure: <OutlineFigure data={hawaii} projection={projections.hawaii} />,
      card: <Metrics rows={[["Recorded links", String(hawaii.links.length)], ["Longest", km(hawaii.longestLinkM)], ["Districts at 435", String(hawaii.districtsAt435)]]} /> },
    { key: "kentucky", title: "Kentucky: the Bend", startBounds: kentucky.contextBounds,
      body: <p>The Kentucky Bend is Kentucky land cut off from the rest of the state by a loop of the Mississippi River, with Missouri across the water and Tennessee to the south. One recorded exclave link, {km(kentucky.longestLinkM)}, joins it to the rest of Kentucky.</p>,
      figure: <WindowFigure data={kentucky} projection={projections.kentucky} />,
      card: <Metrics rows={[["Recorded links", "1 exclave"], ["Length", km(kentucky.longestLinkM)]]}
        legend={[{ label: "Kentucky", color: STATE_TINTS["21"].fill }, ...kentucky.neighbors.map((n) => ({ label: n.state, color: STATE_TINTS[n.stateFips]?.fill ?? WALKTHROUGH_COLORS.neighbor }))]} /> },
    { key: "newYork", title: "New York: Liberty and Ellis",
      body: <p>Liberty Island and New York&rsquo;s part of Ellis Island sit in New Jersey&rsquo;s waters. Two short links tie them to New York&rsquo;s harbor water: a water link to Liberty Island ({number(Math.round(liberty.distanceM))} m) and an exclave link to Ellis Island ({number(Math.round(ellis.distanceM))} m), which also crosses New Jersey land. No one lives in either block today, but if anyone did, these links would keep them correctly in a New York district.</p>,
      figure: <WindowFigure data={newYork} projection={projections.newYork} />,
      card: <Metrics rows={[["Water link", `${number(Math.round(liberty.distanceM))} m`], ["Exclave link", `${number(Math.round(ellis.distanceM))} m`]]} note="Neighbor: New Jersey" /> },
    { key: "alaska", title: "Alaska: across the date line", cardAt: "top-left",
      body: <p>Alaska needs the most: {alaska.links.length} recorded water links, the longest about {km(alaska.longestLinkM)} along the Aleutians. A few of the westernmost islands lie past the 180° line of longitude, in the Eastern Hemisphere. The solver and the map both treat longitude as continuous there, so those islands sit beside the rest of the chain instead of at the far edge of the world. Alaska has {alaska.districtsAt435} district at House 435 and {alaska.districtsAt1000} at 1,000; either way every island must connect.</p>,
      figure: <OutlineFigure data={alaska} projection={projections.alaska} />,
      card: <Metrics rows={[["Recorded links", String(alaska.links.length)], ["Longest", km(alaska.longestLinkM)], ["Districts at 435", String(alaska.districtsAt435)], ["Districts at 1,000", String(alaska.districtsAt1000)]]} /> },
  ];
  const current = steps[step];

  return (
    <ChapterConsole number={3} title="Special cases: when land doesn't touch" steps={steps} step={step} onStep={setStep}>
      <ExplainerStage key={current.key} fadeIn projection={projections[current.key]} bounds={null} startBounds={current.startBounds} padding={0} card={current.card} cardAt={current.cardAt}
        label={`Recorded links, step ${step + 1}: ${current.title}`}>
        {current.figure}
      </ExplainerStage>
    </ChapterConsole>
  );
}
