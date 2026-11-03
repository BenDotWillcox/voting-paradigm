import type { Feature, Geometry, LineString } from "geojson";

/** Static data for the Michigan walkthrough, built by scripts/build_districting_explainer.py. */
export const EXPLAINER_ROOT = "/data/districting-explainer";

export interface ExplainerBlock {
  /** Index in source order, which is also the shared-edge graph node index. */
  i: number;
  geoid: string;
  population: number;
  landM2: number;
  waterM2: number;
  housingUnits?: number;
  urban?: string;
  point: [number, number];
  geometry: Geometry;
}

export interface ExplainerWindow {
  bbox: [number, number, number, number];
  clippedTo: [number, number, number, number];
  blocks: ExplainerBlock[];
  /** Pairs of graph node indices, both inside the window. */
  edges: [number, number][];
}

export interface ExplainerWindows {
  windows: {
    detroit: ExplainerWindow & {
      featured: string;
      corner: { point: [number, number]; cornerPair: [string, string]; blocks: string[] };
    };
    /**
     * The fewest blocks from Upper to Lower Peninsula land. `route` is the
     * shortest line through them, crossing each shared boundary once at the
     * points in `doorways`; `chainCount` chains tie at that length.
     */
    straits: ExplainerWindow & {
      path: string[];
      doorways: [number, number][];
      route: [number, number][];
      chainCount: number;
      waterTouchingBothShores: number;
    };
  };
  upperPeninsula: ExplainerBlock & { neighbors: ExplainerBlock[] };
  multipart: ExplainerBlock & { parts: number; neighbors: ExplainerBlock[] };
}

export interface ExplainerStats {
  blocks: number;
  residents: number;
  districts: number;
  targetPerDistrict: number;
  populatedBlocks: number;
  zeroPopulationBlocks: number;
  waterOnlyBlocks: number;
  tracts: number;
  largestBlockPopulation: number;
  multipartBlocks: number;
  /** County FIPS (three digits) to display name, from the explorer's county index. */
  countyNames: Record<string, string>;
  graph: {
    edge_count: number;
    component_count: number;
    isolated_node_count: number;
    candidate_pair_count: number;
    excluded_corner_pair_count: number;
    interior_overlap_pair_count: number;
    source_coordinate_count: number;
    de9im_pattern: string;
    definition: string;
  };
}

/** An extra graph edge between two named endpoint blocks; the polygons never change. */
export interface RecordedLink {
  id: string;
  kind: "water" | "exclave";
  distanceM: number;
  endpoints: string[];
  geometry: LineString;
}

export interface SpecialCaseBlock {
  geoid: string;
  population: number;
  landM2: number;
  endpoint: boolean;
  /** On a piece of its state that the window encloses: the exclave or island side. */
  cutOff: boolean;
  labelPoint?: [number, number];
  geometry: Geometry;
}

interface SpecialCaseBase {
  state: string;
  stateFips: string;
  coordinateFrame: string;
  districtsAt435: number;
  districtsAt1000: number;
  links: RecordedLink[];
  longestLinkM: number;
}
export interface OutlineCase extends SpecialCaseBase { outline: Feature<Geometry> }
export interface WindowCase extends SpecialCaseBase {
  window: [number, number, number, number];
  blocks: SpecialCaseBlock[];
  neighbors: { state: string; stateFips: string; labelPoint: [number, number]; geometry: Geometry }[];
  /** Whole neighboring states for a zoomed-out first view, where the case needs one. */
  context?: { state: string; stateFips: string; labelPoint: [number, number]; geometry: Geometry }[];
  contextBounds?: [number, number, number, number];
}
export interface SpecialCases {
  hawaii: OutlineCase;
  kentucky: WindowCase;
  newYork: WindowCase;
  alaska: OutlineCase;
  summary: { statesWithLinks: number; states: number; links: number; linkedStates: string[] };
}

interface ExplainerManifest {
  schemaVersion: 1;
  points: { count: number; bbox: [number, number, number, number]; layout: string[] };
  files: { path: string; bytes: number; sha256: string }[];
}

/** Every Michigan block as its internal point, in graph order. */
export interface ExplainerPoints {
  count: number;
  lon: Float64Array;
  lat: Float64Array;
  population: Uint16Array;
  waterOnly: Uint8Array;
}

