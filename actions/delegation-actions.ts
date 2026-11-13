"use server";

import type { ZodTypeAny, z } from "zod";
import { ActionResult } from "@/types/actions/action-types";
import {
  DelegationApiError,
  getCategoryJudgments,
  getPersonProfile,
  resolveBallotPaper,
  backtestDelegations,
  traceMeasure,
  validateDelegation,
} from "@/lib/delegation-api";
import {
  categoryJudgmentsRequestSchema,
  personIdSchema,
  resolveBallotPaperRequestSchema,
  backtestRequestSchema,
  traceMeasureRequestSchema,
  validateDelegationRequestSchema,
} from "@/lib/validations/delegation-schemas";
import type {
  CategoryJudgmentsResponse,
  DelegationBacktest,
  MeasureTrace,
  PersonProfile,
  ResolveBallotPaperResponse,
  ValidateDelegationResponse,
} from "@/types/delegation";

/**
 * The liquid democracy page keeps the viewer's delegations and votes in the
 * browser. These actions are read only: nothing is stored on this side, so
 * nothing is revalidated.
 */
async function run<Schema extends ZodTypeAny, T>(
  label: string,
  schema: Schema,
  input: unknown,
  request: (parsed: z.infer<Schema>) => Promise<T>,
  context: (parsed: z.infer<Schema>) => Record<string, unknown>
): Promise<ActionResult<T>> {
  const parsed = schema.safeParse(input);
  if (!parsed.success) {
    return { isSuccess: false, message: parsed.error.issues[0]?.message ?? "Invalid request" };
  }
  try {
    const data = await request(parsed.data);
    return { isSuccess: true, message: label, data };
  } catch (error) {
    if (error instanceof DelegationApiError && error.status === 422) {
      // The service said why; its message is written to be shown.
      return { isSuccess: false, message: error.message };
    }
    console.error(`Delegation action failed (${label}):`, { ...context(parsed.data), error });
    return { isSuccess: false, message: "The delegation service is unavailable right now." };
  }
}

/**
 * Check one proposed delegation: a rejection with the loop it would close,
 * or the curated questions on which it would come back to the viewer.
 */
export async function validateDelegationAction(
  input: unknown
): Promise<ActionResult<ValidateDelegationResponse>> {
  return run(
    "Delegation checked",
    validateDelegationRequestSchema,
    input,
    validateDelegation,
    (request) => ({ held: request.viewer_delegations.length })
  );
}

/**
 * A category's judgments for the curated questions. The decision model is
 * asked only when the Python service has live judgments switched on.
 */
export async function getCategoryJudgmentsAction(
  input: unknown
): Promise<ActionResult<CategoryJudgmentsResponse>> {
  return run(
    "Category judged",
    categoryJudgmentsRequestSchema,
    input,
    getCategoryJudgments,
    (request) => ({ held: request.held.length })
  );
}

/** Resolve a ballot paper for the viewer's delegations and votes. */
export async function resolveBallotPaperAction(
  input: unknown
): Promise<ActionResult<ResolveBallotPaperResponse>> {
  return run(
    "Ballot paper resolved",
    resolveBallotPaperRequestSchema,
    input,
    resolveBallotPaper,
    (request) => ({
      ballotPaper: request.ballot_paper,
      held: request.viewer_delegations.length,
      votes: Object.keys(request.viewer_votes).length,
    })
  );
}

/** One person's profile and voting history. */
export async function getPersonProfileAction(
  input: unknown
): Promise<ActionResult<PersonProfile>> {
  return run("Profile loaded", personIdSchema, input, getPersonProfile, () => ({}));
}

/**
 * Route one question, curated or drafted, through the network as it stands
 * with the viewer's delegations, and return the scores and where votes go.
 */
export async function traceMeasureAction(input: unknown): Promise<ActionResult<MeasureTrace>> {
  return run("Measure traced", traceMeasureRequestSchema, input, traceMeasure, (request) => ({
    question: request.question_id ?? "draft",
    delegations: request.viewer_delegations.length,
  }));
}

export async function backtestDelegationsAction(
  input: unknown
): Promise<ActionResult<DelegationBacktest>> {
  return run("Past votes replayed", backtestRequestSchema, input, backtestDelegations, (request) => ({
    before: request.before.length,
    after: request.after.length,
  }));
}
