import { geoPath } from "d3-geo";
import type { BlockMapCollection } from "@/lib/block-map-projection";
import { BLOCK_MAP_WIDTH, BLOCK_NATIONAL_HEIGHT, blockDistrictColor, makeNationalBlockProjection } from "@/lib/block-map-projection";
import type { NationalLandState } from "@/lib/block-national-land-display";
import type { BlockAsset, BlockPlan } from "@/types/block-districting";

export interface NationalDistrictPath { id: number; d: string; fill: string }
export interface NationalStatePaths {
  fips: string;
  name: string;
  districts: NationalDistrictPath[];
  landFocused: boolean;
}
export interface NationalPreparedMap {
  states: NationalStatePaths[];
  borders: { fips: string; d: string }[];
  meshes: { state: string; dividers: string; water: string }[];
  derived: { state: string; count: number; d: string }[];
  recorded: { id: string; state: string; kind: "water" | "exclave"; d: string }[];
  estimatedBytes: number;
  pathCount: number;
}

/** No source geometry is retained: this view is just immutable SVG path strings. */
export function prepareNationalMap(
  data: BlockMapCollection,
  boundaries?: BlockMapCollection,
  land?: ReadonlyMap<string, NationalLandState>,
): NationalPreparedMap {
  const { projectionForState } = makeNationalBlockProjection(data);
  const groups = new Map<string, NationalStatePaths>();
  const pathFor = new Map<string, ReturnType<typeof geoPath>>();
  const draw = (state: string, geometry: Parameters<ReturnType<typeof geoPath>>[0]) => {
    const path = pathFor.get(state) ?? geoPath(projectionForState(state));
    pathFor.set(state, path);
    return path(geometry) ?? "";
  };
  for (const feature of data.features) {
    const fips = String(feature.properties.state_fips);
    const group = groups.get(fips) ?? { fips, name: String(feature.properties.state_name), districts: [], landFocused: !!land?.has(fips) };
    const id = Number(feature.properties.district_id);
    group.districts.push({ id, d: draw(fips, feature), fill: blockDistrictColor(id, fips) });
    groups.set(fips, group);
  }
  const states = [...groups.values()].sort((a, b) => a.name.localeCompare(b.name));
  const borders = boundaries?.features.map((feature) => {
    const fips = String(feature.properties.state_fips);
    return { fips, d: draw(fips, land?.get(fips)?.exteriorCoast ?? feature) };
  }) ?? [];
  const meshes: NationalPreparedMap["meshes"] = [];
  const derived: NationalPreparedMap["derived"] = [];
  const recorded: NationalPreparedMap["recorded"] = [];
  for (const [state, value] of land ?? []) {
    meshes.push({ state, dividers: draw(state, value.dividers), water: draw(state, value.interiorWater) });
    if (value.connections.features.length) derived.push({ state, count: value.connections.features.length, d: draw(state, value.connections) });
    for (const [i, feature] of value.recordedConnections.features.entries()) recorded.push({
      id: `${state}:${String(feature.properties.id ?? feature.id ?? i)}`, state,
      kind: String(feature.properties.kind ?? "water").includes("exclave") ? "exclave" : "water", d: draw(state, feature),
    });
  }
  const strings = [
    ...states.flatMap((state) => state.districts.map((district) => district.d)), ...borders.map((border) => border.d),
    ...meshes.flatMap((mesh) => [mesh.dividers, mesh.water]), ...derived.map((connection) => connection.d), ...recorded.map((connection) => connection.d),
  ];
  if (strings.some((value) => /NaN|Infinity/.test(value))) throw new Error("National map projection contains invalid coordinates.");
  const pathCount = strings.length;
  // Conservative UTF-16 path storage plus per-path/state bookkeeping. This is
  // a bounded cache estimate, not a browser heap measurement.
  const estimatedBytes = strings.reduce((bytes, value) => bytes + value.length * 2 + 128, 0) + states.length * 256;
  return { states, borders, meshes, derived, recorded, pathCount, estimatedBytes };
}

export function nationalPreparedKey(
  houseSize: number, mode: "land" | "census", assets: readonly (BlockAsset | undefined)[], plans: readonly BlockPlan[],
) {
  return JSON.stringify(["national-svg-v1", BLOCK_MAP_WIDTH, BLOCK_NATIONAL_HEIGHT, houseSize, mode,
    assets.map((asset) => asset ? [asset.url, asset.sha256] : null),
    plans.map((plan) => [plan.id, plan.stateFips, plan.coordinateFrame])]);
}

export const NATIONAL_PREPARED_MAX_ENTRIES = 2;
export const NATIONAL_PREPARED_MAX_BYTES = 64 * 1024 * 1024;

/** Successful complete preparations only; eviction releases all path references. */
export class NationalPreparedCache {
  private entries = new Map<string, NationalPreparedMap>();
  private bytes = 0;
  constructor(private maxEntries = NATIONAL_PREPARED_MAX_ENTRIES, private maxBytes = NATIONAL_PREPARED_MAX_BYTES) {}
  getOrPrepare(key: string, factory: () => NationalPreparedMap): { map: NationalPreparedMap; cacheHit: boolean } {
    const cached = this.entries.get(key);
    if (cached) {
      this.entries.delete(key);
      this.entries.set(key, cached);
      return { map: cached, cacheHit: true };
    }
    const map = factory(); // A thrown/failed preparation never enters the cache.
    if (Number.isSafeInteger(map.estimatedBytes) && map.estimatedBytes >= 0 && map.estimatedBytes <= this.maxBytes && this.maxEntries > 0) {
      while (this.entries.size >= this.maxEntries || this.bytes + map.estimatedBytes > this.maxBytes) {
        const oldest = this.entries.keys().next().value;
        if (oldest === undefined) break;
        this.bytes -= this.entries.get(oldest)!.estimatedBytes;
        this.entries.delete(oldest);
      }
      this.entries.set(key, map);
      this.bytes += map.estimatedBytes;
    }
    return { map, cacheHit: false };
  }
  snapshot() { return { entries: this.entries.size, estimatedBytes: this.bytes, keys: [...this.entries.keys()] }; }
}

const preparedCache = new NationalPreparedCache();
export const getPreparedNationalMap = (key: string, factory: () => NationalPreparedMap) => preparedCache.getOrPrepare(key, factory);