/** One frame of the recorded power diagram: frame 0 is the bare seeds, the last is the final balance pass. */
export interface PowerFrame {
  iteration: number;
  centers: [number, number][];
  /** √(wᵢ − min w) in km: each weight read as a reach above the smallest. */
  reachKm: number[];
  populations: number[];
  maxDeviation: number;
  /** How far the centers moved after this round; null for the seeds and the final pass. */
  maxMoveM: number | null;
  cells: [number, number][][];
  final?: boolean;
}

export interface SeedDraw {
  order: number;
  block: number;
  u: number;
  chance: number;
  /** 1 = the single most likely block for this draw. */
  rank: number;
  residents: number;
  /** Distance to the nearest earlier seed; null for the first draw. */
  distanceKm: number | null;
  /** Σ pⱼ in people for the first draw; Σ pⱼ·Dⱼ² in person·km² afterwards. */
  total: number;
}

export interface PowerDiagram {
  seed: number;
  settings: { max_outer_iterations: number; inner_max_iterations: number; center_tolerance_m: number };
  centersConverged: boolean;
  target: number;
  seeds: { order: number; block: number; geoid: string; population: number; point: [number, number] }[];
  /** Each k-means++ draw, replayed exactly: the uniform number, the chosen block's chance and its rank. */
  draws: SeedDraw[];
  /** The solver's local plane: meters east and north of a population-weighted origin. */
  plane: { lon0: number; lat0: number; metersPerDegreeLon: number; metersPerDegreeLat: number };
  detachedPieces: number;
  frames: PowerFrame[];
}

/** One detached piece, moved whole to a district it touches. */
export interface RepairMove {
  order: number;
  units: number[];
  source: number;
  target: number;
  population: number;
  landM2: number;
  county: string;
  point: [number, number];
  /** Largest gap from the target after this move. */
  maxDeviation: number;
}

/** One populated block moved across a border to improve balance. */
export interface BalanceMove {
  order: number;
  unit: number;
  source: number;
  target: number;
  population: number;
  county: string;
  point: [number, number];
  maxDeviation: number;
}

/** A window block with its district after the power diagram, after repair, and in the final plan. */
export interface StageBlock extends ExplainerBlock {
  labels: [number, number, number];
}

export interface StageWindow {
  bbox: [number, number, number, number];
  focus: number[];
  blocks: StageBlock[];
  edges: [number, number][];
  /** The move this window illustrates, 1-based within its stage. */
  move: number;
}

export interface RepairData {
  target: number;
  detachedPieces: number;
  stopReason: "local_optimum" | "max_moves";
  populations: Record<"powerDiagram" | "repaired" | "final", number[]>;
  maxDeviation: Record<"powerDiagram" | "repaired" | "final", number>;
  piecesPerDistrict: number[];
  repair: RepairMove[];
  rebalance: BalanceMove[];
  windows: Record<"heaviestPiece" | "firstBalance", StageWindow> & {
    /** With the shortest line from the piece to the rest of its own district. */
    widestPiece: StageWindow & { gap: { from: [number, number]; to: [number, number]; distanceM: number; block: string; touches: number[] } };
  };
}

/** Every block's district at each stage, in graph order; later stages replay the saved moves. */
export interface StageLabels {
  powerDiagram: Uint8Array;
  repaired: Uint8Array;
  final: Uint8Array;
}

/** Population and county measures for one map, from the same 2020 block counts. */
export interface PlanSummary {
  populations: number[];
  maxDeviation: number;
  spread: number;
  counties: number;
  countiesSplit: number;
  countyPieces: number;
}

/** The block pipeline's read-only validator, run on the saved plan and cross-checked by the build. */
export interface ValidationRecord {
  validator: { path: string; sha256: string };
  report: { path: string; sha256: string };
  result: {
    status: string;
    block_count: number;
    total_population: number;
    district_populations: number[];
    max_absolute_deviation_people: number;
    physical_polygon_components: number[];
    policy_components: number[];
    policy: string;
    checks: Record<string, boolean | number | string>;
    limitations: string[];
  };
  officialTotals: { blockCount: number; residentPopulation: number; blockCountSourceUrl: string; residentPopulationSourceUrl: string; validated: boolean };
  geometry: {
    source_invalid_geometries: number;
    dissolved_geometries_valid: boolean;
    district_coverage_is_valid: boolean;
    district_overlap_area_square_meters: number;
  };
  strictValidation: { passed: boolean; issues: unknown[] };
  tractsSplit: number;
}

