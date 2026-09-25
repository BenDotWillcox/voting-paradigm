import type { GeometryCollection, Topology } from "topojson-specification";

// TypeScript types mirroring the Python districting package responses.
// Kept narrow on purpose: only what the API actually returns today.
// Step 3+ will add types for district maps, metrics, etc.

/** Apportionment for a single House size, as returned by the API. */
export interface ApportionmentDto {
  /** Total House size that was requested. Echoed for safety. */
  cap: number;
  /** State FIPS (2-char, with leading zeros) -> seats. Sums to `cap`. */
  apportionment: Record<string, number>;
  /** Always 50 in v1. Provided so the UI doesn't have to count keys. */
  total_states: number;
  /** 2020 census apportionment population summed across the 50 states. */
  total_apportionment_population: number;
}

/** A single anchor on the cap slider. */
export interface CapAnchor {
  /** The cap value the anchor sits at. */
  cap: number;
  /** Short label shown on the slider rail. */
  label: string;
  /** One-sentence tooltip explanation. */
  description: string;
}

/** Tract properties in a plan's `tracts.topo.json` display layer. */
export interface TractProperties {
  /** 11-digit census tract GEOID (state + county + tract code). */
  geoid: string;
  district_id: number;
  population: number;
}

/** District properties in a plan's `districts.topo.json` display layer. */
export interface DistrictProperties {
  district_id: number;
  population: number;
}

export type TractTopology = Topology<{
  tracts: GeometryCollection<TractProperties>;
}>;

export type DistrictTopology = Topology<{
  districts: GeometryCollection<DistrictProperties>;
}>;

export interface DistrictPlanCenter {
  district_id: number;
  x: number;
  y: number;
  weight: number;
}

export interface DistrictPlanProjection {
  kind: "state-centered-equirectangular";
  lon0: number;
  lat0: number;
}

/** Provenance of the simplified display geometry for a plan. */
export interface DistrictPlanDisplay {
  artifact_version: number;
  /** SHA-256 of the full-resolution tract topology the display was built from. */
  source_sha256: string;
  /** mapshaper `-simplify` options applied to the shared-arc topology. */
  simplify: string;
  quantization: number;
  tract_count: number;
  district_count: number;
}

/**
 * A cached district plan's metrics and centers (`plan.json`). Geometry is
 * never embedded: fetch the district and tract layers from
 * `districtPlanLayerUrl`.
 */
export interface DistrictPlan {
  type: "KansasDistrictPlan" | "StateDistrictPlan";
  state_fips: string;
  state_name: string;
  source_year: number;
  unit: "tract";
  /** Number of source units (tracts) the plan was solved over. */
  unit_count: number;
  cap: number;
  seats: number;
  target_population: number;
  total_population: number;
  district_populations: Record<string, number>;
  max_population_imbalance: number;
  iterations: number;
  converged: boolean;
  centers?: DistrictPlanCenter[];
  projection?: DistrictPlanProjection;
  notes: string[];
  display: DistrictPlanDisplay;
}
