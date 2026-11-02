import "server-only";

import { readFile } from "node:fs/promises";
import { join } from "node:path";
import type { FeatureCollection, MultiPolygon, Polygon, Position } from "geojson";

import { blockDistrictColor } from "@/lib/block-map-projection";
import type { PowerDiagram, PowerFrame, RepairData } from "@/lib/districting-explainer";

/** One step of the recorded solve, drawn in the card's square viewBox. */
export interface DistrictingCardFrame {
  /** The balancing round; 0 for the seeds' plain nearest-seed cells. */
  round: number;
  /** One path per district: its exact power cell, before clipping to the land. */
  cells: string[];
  /** Every district's center as a zero-length segment, drawn as a dot. */
  centers: string;
}

export interface DistrictingCardData {
  /** Width and height of the square viewBox. */
  view: number;
  /** Michigan's land, which clips the cells. */
  outline: string;
  /** The explorer's district colors, by district. */
  colors: string[];
  /** People per district at the target. */
  target: number;
  /** The solver's cap on balancing rounds. */
  rounds: number;
  seeds: DistrictingCardFrame;
  /** Sampled balancing rounds, then the solver's final pass after the last one. */
  frames: DistrictingCardFrame[];
  /** Largest gap from the target, in people, after each stage. */
  gaps: { seeds: number; powerDiagram: number; repaired: number; final: number };
  /** Where repair moved detached pieces and rebalancing moved blocks, as dots. */
  repair: { count: number; marks: string };
  rebalance: { count: number; marks: string };
}

const EXPLAINER = join(process.cwd(), "public", "data", "districting-explainer");
const STATES = join(process.cwd(), "public", "data", "us-states.json");
const VIEW = 200;
const PAD = 8;
/**
 * Rounds the card steps through: every early round, where the centers still
 * travel kilometers, then sparser ones as they settle to meters.
 */
const SAMPLED_ROUNDS = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 17, 20, 25, 30, 40, 50, 60, 70, 80];

const round1 = (value: number) => Math.round(value * 10) / 10;

/**
 * Michigan's recorded K13 solve for the districting home card, from the
 * walkthrough's build artifacts (scripts/build_districting_explainer.py).
 * Everything is drawn in the solver's own local plane, where power cells
 * have straight edges, so each cell is exact. The home page carries about
 * 25 kilobytes instead of the walkthrough's files.
 */
export async function loadDistrictingCard(): Promise<DistrictingCardData> {
  const [powerText, repairText, statesText] = await Promise.all([
    readFile(join(EXPLAINER, "michigan-power-diagram.json"), "utf-8"),
    readFile(join(EXPLAINER, "michigan-repair.json"), "utf-8"),
    readFile(STATES, "utf-8"),
  ]);
  const power = JSON.parse(powerText) as PowerDiagram;
  const repair = JSON.parse(repairText) as RepairData;
  const states = JSON.parse(statesText) as FeatureCollection<Polygon | MultiPolygon>;
  const michigan = states.features.find((feature) => feature.id === "26")?.geometry;
  if (!michigan) throw new Error("us-states.json has no Michigan outline");
  const polygons = michigan.type === "Polygon" ? [michigan.coordinates] : michigan.coordinates;

  const { lon0, lat0, metersPerDegreeLon, metersPerDegreeLat } = power.plane;
  const plane = ([lon, lat]: Position) => [(lon - lon0) * metersPerDegreeLon, (lat - lat0) * metersPerDegreeLat];
  const land = polygons.flat(2).map(plane);
  const minX = Math.min(...land.map(([x]) => x));
  const maxX = Math.max(...land.map(([x]) => x));
  const minY = Math.min(...land.map(([, y]) => y));
  const maxY = Math.max(...land.map(([, y]) => y));
  const scale = (VIEW - 2 * PAD) / Math.max(maxX - minX, maxY - minY);
  const offsetX = (VIEW - (maxX - minX) * scale) / 2;
  const offsetY = (VIEW - (maxY - minY) * scale) / 2;
  const project = (position: Position) => {
    const [x, y] = plane(position);
    return `${round1(offsetX + (x - minX) * scale)} ${round1(offsetY + (maxY - y) * scale)}`;
  };
  const ring = (points: Position[]) => `M${points.map(project).join("L")}Z`;
  const dots = (points: Position[]) => points.map((point) => `M${project(point)}l0 0`).join("");
  const frame = (source: PowerFrame): DistrictingCardFrame => ({
    round: source.iteration,
    cells: source.cells.map((cell) => (cell.length > 2 ? ring(cell) : "")),
    centers: dots(source.centers),
  });

  const seeds = power.frames.find((item) => item.iteration === 0);
  const last = power.frames.find((item) => item.final);
  if (!seeds || !last) throw new Error("The power-diagram recording is missing its seeds or final pass");
  const sampled = SAMPLED_ROUNDS.map((round) => {
    const found = power.frames.find((item) => item.iteration === round && !item.final);
    if (!found) throw new Error(`The power-diagram recording has no round ${round}`);
    return frame(found);
  });

  return {
    view: VIEW,
    outline: polygons.flat().map(ring).join(""),
    colors: last.cells.map((_, district) => blockDistrictColor(district, "26")),
    target: power.target,
    rounds: power.settings.max_outer_iterations,
    seeds: frame(seeds),
    frames: [...sampled, frame(last)],
    gaps: {
      seeds: seeds.maxDeviation,
      powerDiagram: repair.maxDeviation.powerDiagram,
      repaired: repair.maxDeviation.repaired,
      final: repair.maxDeviation.final,
    },
    repair: { count: repair.repair.length, marks: dots(repair.repair.map((move) => move.point)) },
    rebalance: { count: repair.rebalance.length, marks: dots(repair.rebalance.map((move) => move.point)) },
  };
}
