import type { FeatureCollection, LineString, MultiLineString, MultiPolygon, Polygon } from "geojson";

export type BlockHouseSize = 435 | 574 | 692 | 1000;
export type BlockCoordinateFrame = "source" | "alaska-continuous";
export type BlockBBox = [number, number, number, number];

/** A logical JSON URL; the route negotiates gzip without exposing cache paths. */
export interface BlockAsset {
  url: string;
  bytes: number;
  gzipBytes: number;
  /** SHA-256 of the decoded JSON representation. */
  sha256: string;
}

/** Display-only references shared by all accepted House anchors for a state. */
export interface BlockComparisonLayer {
  asset: BlockAsset;
  label: string;
  description: string;
  sourceUrl: string;
  vintage: string;
  featureCount: number;
}

export type BlockComparisonLayerKind = "density" | "counties" | "congressional";
export type BlockStateComparisonLayers = Record<BlockComparisonLayerKind, BlockComparisonLayer>;

/** A display derivative only; every original plan asset and assignment remains authoritative. */
export interface BlockLandDisplay {
  planId: string;
  state: BlockAsset;
  national: BlockAsset;
  stateOutline?: BlockAsset;
  connections: BlockAsset;
  summary: {
    derivedConnectionCount: number;
    zeroLandPopulation: number;
    zeroLandBlockCount: number;
    method: string;
  };
}

/** Display/navigation derivatives never replace the accepted plan. */
export interface StateExplorerPlanAssets {
  overview: BlockAsset;
  /** Preserved census overview for the coverage toggle; Alaska stays continuous. */
  censusOverview?: BlockAsset;
  coast: BlockAsset;
  dividers: BlockAsset;
  detailDividers: BlockAsset;
  /** Jointly simplified fine coverage, in the accepted plan's coordinate frame. */
  detail?: BlockAsset;
  coverage?: "land-focused" | "census";
  coordinateFrame?: BlockCoordinateFrame;
  summary: BlockAsset;
  /** Optional small-area chunks of whole, unchanged saved census blocks. */
  spatialIndex?: BlockAsset;
}

export interface StateSpatialBlockChunk {
  chunkId: string;
  /** Full source geometry extent, including spanning and water-only blocks. */
  bbox: BlockBBox;
  blockCount: number;
  population: number;
  asset: BlockAsset;
  /** Schema 2 shares geometry across anchors; this sidecar restores district IDs. */
  assignments?: BlockAsset;
}

export interface StateSpatialBlockIndex {
  schemaVersion: 1 | 2;
  planId: string;
  stateFips: string;
  coordinateFrame?: BlockCoordinateFrame;
  totalBlockCount: number;
  totalPopulation: number;
  counties: { fips: string; blockCount: number; population: number }[];
  chunks: StateSpatialBlockChunk[];
}

export interface StateCountyDistrictShare {
  districtId: number;
  population: number;
  blockCount: number;
  /** Share of the county's residents, not area or block count. */
  percent: number;
}

export interface StateExplorerSummary {
  planId: string;
  stateFips: string;
  coordinateFrame?: BlockCoordinateFrame;
  residentPopulation: number;
  blockCount: number;
  counties: {
    fips: string;
    name: string;
    displayName?: string;
    population: number;
    blockCount: number;
    bbox: BlockBBox;
    districtShares: StateCountyDistrictShare[];
  }[];
  districts: {
    districtId: number;
    population: number;
    blockCount: number;
    countyFips: string[];
  }[];
}

export interface StateCityMetadata {
  label: string;
  description: string;
  featureCount: number;
  minimumPopulation: number;
  vintage: string;
  coordinateMeaning: string;
  sources: { url: string; label: string; vintage: string; sha256: string; bytes: number }[];
}

export interface StateExplorerAssets {
  cities: BlockAsset;
  cityMetadata: StateCityMetadata;
  plans: Record<string, StateExplorerPlanAssets>;
}

/** Compatibility names for the original Michigan derivative and its audits. */
export type MichiganExplorerPlanAssets = StateExplorerPlanAssets;
export type MichiganSpatialBlockChunk = StateSpatialBlockChunk;
export type MichiganSpatialBlockIndex = StateSpatialBlockIndex;
export type MichiganCountyDistrictShare = StateCountyDistrictShare;
export type MichiganExplorerSummary = StateExplorerSummary;

