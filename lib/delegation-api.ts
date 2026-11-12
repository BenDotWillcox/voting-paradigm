import "server-only";
import type { z } from "zod";
import { cache } from "react";
import {
  cityResponseSchema,
  categoryJudgmentsResponseSchema,
  profileResponseSchema,
  resolveBallotPaperResponseSchema,
  scenarioResponseSchema,
  validateDelegationResponseSchema,
} from "@/lib/validations/delegation-schemas";
import type {
  CityResults,
  CategoryJudgmentsRequest,
  CategoryJudgmentsResponse,
  DelegationScenario,
  PersonProfile,
  ResolveBallotPaperRequest,
  ResolveBallotPaperResponse,
  ValidateDelegationRequest,
  ValidateDelegationResponse,
} from "@/types/delegation";

/**
 * Typed client for the liquid democracy routes of the Python service.
 *
 * `status` is 422 when the service refused the request and said why (the
 * message is safe to show), 503 when it could not be reached, and 502 when
 * it answered with something this client could not read.
 */
export class DelegationApiError extends Error {
  constructor(
    public readonly status: 422 | 502 | 503,
    message: string
  ) {
    super(message);
    this.name = "DelegationApiError";
  }
}

const UNAVAILABLE = "The delegation service is unavailable right now.";

function baseUrl(): string {
  const url =
    process.env.VOTING_API_URL || process.env.NEBULA_API_URL || "http://localhost:8000";
  return `${url.replace(/\/$/, "")}/api/delegation`;
}

async function refusal(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  } catch {
    // Fall through to the generic message.
  }
  return "The delegation service refused the request.";
}

async function call<Schema extends z.ZodTypeAny>(
  path: string,
  schema: Schema,
  body?: unknown,
  timeoutMs = 15000
): Promise<z.infer<Schema>> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl()}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    throw new DelegationApiError(503, UNAVAILABLE);
  }
  if (response.status === 422) {
    throw new DelegationApiError(422, await refusal(response));
  }
  if (!response.ok) {
    throw new DelegationApiError(502, UNAVAILABLE);
  }
  try {
    return schema.parse(await response.json());
  } catch {
    throw new DelegationApiError(502, "The delegation service's answer could not be read.");
  }
}

/**
 * The synthetic network, the category pool, the ballot papers and the
 * viewer's starting account. Fetched once per page render however many
 * server components ask for it.
 */
export const getDelegationScenario = cache((): Promise<DelegationScenario> => {
  return call("/scenario", scenarioResponseSchema);
});

/** One person's profile, read from the closed ballot papers. */
export function getPersonProfile(personId: string): Promise<PersonProfile> {
  return call(`/people/${encodeURIComponent(personId)}`, profileResponseSchema);
}

/** Run the creation checks on one proposed delegation. */
export function validateDelegation(
  request: ValidateDelegationRequest
): Promise<ValidateDelegationResponse> {
  return call("/delegations/validate", validateDelegationResponseSchema, request);
}

/**
 * A category's judgments for every curated question. When live judgments
 * are switched on this asks the decision model, so it is given longer.
 */
export function getCategoryJudgments(
  request: CategoryJudgmentsRequest
): Promise<CategoryJudgmentsResponse> {
  return call("/judgments", categoryJudgmentsResponseSchema, request, 60000);
}

/** Resolve every question on a ballot paper for the viewer's delegations and votes. */
export function resolveBallotPaper(
  request: ResolveBallotPaperRequest
): Promise<ResolveBallotPaperResponse> {
  return call("/resolve", resolveBallotPaperResponseSchema, request);
}

/** Every closed question across the city: turnout, delegation and results. */
export function getCityResults(): Promise<CityResults> {
  return call("/city", cityResponseSchema);
}
