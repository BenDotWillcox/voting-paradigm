import { geoAlbers, geoConicEqualArea, geoStream, geoTransform } from "d3-geo";
import type { GeoStreamWrapper } from "d3-geo";
import type { FeatureCollection, Geometry } from "geojson";

export type BlockMapProperties = Record<string, unknown>;
export type BlockMapCollection = FeatureCollection<Geometry, BlockMapProperties>;
export interface BlockMapProjection extends GeoStreamWrapper {
  projectPoint: (coordinates: readonly number[]) => [number, number];
}

export const BLOCK_MAP_WIDTH = 1000;
export const BLOCK_MAP_HEIGHT = 620;
export const BLOCK_NATIONAL_HEIGHT = 650;
export const BLOCK_MAP_INSETS = {
  alaska: { x: 16, y: 448, width: 292, height: 180, label: "Alaska · inset" },
  hawaii: { x: 330, y: 512, width: 190, height: 116, label: "Hawaii · inset" },
} as const;

function visitPoints(collection: BlockMapCollection, visitor: (x: number, y: number) => void) {
  geoStream(collection, {
    point: visitor,
    lineStart() {}, lineEnd() {}, polygonStart() {}, polygonEnd() {}, sphere() {},
  });
}

export function blockCoordinateBounds(collection: BlockMapCollection, alaska = false) {
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
  visitPoints(collection, (longitude, latitude) => {
    const x = alaska && longitude > 0 ? longitude - 360 : longitude;
    west = Math.min(west, x); east = Math.max(east, x);
    south = Math.min(south, latitude); north = Math.max(north, latitude);
  });
  return Number.isFinite(west) ? [west, south, east, north] as const : [-1, -1, 1, 1] as const;
}

function fittedPlanarProjection(
  collection: BlockMapCollection,
  base: (point: [number, number]) => [number, number],
  extent: readonly [readonly [number, number], readonly [number, number]],
): BlockMapProjection {
  let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
  visitPoints(collection, (x, y) => {
    const point = base([x, y]);
    left = Math.min(left, point[0]); right = Math.max(right, point[0]);
    top = Math.min(top, point[1]); bottom = Math.max(bottom, point[1]);
  });
  if (!Number.isFinite(left)) [left, top, right, bottom] = [-1, -1, 1, 1];
  const width = extent[1][0] - extent[0][0], height = extent[1][1] - extent[0][1];
  const scale = Math.min(width / Math.max(right - left, 1e-8), height / Math.max(bottom - top, 1e-8));
  const dx = extent[0][0] + (width - (right - left) * scale) / 2 - left * scale;
  const dy = extent[0][1] + (height - (bottom - top) * scale) / 2 - top * scale;
  const projectPoint = (coordinates: readonly number[]): [number, number] => {
    const point = base([coordinates[0], coordinates[1]]);
    return [point[0] * scale + dx, point[1] * scale + dy];
  };
  // Exported Shapely rings use planar GeoJSON winding. Sending them through a
  // spherical d3 stream can select the globe's complement. Project points
  // directly and stream planar rings instead; even-odd fill preserves holes.
  const transform = geoTransform({
    point(x, y) {
      const point = projectPoint([x, y]);
      this.stream.point(point[0], point[1]);
    },
  });
  return { stream: transform.stream.bind(transform), projectPoint };
}

function localBase(collection: BlockMapCollection, stateFips: string) {
  const [west, south, east, north] = blockCoordinateBounds(collection, stateFips === "02");
  if (stateFips === "02") {
    const cosine = Math.cos(61 * Math.PI / 180);
    return ([longitude, latitude]: [number, number]): [number, number] => [
      (longitude > 0 ? longitude - 360 : longitude) * cosine, -latitude,
    ];
  }
  const span = Math.max(north - south, 0.01);
  const projection = geoConicEqualArea()
    .parallels([south + span / 6, north - span / 6])
    .rotate([-(west + east) / 2, 0]).scale(1).translate([0, 0]);
  return (point: [number, number]): [number, number] => projection(point) ?? [0, 0];
}

export function makeStateBlockProjection(
  collection: BlockMapCollection, stateFips: string,
  width = BLOCK_MAP_WIDTH, height = BLOCK_MAP_HEIGHT, padding = 28,
): BlockMapProjection {
  return fittedPlanarProjection(collection, localBase(collection, stateFips), [
    [padding, padding], [width - padding, height - padding],
  ]);
}

export function makeNationalBlockProjection(
  collection: BlockMapCollection, width = BLOCK_MAP_WIDTH, height = BLOCK_NATIONAL_HEIGHT,
) {
  const group = (predicate: (state: string) => boolean): BlockMapCollection => ({
    type: "FeatureCollection",
    features: collection.features.filter((feature) => predicate(String(feature.properties.state_fips))),
  });
  const continental = group((state) => state !== "02" && state !== "15");
  const albers = geoAlbers().scale(1).translate([0, 0]);
  const conus = fittedPlanarProjection(continental, (point) => albers(point) ?? [0, 0], [
    [26, 18], [width - 26, height - 148],
  ]);
  const insetProjection = (state: string, inset: typeof BLOCK_MAP_INSETS.alaska | typeof BLOCK_MAP_INSETS.hawaii) => {
    const data = group((value) => value === state);
    return fittedPlanarProjection(data, localBase(data, state), [
      [inset.x + 12, inset.y + 27], [inset.x + inset.width - 12, inset.y + inset.height - 12],
    ]);
  };
  const alaska = insetProjection("02", BLOCK_MAP_INSETS.alaska);
  const hawaii = insetProjection("15", BLOCK_MAP_INSETS.hawaii);
  return { projectionForState: (state: string) => state === "02" ? alaska : state === "15" ? hawaii : conus };
}

export function blockDistrictColor(district: number, stateFips = "00") {
  const hue = (district * 137.508 + Number(stateFips) * 17) % 360;
  return `hsl(${hue.toFixed(1)} 72% 59%)`;
}

export function formatMapBytes(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MiB` : `${Math.max(1, Math.round(bytes / 1024))} KiB`;
}

export async function fetchBlockCollection(url: string, signal: AbortSignal): Promise<BlockMapCollection> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Map request failed (${response.status}).`);
  const document = await response.json();
  if (document?.type !== "FeatureCollection" || !Array.isArray(document.features)) {
    throw new Error("The requested map is not a feature collection.");
  }
  return document as BlockMapCollection;
}