export type EnactedFeature = Feature<Geometry, { district: number; labelPoint: [number, number] }>;

/** Michigan's enacted 118th-Congress map, measured on the same blocks as the computed one. */
export interface EnactedComparison {
  source: { url: string; sha256: string; bytes: number; lastModified: string };
  landOutline: { url: string; sha256: string; scale: string };
  computed: PlanSummary;
  enacted: PlanSummary;
  compactness: { computed: number[]; enacted: number[] };
  unplacedEmptyBlocks: number;
  features: EnactedFeature[];
  method: string;
}

/** One state's computed House-435 plan beside its serving (119th Congress) map, measured the same way. */
export interface ExtremeState {
  state: string;
  stateFips: string;
  districts: number;
  bbox: [number, number, number, number];
  computed: { pp: number[]; features: { district: number; geometry: Geometry }[] };
  enacted: { pp: number[]; features: { district: number; geometry: Geometry }[] };
  /** What makes the serving map's lines visible as choices, all measured from the maps. */
  callouts: {
    /** Districts reaching within radiusKm of one city's downtown, on each map. */
    focus: { city: string; point: [number, number]; radiusKm: number; enacted: number; computed: number };
    /** The serving map's least compact district and the listed cities inside it. */
    leastCompact: { district: number; index: number; pp: number; cities: string[]; labelPoint: [number, number] };
    cities: { name: string; point: [number, number] }[];
  };
}

export interface ExplainerChecks {
  validation: ValidationRecord;
  enacted: EnactedComparison;
  extremes: ExtremeState[];
  /** Every compactness figure uses land shapes simplified to this many degrees (about 500 m). */
  compactnessToleranceDegrees: number;
}

/** What chapters 1–4 need: the block points, curated windows and special cases. */
export interface ExplainerCore {
  stats: ExplainerStats;
  windows: ExplainerWindows;
  points: ExplainerPoints;
  special: SpecialCases;
}

/** What chapters 5–9 add: the recorded solve, repair and balancing, checks and comparisons. */
export interface ExplainerRest {
  power: PowerDiagram;
  repair: RepairData;
  labels: StageLabels;
  checks: ExplainerChecks;
}

export type ExplainerData = ExplainerCore & ExplainerRest;

async function verified(manifest: ExplainerManifest, name: string, signal: AbortSignal): Promise<ArrayBuffer> {
  const entry = manifest.files.find((file) => file.path === name);
  if (!entry) throw new Error(`The walkthrough manifest does not list ${name}.`);
  // The content hash in the URL keeps caches from mixing files across rebuilds.
  const response = await fetch(`${EXPLAINER_ROOT}/${name}?v=${entry.sha256.slice(0, 16)}`, { signal });
  if (!response.ok) throw new Error(`Walkthrough data request failed (${response.status}).`);
  const buffer = await response.arrayBuffer();
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", buffer)), (byte) => byte.toString(16).padStart(2, "0")).join("");
  if (buffer.byteLength !== entry.bytes || digest !== entry.sha256) throw new Error(`${name} does not match its manifest hash.`);
  return buffer;
}

function decodePoints(buffer: ArrayBuffer, manifest: ExplainerManifest): ExplainerPoints {
  const { count, bbox } = manifest.points;
  if (buffer.byteLength !== count * 7) throw new Error("Unexpected point file size.");
  const lonQ = new Uint16Array(buffer.slice(0, count * 2));
  const latQ = new Uint16Array(buffer.slice(count * 2, count * 4));
  const population = new Uint16Array(buffer.slice(count * 4, count * 6));
  const waterOnly = new Uint8Array(buffer.slice(count * 6, count * 7));
  const lon = new Float64Array(count), lat = new Float64Array(count);
  for (let i = 0; i < count; i++) {
    lon[i] = bbox[0] + (lonQ[i] / 65535) * (bbox[2] - bbox[0]);
    lat[i] = bbox[1] + (latQ[i] / 65535) * (bbox[3] - bbox[1]);
  }
  return { count, lon, lat, population, waterOnly };
}

