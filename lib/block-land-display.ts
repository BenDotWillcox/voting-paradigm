import type { BlockLandDisplay, BlockPlan } from "@/types/block-districting";
import type { BlockMapCollection, BlockMapProperties } from "@/lib/block-map-projection";
import { fetchBlockCollection } from "@/lib/block-map-projection";
import type { Feature, Geometry, LineString, MultiLineString } from "geojson";

export interface DerivedWaterProperties extends BlockMapProperties {
  id: string;
  kind: "derived-water-adjacency";
  district_id: number;
  block_path: string[];
  water_block_count: number;
  endpoints: { geoid: string; coordinate: [number, number] }[];
  distance_m?: number;
  derivation_schema_version?: 1 | 2;
  schematic?: boolean;
  source_part_path?: { geoid: string; source_polygon_part: number; water_only: boolean }[];
  land_component_ids?: (number | null)[];
}

export type DerivedWaterFeature = Feature<LineString, DerivedWaterProperties>;

/** Stroke only: retain every polygon/island exterior without outlining interior lakes.
 * Fills, clipping and hit testing must continue to use the original full geometry.
 */
export function polygonExteriorStrokeGeometry(geometry: Geometry | null): MultiLineString | null {
  const polygons = geometry?.type === "Polygon" ? [geometry.coordinates]
    : geometry?.type === "MultiPolygon" ? geometry.coordinates : null;
  if (!polygons) return null;
  return {
    type: "MultiLineString",
    coordinates: polygons.flatMap((polygon) => polygon[0] ? [polygon[0].map((point) => [...point])] : []),
  };
}

/** A mismatched derivative must never replace the selected authoritative plan. */
export function matchingLandDisplay(plan: BlockPlan, display?: BlockLandDisplay) {
  return display?.planId === plan.id ? display : undefined;
}

/** Detailed inspection must use the finer polygon coverage, including for clip/fill/hit testing. */
export function needsFineBlockDisplay(manualDetail: boolean, focus: "state" | "county" | "connection" | "derived", hasCountyBlocks: boolean) {
  return manualDetail || focus !== "state" || hasCountyBlocks;
}

export function selectBlockDisplayAsset(plan: BlockPlan, display: BlockLandDisplay | undefined, fullExtent: boolean, exact: boolean, fineDetail = false) {
  const available = matchingLandDisplay(plan, display);
  const landFocused = !!available && !fullExtent;
  return {
    landFocused,
    asset: landFocused ? (fineDetail ? available.state : available.national) : exact ? plan.assets.full : plan.assets.state,
  };
}

