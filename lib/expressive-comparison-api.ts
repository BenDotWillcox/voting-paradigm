import "server-only";
import { ExpressivePreviewError } from "@/lib/expressive-api";
import { scalarComparisonResponseSchema } from "@/lib/validations/expressive-comparison";
import type { ScalarComparisonRequest, ScalarComparisonResponse } from "@/types/expressive-comparison";

export async function compareScalarBallots(
  request: ScalarComparisonRequest,
): Promise<ScalarComparisonResponse> {
  const baseUrl = process.env.VOTING_API_URL || process.env.NEBULA_API_URL || "http://localhost:8000";
  let response: Response;
  try {
    response = await fetch(`${baseUrl.replace(/\/$/, "")}/api/expressive/scalar/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
  } catch {
    throw new ExpressivePreviewError(503, "The comparison is temporarily unavailable. Your ballots are still here; try again shortly.");
  }
  if (!response.ok) {
    throw new ExpressivePreviewError(
      response.status === 422 ? 422 : 502,
      response.status === 422
        ? "Check your yes/no answer and rate ballot before comparing."
        : "The comparison is temporarily unavailable. Please try again.",
    );
  }
  try {
    return scalarComparisonResponseSchema.parse(await response.json());
  } catch {
    throw new ExpressivePreviewError(502, "The comparison response could not be read. Please try again.");
  }
}