function stageLabels(buffer: ArrayBuffer, repair: RepairData, count: number): StageLabels {
  if (buffer.byteLength !== count) throw new Error("Unexpected label file size.");
  const powerDiagram = new Uint8Array(buffer);
  const repaired = powerDiagram.slice();
  for (const move of repair.repair) for (const unit of move.units) repaired[unit] = move.target;
  const final = repaired.slice();
  for (const move of repair.rebalance) final[move.unit] = move.target;
  return { powerDiagram, repaired, final };
}

async function loadManifest(signal: AbortSignal): Promise<ExplainerManifest> {
  const response = await fetch(`${EXPLAINER_ROOT}/manifest.json`, { signal, cache: "no-cache" });
  if (!response.ok) throw new Error(`Walkthrough manifest request failed (${response.status}).`);
  const manifest = await response.json() as ExplainerManifest;
  if (manifest.schemaVersion !== 1) throw new Error("Unsupported walkthrough data version.");
  return manifest;
}

const decoder = new TextDecoder();
const json = <T,>(manifest: ExplainerManifest, name: string, signal: AbortSignal) =>
  verified(manifest, name, signal).then((buffer) => JSON.parse(decoder.decode(buffer)) as T);

/**
 * The walkthrough's data in two stages. The first chapters' files load first;
 * the later chapters' files start only once those arrive, so the opening
 * chapters never share bandwidth with the rest.
 */
export function loadExplainer(signal: AbortSignal): { core: Promise<ExplainerCore>; rest: Promise<ExplainerRest> } {
  const manifest = loadManifest(signal);
  const core = manifest.then(async (m) => {
    const [stats, windows, points, special] = await Promise.all([
      json<ExplainerStats>(m, "michigan-stats.json", signal),
      json<ExplainerWindows>(m, "michigan-windows.json", signal),
      verified(m, "michigan-points.bin", signal).then((buffer) => decodePoints(buffer, m)),
      json<SpecialCases>(m, "special-cases.json", signal),
    ]);
    return { stats, windows, points, special };
  });
  const rest = core.then(async ({ points }) => {
    const m = await manifest;
    const [power, repair, labelBuffer, checks] = await Promise.all([
      json<PowerDiagram>(m, "michigan-power-diagram.json", signal),
      json<RepairData>(m, "michigan-repair.json", signal),
      verified(m, "michigan-labels-power.bin", signal),
      json<ExplainerChecks>(m, "michigan-checks.json", signal),
    ]);
    return { power, repair, labels: stageLabels(labelBuffer, repair, points.count), checks };
  });
  return { core, rest };
}

/** Smooth zoom between two views (van Wijk & Nuij), the formulation d3-interpolate uses. */
export function interpolateView(from: [number, number, number], to: [number, number, number], rho = Math.SQRT2) {
  const [ux0, uy0, w0] = from, [ux1, uy1, w1] = to;
  const dx = ux1 - ux0, dy = uy1 - uy0, d2 = dx * dx + dy * dy, rho2 = rho * rho, rho4 = rho2 * rho2;
  const cosh = (x: number) => (Math.exp(x) + Math.exp(-x)) / 2;
  const sinh = (x: number) => (Math.exp(x) - Math.exp(-x)) / 2;
  const tanh = (x: number) => { const e = Math.exp(2 * x); return (e - 1) / (e + 1); };
  if (d2 < 1e-12) {
    const S = Math.log(w1 / w0) / rho;
    return { duration: Math.abs(S) * 1000, at: (t: number): [number, number, number] => [ux0 + t * dx, uy0 + t * dy, w0 * Math.exp(rho * t * S)] };
  }
  const d1 = Math.sqrt(d2);
  const b0 = (w1 * w1 - w0 * w0 + rho4 * d2) / (2 * w0 * rho2 * d1);
  const b1 = (w1 * w1 - w0 * w0 - rho4 * d2) / (2 * w1 * rho2 * d1);
  const r0 = Math.log(Math.sqrt(b0 * b0 + 1) - b0), r1 = Math.log(Math.sqrt(b1 * b1 + 1) - b1);
  const S = (r1 - r0) / rho;
  return {
    duration: S * 1000,
    at: (t: number): [number, number, number] => {
      const s = t * S, u = w0 / (rho2 * d1) * (cosh(r0) * tanh(rho * s + r0) - sinh(r0));
      return [ux0 + u * dx, uy0 + u * dy, w0 * cosh(r0) / cosh(rho * s + r0)];
    },
  };
}
