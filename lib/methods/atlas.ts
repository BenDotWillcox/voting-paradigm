/**
 * The atlas: Yee's spatial diagrams for the seven methods. Each cell of a
 * square grid is the same voter cloud centered there, colored by who wins.
 * Python counts every cell (POST /api/voting/atlas); this module only reads
 * the maps: which view shows which cells, area shares, and grid geometry.
 */

import type { AtlasCandidate, AtlasResponse, VotingMethod } from "@/types/methods";

import { METHOD_META } from "./instrument";

export type AtlasReference = "condorcet" | "utilitarian" | "disagreement";
export type AtlasView = VotingMethod | AtlasReference;

export const ATLAS_METHOD_VIEWS: VotingMethod[] = [
  "plurality",
  "irv",
  "borda",
  "ranked_pairs",
  "approval",
  "score",
  "quadratic",
];

export const ATLAS_REFERENCES: { id: AtlasReference; label: string; description: string }[] = [
  {
    id: "condorcet",
    label: "Condorcet winner",
    description:
      "The candidate who beats every rival head to head on the voters' sincere rankings. Blank where the majority relation cycles.",
  },
  {
    id: "utilitarian",
    label: "Least distance",
    description:
      "The candidate with the least total distance to the voters: a welfare benchmark on raw distances, not on each voter's rescaled utilities.",
  },
  {
    id: "disagreement",
    label: "Disagreement",
    description: "How many different winners the seven methods produce in each cell.",
  },
];

export function viewLabel(view: AtlasView): string {
  return isReference(view)
    ? (ATLAS_REFERENCES.find((r) => r.id === view)?.label ?? view)
    : METHOD_META[view].label;
}

export function isReference(view: AtlasView): view is AtlasReference {
  return view === "condorcet" || view === "utilitarian" || view === "disagreement";
}

/** One character per cell: a candidate ID, "-" for none, or a digit for disagreement. */
export function viewCells(atlas: AtlasResponse, view: AtlasView): string {
  if (view === "condorcet") return atlas.condorcet;
  if (view === "utilitarian") return atlas.utilitarian;
  if (view === "disagreement") return atlas.disagreement;
  return atlas.maps.find((m) => m.method === view)?.winners ?? "";
}

const NO_TIES: readonly number[] = [];

/** Cells where a tiebreak decided the winner; empty for reference views. */
export function viewTieCells(atlas: AtlasResponse, view: AtlasView): readonly number[] {
  if (isReference(view)) return NO_TIES;
  return atlas.maps.find((m) => m.method === view)?.ties ?? NO_TIES;
}

export function viewTies(atlas: AtlasResponse, view: AtlasView): Set<number> {
  return new Set(viewTieCells(atlas, view));
}

/** Share of the cells showing each character. */
export function shares(cells: string): Map<string, number> {
  const counts = new Map<string, number>();
  for (const cell of cells) counts.set(cell, (counts.get(cell) ?? 0) + 1);
  return new Map([...counts].map(([key, count]) => [key, count / Math.max(cells.length, 1)]));
}

/** The row-major cell under a point in the unit square. */
export function cellAt(x: number, y: number, size: number): number {
  const col = Math.min(size - 1, Math.max(0, Math.floor(x * size)));
  const row = Math.min(size - 1, Math.max(0, Math.floor(y * size)));
  return row * size + col;
}

/** A cell's center in the unit square. */
export function cellCenter(cell: number, size: number): [number, number] {
  return [((cell % size) + 0.5) / size, (Math.floor(cell / size) + 0.5) / size];
}

/** A layout's cache key: candidates and positions, rounded as sent. */
export function layoutKey(candidates: AtlasCandidate[]): string {
  return candidates.map((c) => `${c.id}${round(c.x)},${round(c.y)}`).join(";");
}

/** Positions are sent to three decimal places, a sixteenth of a cell. */
export function round(value: number): number {
  return Math.round(Math.min(1, Math.max(0, value)) * 1000) / 1000;
}

export interface AtlasLayout {
  id: string;
  label: string;
  caption: string;
  atlas: AtlasResponse;
}

/**
 * Copy for the curated layouts built by scripts/build_methods_artifacts.py.
 * Shares count only cells a method decided outright; api/tests/test_atlas.py
 * checks each claim against public/data/methods/atlas.json.
 */
export const LAYOUT_COPY: Record<string, { label: string; caption: string }> = {
  hub: {
    label: "Hub",
    caption:
      "D sits inside A, B and C. D is the Condorcet winner on 11% of the map, but plurality elects it on under 3%: near D, the voters on every side give their first choices to A, B or C. Instant runoff gives D 7%, and Borda, score and quadratic about 13%. Approval elects D outright on 61% and has it tied for the lead on all the rest, because D is above most voters' average utility from anywhere on the map.",
  },
  squeeze: {
    label: "Center squeeze",
    caption:
      "C sits between A and B. C is the Condorcet winner on 20% of the map, but plurality elects it on only 9%: near C, the voters on either side give their first choices to A or B. Instant runoff gives C 17%; approval gives it 55%, because C is above average for most voters.",
  },
  clones: {
    label: "Clones",
    caption:
      "B and C are a near-identical pair facing A. Plurality gives A a point more of the map than the Condorcet winner map does, because the pair splits its voters' first choices. Borda gives A four points less: on the pair's voters' ballots, the second clone pushes A a place lower.",
  },
  ring: {
    label: "Ring of five",
    caption:
      "Five candidates around a ring. Near the middle, instant runoff's eliminations cascade, and its regions break up: a tie decides 9% of its cells. Approval needs a tiebreak in 18%, Ranked Pairs in almost none.",
  },
  spread: {
    label: "Spread out",
    caption:
      "Far apart, the methods agree. Every method's map is within two points of the Condorcet winner map, and 97% of cells have a single winner across all seven.",
  },
};
