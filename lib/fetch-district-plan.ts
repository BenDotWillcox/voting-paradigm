import type { DistrictTopology, TractTopology } from "@/types/districting";

import {
  districtPlanLayerUrl,
  type DistrictPlanLayer,
} from "./district-plans";

interface LayerTopology {
  districts: DistrictTopology;
  tracts: TractTopology;
}

// Module-level promise cache so revisiting a state within a session never
// refetches or reparses a layer (on top of HTTP caching).
const layerCache = new Map<string, Promise<unknown>>();

/**
 * Fetch one display layer of a cached district plan from /public.
 * Concurrent and repeat callers share one in-flight promise per URL.
 */
export function fetchDistrictPlanLayer<L extends DistrictPlanLayer>(
  stateFips: string,
  cap: number,
  seats: number,
  layer: L
): Promise<LayerTopology[L]> {
  const url = districtPlanLayerUrl(stateFips, cap, seats, layer);
  const cached = layerCache.get(url);
  if (cached) return cached as Promise<LayerTopology[L]>;

  const request = fetch(url).then(async (response) => {
    if (!response.ok) {
      throw new Error(`Failed to fetch district plan layer ${url}: ${response.status}`);
    }
    return (await response.json()) as LayerTopology[L];
  });
  // Drop failed fetches so a transient error doesn't poison the cache.
  request.catch(() => layerCache.delete(url));
  layerCache.set(url, request);
  return request;
}
