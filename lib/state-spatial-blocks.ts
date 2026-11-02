import type { BlockPlan, StateSpatialBlockChunk } from "@/types/block-districting";
import { fetchBlockCollection } from "@/lib/block-map-projection";
import type { BlockMapCollection } from "@/lib/block-map-projection";
import { validateStateSpatialBlocks } from "@/lib/state-map-interaction";

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid block assignment metadata.");
  return value as Record<string, unknown>;
}

/** Restore each saved district ID without copying or changing shared geometry. */
export function restoreStateSpatialAssignments(geometry: BlockMapCollection, assignmentValue: unknown, plan: BlockPlan, chunk: StateSpatialBlockChunk): BlockMapCollection {
  const metadata = record((geometry as BlockMapCollection & { metadata?: unknown }).metadata);
  const assignments = record(assignmentValue);
  if (metadata.schemaVersion !== 2 || metadata.stateFips !== plan.stateFips || metadata.coordinateFrame !== plan.coordinateFrame
    || metadata.chunkId !== chunk.chunkId || metadata.sharedAcrossPlans !== true || metadata.wholeSavedBlocks !== true || metadata.assignmentField !== "district_id"
    || assignments.schemaVersion !== 1 || assignments.planId !== plan.id || assignments.stateFips !== plan.stateFips
    || assignments.coordinateFrame !== plan.coordinateFrame || assignments.chunkId !== chunk.chunkId || assignments.geometrySha256 !== chunk.asset.sha256
    || !Array.isArray(assignments.districtIds) || assignments.districtIds.length !== geometry.features.length
    || geometry.features.length !== chunk.blockCount) throw new Error("Shared block geometry and saved assignments do not match this plan.");
  const ids = assignments.districtIds;
  const features = geometry.features.map((feature, i) => {
    const district = ids[i];
    if (!Number.isInteger(district) || district < 0 || district >= plan.districtCount || Object.hasOwn(feature.properties, "district_id")) throw new Error("Invalid saved district assignment.");
    return { ...feature, properties: { ...feature.properties, district_id: district } };
  });
  return validateStateSpatialBlocks({ type: "FeatureCollection", features }, plan, chunk);
}

export async function loadStateSpatialBlocks(plan: BlockPlan, chunk: StateSpatialBlockChunk, signal: AbortSignal): Promise<BlockMapCollection> {
  if (!chunk.assignments) return validateStateSpatialBlocks(await fetchBlockCollection(chunk.asset.url, signal), plan, chunk);
  const [geometry, assignments] = await Promise.all([
    fetchBlockCollection(chunk.asset.url, signal),
    fetch(chunk.assignments.url, { signal }).then(async (response) => {
      if (!response.ok) throw new Error(`Saved assignments request failed (${response.status}).`);
      return response.json() as Promise<unknown>;
    }),
  ]);
  if (signal.aborted) throw new DOMException("Spatial block request was canceled.", "AbortError");
  return restoreStateSpatialAssignments(geometry, assignments, plan, chunk);
}
