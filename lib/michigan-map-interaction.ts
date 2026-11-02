/** Compatibility exports for the original Michigan audits. */
export * from "./state-map-interaction";
export {
  type StateInspectionTarget as MichiganInspectionTarget,
  stateBlockDetailReady as michiganBlockDetailReady,
  type StateCanvasFrame as MichiganCanvasFrame,
  retainedStateFrameTransform as retainedMichiganFrameTransform,
  projectedStateCountyBounds as projectedMichiganCountyBounds,
  visibleStateCountyFips as visibleMichiganCountyFips,
  visibleStateSpatialChunks as visibleMichiganSpatialChunks,
  type StatePreparedBlockShape as MichiganPreparedBlockShape,
  type StatePreparedCounty as MichiganPreparedCounty,
  prepareStateCounty as prepareMichiganCounty,
  prepareStateCountyAsync as prepareMichiganCountyAsync,
  stateZoomLimits as michiganZoomLimits,
  validateStateSummary as validateMichiganSummary,
  validateStateSpatialIndex as validateMichiganSpatialIndex,
  validateStateSpatialBlocks as validateMichiganSpatialBlocks
} from "./state-map-interaction";
