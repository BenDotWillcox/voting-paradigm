/**
 * Zod schemas for the methods instrument's Server Action boundary. They
 * mirror the Python request model in api/schemas/voting.py, so a request the
 * action accepts is one the API accepts.
 */

import { z } from "zod";

const MIN_CANDIDATES = 2;
const MAX_CANDIDATES = 5;
const MAX_VOTERS = 10_000;
const UTILITY_SCALE = 100;

const candidateIdSchema = z.string().regex(/^[A-Za-z0-9_-]{1,32}$/);

export const rankedProfileSchema = z
  .object({
    ballot_type: z.literal("ranked"),
    candidates: z.array(candidateIdSchema).min(MIN_CANDIDATES).max(MAX_CANDIDATES),
    rows: z.array(
      z.object({
        count: z.number().int().min(0).max(MAX_VOTERS),
        ranking: z.array(candidateIdSchema).min(1).max(MAX_CANDIDATES),
      })
    ),
  })
  .superRefine((profile, ctx) => {
    const candidates = new Set(profile.candidates);
    if (candidates.size !== profile.candidates.length) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Candidates repeat" });
    }
    profile.rows.forEach((row, index) => {
      const ranked = new Set(row.ranking);
      const complete =
        ranked.size === row.ranking.length &&
        ranked.size === candidates.size &&
        row.ranking.every((id) => candidates.has(id));
      if (!complete) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["rows", index, "ranking"],
          message: "Each ranking must order every candidate exactly once",
        });
      }
    });
    const total = profile.rows.reduce((sum, row) => sum + row.count, 0);
    if (total < 1 || total > MAX_VOTERS) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["rows"],
        message: `A profile needs 1 to ${MAX_VOTERS} voters`,
      });
    }
  });

export const utilityProfileSchema = z
  .object({
    ballot_type: z.literal("utility"),
    candidates: z.array(candidateIdSchema).min(MIN_CANDIDATES).max(MAX_CANDIDATES),
    rows: z.array(
      z.object({
        count: z.number().int().min(0).max(MAX_VOTERS),
        utilities: z.record(candidateIdSchema, z.number().int().min(0).max(UTILITY_SCALE)),
      })
    ),
  })
  .superRefine((profile, ctx) => {
    const candidates = new Set(profile.candidates);
    if (candidates.size !== profile.candidates.length) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Candidates repeat" });
    }
    profile.rows.forEach((row, index) => {
      const keys = Object.keys(row.utilities);
      if (keys.length !== candidates.size || !keys.every((id) => candidates.has(id))) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["rows", index, "utilities"],
          message: "Each voter type needs one utility per candidate",
        });
      }
    });
    const total = profile.rows.reduce((sum, row) => sum + row.count, 0);
    if (total < 1 || total > MAX_VOTERS) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["rows"],
        message: `A profile needs 1 to ${MAX_VOTERS} voters`,
      });
    }
  });

export const profileResolveRequestSchema = z.object({
  profile: z.union([rankedProfileSchema, utilityProfileSchema]),
  tiebreak_seed: z.number().int().min(0).max(2 ** 31 - 1).optional(),
});

// The atlas: three to five single-letter candidates in the unit square, and
// a 64 x 64 grid (api/schemas/atlas.py)
const ATLAS_CELLS = 64 * 64;

export const atlasRequestSchema = z
  .object({
    candidates: z
      .array(
        z.object({
          id: z.string().regex(/^[A-E]$/),
          x: z.number().min(0).max(1),
          y: z.number().min(0).max(1),
        })
      )
      .min(3)
      .max(5),
    tiebreak_seed: z.number().int().min(0).max(2 ** 31 - 1).optional(),
  })
  .refine((request) => new Set(request.candidates.map((c) => c.id)).size === request.candidates.length, {
    message: "Candidates repeat",
  });

export const atlasPointRequestSchema = z.intersection(
  atlasRequestSchema,
  z.object({ cell: z.number().int().min(0).max(ATLAS_CELLS - 1) })
);
