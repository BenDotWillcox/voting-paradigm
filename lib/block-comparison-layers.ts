import type { BlockComparisonLayer, BlockComparisonLayerKind } from "@/types/block-districting";
import { fetchBlockCollection } from "@/lib/block-map-projection";
import type { BlockMapCollection } from "@/lib/block-map-projection";

/** Fixed bins make the same density mean the same color in every state. */
export const DENSITY_BINS = [
  { maximum: 0, label: "0", color: "#18243a" },
  { maximum: 10, label: "0–10", color: "#433e85" },
  { maximum: 100, label: "10–100", color: "#31688e" },
  { maximum: 1000, label: "100–1,000", color: "#21918c" },
  { maximum: 10000, label: "1,000–10,000", color: "#6ece58" },
  { maximum: Infinity, label: "10,000+", color: "#fde725" },
] as const;
export const DENSITY_NO_LAND_COLOR = "#94a3b8";

export function densityColor(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return DENSITY_NO_LAND_COLOR;
  return DENSITY_BINS.find((bin) => value <= bin.maximum)!.color;
}

export function comparisonLayerKey(stateFips: string, kind: BlockComparisonLayerKind, layer: BlockComparisonLayer) {
  return `${stateFips}:${kind}:${layer.asset.url}`;
}

/** Fail closed if a reference from another state or a malformed density arrives. */
export function validateComparisonCollection(
  data: BlockMapCollection, stateFips: string, kind: BlockComparisonLayerKind, expectedCount: number,
): BlockMapCollection {
  if (data.features.length !== expectedCount) throw new Error("Comparison layer feature count does not match its manifest.");
  const seen = new Set<string>();
  for (const feature of data.features) {
    const props = feature.properties;
    const geoid = props?.geoid;
    if (typeof geoid !== "string" || !geoid.startsWith(stateFips) || seen.has(geoid)
      || !feature.geometry || !["Polygon", "MultiPolygon"].includes(feature.geometry.type)) {
      throw new Error("Comparison layer contains an invalid or duplicate state geography.");
    }
    seen.add(geoid);
    if (kind === "density") {
      const { population, landAreaM2, densityPerKm2 } = props;
      if (typeof population !== "number" || !Number.isSafeInteger(population) || population < 0
        || typeof landAreaM2 !== "number" || !Number.isFinite(landAreaM2) || landAreaM2 < 0
        || (landAreaM2 === 0 ? densityPerKm2 !== null
          : typeof densityPerKm2 !== "number" || !Number.isFinite(densityPerKm2) || densityPerKm2 < 0)) {
        throw new Error("Comparison layer contains invalid population-density values.");
      }
    }
  }
  return data;
}

/** Bounded decoded-payload cache: shared across anchors, never across identities. */
export class ComparisonLayerCache {
  private entries = new Map<string, { data: BlockMapCollection; bytes: number }>();
  private bytes = 0;
  constructor(private readonly maxEntries = 6, private readonly maxBytes = 24 * 1024 * 1024) {}
  get(key: string) {
    const value = this.entries.get(key);
    if (!value) return null;
    this.entries.delete(key);
    this.entries.set(key, value);
    return value.data;
  }
  put(key: string, data: BlockMapCollection, bytes: number) {
    const previous = this.entries.get(key);
    if (previous) { this.bytes -= previous.bytes; this.entries.delete(key); }
    if (!Number.isFinite(bytes) || bytes < 0 || bytes > this.maxBytes || this.maxEntries < 1) return;
    this.entries.set(key, { data, bytes });
    this.bytes += bytes;
    while (this.entries.size > this.maxEntries || this.bytes > this.maxBytes) {
      const oldest = this.entries.entries().next().value!;
      this.entries.delete(oldest[0]); this.bytes -= oldest[1].bytes;
    }
  }
}

const comparisonCache = new ComparisonLayerCache();

export async function loadComparisonLayer(
  stateFips: string, kind: BlockComparisonLayerKind, layer: BlockComparisonLayer, signal: AbortSignal,
) {
  signal.throwIfAborted();
  const key = comparisonLayerKey(stateFips, kind, layer);
  const cached = comparisonCache.get(key);
  if (cached) return cached;
  const data = validateComparisonCollection(
    await fetchBlockCollection(layer.asset.url, signal), stateFips, kind, layer.featureCount,
  );
  signal.throwIfAborted();
  comparisonCache.put(key, data, layer.asset.bytes);
  return data;
}