/** These lines explain saved water-block paths, never additional policy edges. */
export function validateDerivedConnections(data: BlockMapCollection, plan: BlockPlan, expectedCount: number): DerivedWaterFeature[] {
  const metadata = (data as BlockMapCollection & { metadata?: { planId?: string } }).metadata;
  if (metadata?.planId !== plan.id || data.features.length !== expectedCount) {
    throw new Error("Derived connections do not match the selected plan.");
  }
  const ids = new Set<string>();
  const point = (value: unknown): value is [number, number] => Array.isArray(value) && value.length === 2
    && value.every((coordinate) => typeof coordinate === "number" && Number.isFinite(coordinate));
  const result: DerivedWaterFeature[] = [];
  for (const feature of data.features) {
    const props = feature.properties;
    const path = props?.block_path;
    const endpoints = props?.endpoints as Record<string, unknown>[] | undefined;
    if (!props || props.kind !== "derived-water-adjacency" || typeof props.id !== "string" || !props.id || ids.has(props.id)
      || !Number.isInteger(props.district_id) || Number(props.district_id) < 0 || Number(props.district_id) >= plan.districtCount
      || !Array.isArray(path) || path.length < 1 || path.some((geoid) => typeof geoid !== "string" || !/^\d{15}$/.test(geoid) || !geoid.startsWith(plan.stateFips))
      || !Number.isInteger(props.water_block_count) || Number(props.water_block_count) < 0
      || !Array.isArray(endpoints) || endpoints.length !== 2 || endpoints.some((endpoint) => !endpoint || !point(endpoint.coordinate))
      || endpoints[0].geoid !== path[0] || endpoints[1].geoid !== path[path.length - 1]
      || feature.geometry?.type !== "LineString" || feature.geometry.coordinates.length < 2
      || feature.geometry.coordinates.some((coordinate) => !point(coordinate))) {
      throw new Error("A derived water connection has invalid path or district evidence.");
    }
    if (props.derivation_schema_version === 2) {
      const parts = props.source_part_path as Record<string, unknown>[] | undefined;
      const components = props.land_component_ids;
      const integer = (value: unknown) => typeof value === "number" && Number.isInteger(value) && value >= 0;
      if (props.schematic !== true || Number(props.water_block_count) < 1 || !Array.isArray(parts) || parts.length !== path.length
        || parts.some((part, i) => !part || part.geoid !== path[i] || !integer(part.source_polygon_part) || typeof part.water_only !== "boolean")
        || parts.filter((part) => part.water_only).length !== props.water_block_count
        || !Array.isArray(components) || components.length !== 2
        || components.some((component) => component !== null && !integer(component))) {
        throw new Error("A derived water connection has invalid source-part evidence.");
      }
      for (let i = 0; i < 2; i++) {
        const endpoint = endpoints[i], part = parts[i === 0 ? 0 : parts.length - 1];
        if (!integer(endpoint.source_polygon_part) || endpoint.source_polygon_part !== part.source_polygon_part) {
          throw new Error("A derived water connection endpoint does not match its source part.");
        }
        if (endpoint.kind === "land-component") {
          if (part.water_only || !integer(endpoint.land_component_id) || components[i] !== endpoint.land_component_id
            || endpoint.recorded_link_id !== undefined || endpoint.recorded_endpoint_index !== undefined) {
            throw new Error("A derived water connection has invalid land-component evidence.");
          }
        } else if (endpoint.kind === "recorded-connection-endpoint") {
          if (!Number.isInteger(plan.recordedLinkCount) || plan.recordedLinkCount < 1 || !part.water_only || components[i] !== null || endpoint.land_component_id !== undefined
            || typeof endpoint.recorded_link_id !== "string" || !endpoint.recorded_link_id
            || ![0, 1].includes(Number(endpoint.recorded_endpoint_index)) || !Number.isInteger(endpoint.recorded_endpoint_index)) {
            throw new Error("A derived water connection has invalid recorded-endpoint evidence.");
          }
        } else {
          throw new Error("A derived water connection has an unknown endpoint kind.");
        }
      }
    } else if ((props.derivation_schema_version !== undefined && props.derivation_schema_version !== 1)
      || path.length < 3 || props.water_block_count !== path.length - 2) {
      throw new Error("A derived water connection has invalid path or district evidence.");
    }
    const first = feature.geometry.coordinates[0], last = feature.geometry.coordinates[feature.geometry.coordinates.length - 1];
    const start = endpoints[0].coordinate as [number, number], end = endpoints[1].coordinate as [number, number];
    if (first[0] !== start[0] || first[1] !== start[1] || last[0] !== end[0] || last[1] !== end[1]) {
      throw new Error("A derived water connection does not match its endpoint coordinates.");
    }
    ids.add(props.id);
    result.push(feature as DerivedWaterFeature);
  }
  return result;
}

export async function loadDerivedConnections(plan: BlockPlan, display: BlockLandDisplay, signal: AbortSignal) {
  signal.throwIfAborted();
  if (!matchingLandDisplay(plan, display)) throw new Error("Derived connections do not match the selected plan.");
  const data = await fetchBlockCollection(display.connections.url, signal);
  signal.throwIfAborted();
  return validateDerivedConnections(data, plan, display.summary.derivedConnectionCount);
}
