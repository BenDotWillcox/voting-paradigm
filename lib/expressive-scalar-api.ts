/** Python owns utility evaluation; the browser renders its sampled curve. */
import "server-only";
import { ExpressivePreviewError } from "@/lib/expressive-api";
import { scalarPreviewResponseSchema } from "@/lib/validations/expressive-scalar";
import type { ScalarBallotState, ScalarPreviewResponse } from "@/types/expressive-scalar";

export async function previewScalarBallot(ballot: ScalarBallotState): Promise<ScalarPreviewResponse> {
  const baseUrl = process.env.VOTING_API_URL || process.env.NEBULA_API_URL || "http://localhost:8000";
  let response: Response;
  try {
    response = await fetch(`${baseUrl.replace(/\/$/, "")}/api/expressive/scalar/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ballot),
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
  } catch {
    throw new ExpressivePreviewError(503, "Curve evaluation is temporarily unavailable. Your settings are still here; try again shortly.");
  }
  if (!response.ok) {
    throw new ExpressivePreviewError(
      response.status === 422 ? 422 : 502,
      response.status === 422
        ? "Check that your preferred rate is inside the approval band and both taper widths are positive."
        : "Curve evaluation is temporarily unavailable. Please try again.",
    );
  }
  try {
    return scalarPreviewResponseSchema.parse(await response.json());
  } catch {
    throw new ExpressivePreviewError(502, "The curve response could not be read. Please try again.");
  }
}
