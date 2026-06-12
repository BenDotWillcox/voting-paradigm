import type { CachedDistrictPlan } from "@/types/districting";

// Module-level promise cache so revisiting a state within a session never
// refetches or reparses the multi-MB tract topo (on top of HTTP caching).
const planCache = new Map<string, Promise<CachedDistrictPlan>>();

/**
 * Fetch a display plan artifact (tract topo or summary) from /public.
 * Concurrent and repeat callers share one in-flight promise per URL.
 */
export function fetchDistrictPlan(url: string): Promise<CachedDistrictPlan> {
  const cached = planCache.get(url);
  if (cached) return cached;

  const request = fetch(url).then(async (response) => {
    if (!response.ok) {
      throw new Error(`Failed to fetch district plan ${url}: ${response.status}`);
    }
    return (await response.json()) as CachedDistrictPlan;
  });
  // Drop failed fetches so a transient error doesn't poison the cache.
  request.catch(() => planCache.delete(url));
  planCache.set(url, request);
  return request;
}
