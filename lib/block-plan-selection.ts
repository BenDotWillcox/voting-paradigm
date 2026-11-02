import type { BlockHouseSize, BlockPlan, BlockPlanManifest } from "@/types/block-districting";

export const BLOCK_HOUSE_SIZES = [435, 574, 692, 1000] as const;

export function isBlockHouseSize(value: number): value is BlockHouseSize {
  return BLOCK_HOUSE_SIZES.some((anchor) => anchor === value);
}

/** Unsupported values never masquerade as computed intermediate plans. */
export function blockHouseSize(value: string | number | null | undefined): BlockHouseSize {
  const number = value === null || value === undefined || value === "" ? 435 : Number(value);
  return isBlockHouseSize(number) ? number : 435;
}

export function blockPlanAt(manifest: BlockPlanManifest, houseSize: BlockHouseSize, stateFips: string | null): BlockPlan | null {
  if (!stateFips) return null;
  const anchor = manifest.anchors.find((item) => item.houseSize === houseSize);
  const id = anchor?.planIds.find((planId) => manifest.plans[planId]?.stateFips === stateFips);
  return id ? manifest.plans[id] ?? null : null;
}

export function blockPlanUrl(houseSize: BlockHouseSize, stateFips: string | null = null): string {
  const params = new URLSearchParams({ cap: String(houseSize) });
  if (stateFips) params.set("state", stateFips);
  return `/districts?${params.toString()}`;
}

/**
 * The files the national map requests for its opening view at a House size:
 * its districts, the state outlines and the land-focused layers
 * (components/districting/block-national-map.tsx). The districts page fetches
 * them in the background so the explorer opens from the HTTP cache.
 */
export function nationalOverviewUrls(manifest: BlockPlanManifest, houseSize: BlockHouseSize): string[] {
  const anchor = manifest.anchors.find((item) => item.houseSize === houseSize);
  const land = manifest.nationalLandAnchors?.[String(houseSize)] ?? manifest.landAnchors?.[String(houseSize)];
  return [
    anchor?.national.url, manifest.stateOutlines?.url,
    land?.outlines.url, land?.coast.url, land?.dividers.url, land?.connections.url, land?.recordedConnections?.url,
  ].filter((url): url is string => Boolean(url));
}
