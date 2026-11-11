/** A directly authored rate ballot; widths are percentage-point half-value distances. */
export interface ScalarBallotState {
  ideal: number;
  lower_half_width: number;
  upper_half_width: number;
  approval_min: number;
  approval_max: number;
  probe: number;
}

export interface ScalarPreviewResponse {
  model: "clipped-asymmetric-gaussian-v2";
  points: { value: number; unclipped_score: number }[];
  probe: { value: number; score: number; approved: boolean };
}
