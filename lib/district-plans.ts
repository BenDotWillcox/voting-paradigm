/**
 * Shared, isomorphic helpers for cached district plan display artifacts.
 *
 * Artifacts are built by `node scripts/build-district-display.mjs` into
 * `public/data/district-plans/{fips}/cap-{cap}-seats-{seats}/`:
 * `plan.json` (metrics, server-embedded), `districts.topo.json` (small,
 * fetched immediately), and `tracts.topo.json` (fetched lazily).
 */

import type { GeoProjection } from "d3-geo";

import type { DistrictPlan } from "@/types/districting";

export type DistrictPlanLayer = "districts" | "tracts";

export function districtPlanId(cap: number, seats: number): string {
  return `cap-${cap}-seats-${seats}`;
}

export function districtPlanLayerUrl(
  stateFips: string,
  cap: number,
  seats: number,
  layer: DistrictPlanLayer
): string {
  return `/data/district-plans/${stateFips}/${districtPlanId(cap, seats)}/${layer}.topo.json`;
}

/** Deterministic, well-spread district fill (golden-angle hue steps). */
export function districtColor(districtId: number, seats: number): string {
  const hue = (districtId * 137.508) % 360;
  const lightness = seats > 24 ? 0.72 : 0.66;
  const chroma = seats > 24 ? 0.11 : 0.14;
  return `oklch(${lightness} ${chroma} ${hue.toFixed(1)})`;
}

/** "06029004402" -> "Census Tract 44.02"; "26163591900" -> "Census Tract 5919". */
export function tractName(geoid: string): string {
  const code = geoid.slice(5);
  const whole = String(Number.parseInt(code.slice(0, 4), 10));
  const suffix = code.slice(4);
  return `Census Tract ${suffix === "00" ? whole : `${whole}.${suffix}`}`;
}

export interface ProjectedCenter {
  districtId: number;
  weight: number;
  point: [number, number];
}

/**
 * Project the solver's centers (stored in the plan's local equirectangular
 * meters) into the display projection. Rounded to 0.01px because Math.cos
 * can differ in the last float digits between Node and the browser, which
 * would otherwise trip hydration on SSR'd attributes.
 */
export function projectPlanCenters(
  plan: DistrictPlan,
  projection: GeoProjection
): ProjectedCenter[] {
  const meta = plan.projection;
  if (!meta || !plan.centers) return [];
  const centers: ProjectedCenter[] = [];
  for (const center of plan.centers) {
    const point = projection(
      unprojectEquirectangular(center.x, center.y, meta.lon0, meta.lat0)
    );
    if (!point) continue;
    centers.push({
      districtId: center.district_id,
      weight: center.weight,
      point: [roundCoord(point[0]), roundCoord(point[1])],
    });
  }
  return centers;
}

function unprojectEquirectangular(
  x: number,
  y: number,
  lon0: number,
  lat0: number
): [number, number] {
  const earthRadiusM = 6_371_000;
  const lat = lat0 + radiansToDegrees(y / earthRadiusM);
  const lon =
    lon0 + radiansToDegrees(x / (earthRadiusM * Math.cos(degreesToRadians(lat0))));
  return [lon, lat];
}

function degreesToRadians(value: number): number {
  return (value * Math.PI) / 180;
}

function radiansToDegrees(value: number): number {
  return (value * 180) / Math.PI;
}

function roundCoord(value: number): number {
  return Math.round(value * 100) / 100;
}
