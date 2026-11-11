import { z } from "zod";

const rate = z.number().finite().min(0).max(100);
const halfWidth = z.number().finite().positive().max(100);
const score = z.number().finite().min(0).max(1);

export const scalarPreviewRequestSchema = z.object({
  ideal: rate,
  lower_half_width: halfWidth,
  upper_half_width: halfWidth,
  approval_min: rate,
  approval_max: rate,
  probe: rate,
}).strict().superRefine((ballot, context) => {
  if (ballot.approval_min > ballot.ideal || ballot.ideal > ballot.approval_max) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["ideal"],
      message: "Keep your preferred rate inside the approval band.",
    });
  }
});

export const scalarPreviewResponseSchema = z.object({
  model: z.literal("clipped-asymmetric-gaussian-v2"),
  points: z.array(z.object({ value: rate, unclipped_score: score }).strict()).min(2001).max(2007),
  probe: z.object({ value: rate, score, approved: z.boolean() }).strict(),
}).strict();
