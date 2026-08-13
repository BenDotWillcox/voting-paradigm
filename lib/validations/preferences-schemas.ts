/**
 * Zod schemas for the preferences demo's JSONB boundaries.
 *
 * `preference_session.state_snapshot` and `current_question` are JSONB;
 * Drizzle types them as `unknown`. Every read re-validates against these
 * schemas instead of casting, so a corrupted or legacy-shaped snapshot
 * surfaces as an explicit error at the boundary rather than a downstream
 * crash. The shapes mirror the Python wire contract in
 * api/schemas/preferences.py.
 */

import { z } from "zod";

export const evidenceSourceSchema = z.enum([
  "pairwise",
  "slider",
  "free_text_extraction",
  "correction",
  "override",
]);

export const evidenceSchema = z.object({
  source: evidenceSourceSchema,
  item_a: z.string(),
  item_b: z.string(),
  value: z.number().min(-10).max(10),
  event_id: z.string().nullish(),
  confirmed_by_participant: z.literal(false).default(false),
  confidence: z.number().gt(0).max(1).default(1),
  prompt_id: z.string().nullish(),
  raw_response: z.string().nullish(),
  extracted_claims: z.array(z.string()).default([]),
  response_time_ms: z.number().int().nullish(),
  timestamp: z.string().nullish(),
  metadata: z.record(z.unknown()).default({}),
});

const directWireEvidenceSchema = evidenceSchema.refine(
  (evidence) =>
    evidence.source === "pairwise" || evidence.source === "slider",
  "Legacy preference state accepts only pairwise or slider evidence"
);

/** Pre-Evidence snapshots stored a `responses` list; passed through so the
 * Python API can upgrade them (see preferences/serialization.py). */
const legacyResponseSchema = z.object({
  question_id: z.string(),
  chosen_option_id: z.string(),
  strength: z.number().nullish(),
  response_time_ms: z.number().int().nullish(),
  timestamp: z.string().nullish(),
});

export const preferenceStateSchema = z.object({
  user_id: z.string(),
  session_id: z.string(),
  item_ids: z.array(z.string()),
  mu: z.array(z.number()),
  sigma_flat: z.array(z.number()),
  evidence: z.array(directWireEvidenceSchema).nullish(),
  responses: z.array(legacyResponseSchema).nullish(),
  n_questions_asked: z.number().int().nonnegative(),
  asked_question_ids: z.array(z.string()).default([]),
  model_version: z.string(),
});

export const questionOptionSchema = z.object({
  item_id: z.string(),
  text: z.string(),
  description: z.string().nullish(),
});

export const questionSchema = z.object({
  id: z.string(),
  question_type: z.string(),
  prompt: z.string(),
  options: z.array(questionOptionSchema),
  domain: z.string().nullish(),
  source: z.string().default("bank"),
  metadata: z.record(z.unknown()).default({}),
});

export type EvidenceDto = z.infer<typeof evidenceSchema>;
export type PreferenceStateDto = z.infer<typeof preferenceStateSchema>;
export type QuestionDto = z.infer<typeof questionSchema>;
export type QuestionOptionDto = z.infer<typeof questionOptionSchema>;

/** Parse a JSONB state snapshot; throws with a readable message on mismatch. */
export function parsePreferenceState(value: unknown): PreferenceStateDto {
  const parsed = preferenceStateSchema.safeParse(value);
  if (!parsed.success) {
    throw new Error(
      `Invalid preference state snapshot: ${parsed.error.issues
        .map((i) => `${i.path.join(".")}: ${i.message}`)
        .join("; ")}`
    );
  }
  return parsed.data;
}

/** Parse a JSONB question snapshot (nullable column). */
export function parseCurrentQuestion(value: unknown): QuestionDto | null {
  if (value === null || value === undefined) return null;
  const parsed = questionSchema.safeParse(value);
  if (!parsed.success) {
    throw new Error(
      `Invalid current question snapshot: ${parsed.error.issues
        .map((i) => `${i.path.join(".")}: ${i.message}`)
        .join("; ")}`
    );
  }
  return parsed.data;
}
