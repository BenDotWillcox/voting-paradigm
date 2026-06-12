import type { FeatureCollection, Geometry } from "geojson";
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

export interface DistrictPlanFeatureProperties {
  geoid: string;
  name: string;
  population: number;
  district_id: number;
}

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

export type DistrictPlanTopology = Topology<{
  districts: GeometryCollection<DistrictPlanFeatureProperties>;
}>;

export interface CachedDistrictPlan {
  type: "KansasDistrictPlan" | "StateDistrictPlan";
  state_fips: string;
  state_name: string;
  source_year: number;
  unit: "tract";
  /** Number of source units (tracts) the plan was solved over. */
  unit_count?: number;
  /**
   * Granularity of `display_topology` features: per-tract detail or
   * dissolved per-district outlines (the compact summary artifact).
   */
  display_unit?: "tract" | "district";
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
  feature_collection?: FeatureCollection<Geometry, DistrictPlanFeatureProperties>;
  display_topology?: DistrictPlanTopology;
  notes: string[];
}
