/** Public self-report boundary; mirrors the Python spectrum records. */
import { z } from "zod";

export const SPECTRUM_BANK_VERSION = "spectrum_demo_v1" as const;
export const SPECTRUM_SD_MIN = 0.08;
export const SPECTRUM_SD_MAX = 0.28;
const questionId = z.string().min(1).max(100);
const finite = z.number().finite();
export const reportedUncertaintySchema = z.object({
  sd_fraction: finite.min(SPECTRUM_SD_MIN).max(SPECTRUM_SD_MAX),
}).strict();
export const acceptableRangeSchema = z.object({ lower: finite, upper: finite })
  .strict().refine((range) => range.lower <= range.upper, "Range endpoints must be ordered");

export const elicitationEventSchema = z.discriminatedUnion("action", [
  z.object({
    action: z.literal("answer"), question_id: questionId, question_version: z.literal(1),
    position: finite,
    reported_uncertainty: reportedUncertaintySchema.nullable().default(null),
    acceptable_range: acceptableRangeSchema.nullable().default(null),
  }).strict(),
  z.object({ action: z.literal("skip"), question_id: questionId, question_version: z.literal(1) }).strict(),
  z.object({ action: z.literal("depends"), question_id: questionId, question_version: z.literal(1) }).strict(),
]);

export const elicitationRequestSchema = z.object({
  bank_version: z.literal(SPECTRUM_BANK_VERSION),
  responses: z.array(elicitationEventSchema).max(4).default([]),
}).strict();

const scaleSchema = z.object({
  min: finite, max: finite, step: finite.positive(), unit: z.string().min(1),
  format: z.enum(["number", "clock_hour"]),
  anchors: z.array(z.object({ value: finite, label: z.string().min(1) }).strict()).min(2),
}).strict().superRefine((scale, ctx) => {
  if (scale.min >= scale.max ||
    scale.anchors[0]?.value !== scale.min || scale.anchors.at(-1)?.value !== scale.max ||
    scale.anchors.some((anchor, index) => !isScaleValue(anchor.value, scale) ||
      (index > 0 && anchor.value <= scale.anchors[index - 1].value))) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Invalid spectrum scale" });
  }
});

export const spectrumQuestionSchema = z.object({
  id: questionId, version: z.literal(1), title: z.string().min(1),
  prompt: z.string().min(1), context: z.string().min(1), scale: scaleSchema,
}).strict();

export type ReportedUncertainty = z.infer<typeof reportedUncertaintySchema>;
export type AcceptableRange = z.infer<typeof acceptableRangeSchema>;
export type SpectrumQuestion = z.infer<typeof spectrumQuestionSchema>;
export type ElicitationEvent = z.infer<typeof elicitationEventSchema>;

export function isScaleValue(value: number, scale: { min: number; max: number; step: number }): boolean {
  if (![value, scale.min, scale.max, scale.step].every(Number.isFinite) ||
    scale.step <= 0 || value < scale.min || value > scale.max) return false;
  // Match Python's Decimal(str(value)) grid: 0.3 is on a 0.1 grid, but
  // 0.30000000000000004 is not. Float division cannot distinguish them safely.
  const decimals = [value, scale.min, scale.step].map((number) => {
    const [mantissa, exponent = "0"] = number.toString().split("e");
    const fractionLength = mantissa.split(".")[1]?.length ?? 0;
    return { coefficient: BigInt(mantissa.replace(".", "")), exponent: Number(exponent) - fractionLength };
  });
  const commonExponent = Math.min(...decimals.map((decimal) => decimal.exponent));
  const [point, lower, step] = decimals.map((decimal) =>
    decimal.coefficient * BigInt(10) ** BigInt(decimal.exponent - commonExponent));
  return (point - lower) % step === BigInt(0);
}

export function spectrumEventMatchesQuestion(event: ElicitationEvent, question: SpectrumQuestion): boolean {
  return event.question_id === question.id && event.question_version === question.version &&
    (event.action !== "answer" || (isScaleValue(event.position, question.scale) &&
      (event.acceptable_range === null || (
        isScaleValue(event.acceptable_range.lower, question.scale) &&
        isScaleValue(event.acceptable_range.upper, question.scale)
      ))));
}

const count = z.number().int().min(0).max(4);
export const elicitationResponseSchema = z.object({
  bank_version: z.literal(SPECTRUM_BANK_VERSION),
  questions: z.array(spectrumQuestionSchema).length(4),
  responses: z.array(elicitationEventSchema).max(4),
  n_reviewed: count, n_answered: count, n_skipped: count, n_depends: count,
  target_questions: z.literal(4), is_complete: z.boolean(),
}).strict().superRefine((response, ctx) => {
  if (new Set(response.questions.map((question) => question.id)).size !== 4 ||
    response.n_reviewed !== response.responses.length ||
    response.n_answered !== response.responses.filter((event) => event.action === "answer").length ||
    response.n_skipped !== response.responses.filter((event) => event.action === "skip").length ||
    response.n_depends !== response.responses.filter((event) => event.action === "depends").length ||
    response.is_complete !== (response.n_reviewed === response.target_questions) ||
    response.responses.some((event, index) => !response.questions[index] ||
      !spectrumEventMatchesQuestion(event, response.questions[index]))) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Inconsistent spectrum session" });
  }
});

export type ElicitationResponse = z.infer<typeof elicitationResponseSchema>;