export interface BlockPlanOptimizer {
  kind: string | null;
  innerPassCount: number;
  unsuccessfulInnerPassCount: number;
  innerIterationCaps: number;
  maximumInnerIterations: number | null;
  outerIterations: number | null;
  centersConverged: boolean | null;
  outerIterationLimitReached: boolean;
}

export interface BlockPlan {
  id: string;
  stateFips: string;
  stateName: string;
  districtCount: number;
  houseSizes: BlockHouseSize[];
  residentPopulation: number;
  blockCount: number;
  districtPopulations: number[];
  maxDeviationPeople: number;
  maxDeviationPercent: number;
  populationRangePeople: number;
  connectivityPolicy: string;
  strictConnectivity: boolean;
  policyConnectivity: boolean;
  recordedLinkCount: number;
  coordinateFrame: BlockCoordinateFrame;
  bbox: BlockBBox;
  optimizer: BlockPlanOptimizer;
  runtimeScope: string;
  pipelineSeconds: number;
  peakMemoryBytes: number;
  caveats: string[];
  assets: {
    /** Alaska uses wrapped longitudes here; combined national anchors use its working frame. */
    national: BlockAsset;
    state: BlockAsset;
    full: BlockAsset;
    connections?: BlockAsset;
    detailIndex: BlockAsset;
  };
}

export interface BlockPlanAnchor {
  houseSize: BlockHouseSize;
  planIds: string[];
  /** Dissolved district outlines only. Alaska uses an explicitly flagged continuous frame. */
  national: BlockAsset;
}

/** Bundled display-only layers; accepted anchor records remain unchanged. */
export interface BlockNationalLandAssets {
  houseSize: BlockHouseSize;
  planIds: string[];
  outlines: BlockAsset;
  coast: BlockAsset;
  dividers: BlockAsset;
  connections: BlockAsset;
  recordedConnections?: BlockAsset;
}

export interface BlockPlanManifest {
  schemaVersion: 1;
  catalogSha256: string;
  generatedAt: string;
  sourceYear: 2020;
  unit: "census_block";
  houseSizes: BlockHouseSize[];
  anchors: BlockPlanAnchor[];
  /** Display-only state coverage, dissolved before simplification; shared by all anchors. */
  stateOutlines?: BlockAsset;
  comparisonLayers?: Record<string, BlockStateComparisonLayers>;
  landDisplays?: Record<string, BlockLandDisplay>;
  landAnchors?: Record<string, BlockNationalLandAssets>;
  /** National-scale derivatives; state inspection keeps its finer land assets. */
  nationalLandAnchors?: Record<string, BlockNationalLandAssets>;
  stateExplorers?: Record<string, StateExplorerAssets>;
  michiganExplorer?: {
    cities: BlockAsset;
    plans: Record<string, MichiganExplorerPlanAssets>;
  };
  plans: Record<string, BlockPlan>;
}

export interface BlockCountyAsset {
  fips: string;
  blockCount: number;
  population: number;
  /** Optional for Alaska: source exports do not contain county bounding boxes. */
  bbox?: BlockBBox;
  asset: BlockAsset;
}

export interface BlockDetailIndex {
  planId: string;
  bbox: BlockBBox;
  coordinateFrame: BlockCoordinateFrame;
  counties: BlockCountyAsset[];
}

/** Saved district IDs are zero-based in every export. */
export interface BlockDistrictProperties {
  district_id: number;
  population: number;
  block_count: number;
  deviation_people?: number;
  deviation_percent?: number;
}

export interface BlockNationalProperties extends BlockDistrictProperties {
  state_fips: string;
  state_name: string;
  plan_id: string;
  coordinate_frame: BlockCoordinateFrame;
}

/** Standard and Alaska block exports share these fields; additional audit fields may exist. */
export interface CensusBlockProperties {
  geoid: string;
  population: number;
  district_id: number;
  [key: string]: unknown;
}

/** Connection exports retain their historical metadata instead of rewriting large artifacts. */
export interface BlockConnectionProperties {
  id?: string;
  link_id?: string;
  kind?: string;
  connection_kind?: string;
  distance_m?: number;
  district_id?: number;
  [key: string]: unknown;
}

export type BlockDistrictCollection = FeatureCollection<Polygon | MultiPolygon, BlockDistrictProperties>;
export type BlockNationalCollection = FeatureCollection<Polygon | MultiPolygon, BlockNationalProperties>;
export type CensusBlockCollection = FeatureCollection<Polygon | MultiPolygon, CensusBlockProperties>;
export type BlockConnectionCollection = FeatureCollection<LineString | MultiLineString, BlockConnectionProperties>;
