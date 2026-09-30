import type { ElicitationEvent } from "@/lib/validations/elicitation-schemas";

/** Replace a reviewed answer or append the next one, without losing later answers. */
export function replaceReviewedResponse(
  responses: readonly ElicitationEvent[],
  questionIndex: number,
  event: ElicitationEvent,
): ElicitationEvent[] {
  if (!Number.isInteger(questionIndex) || questionIndex < 0 || questionIndex > responses.length) {
    throw new Error("A response must replace a reviewed question or extend the reviewed prefix");
  }
  const existing = responses[questionIndex];
  if (existing && (existing.question_id !== event.question_id ||
    existing.question_version !== event.question_version)) {
    throw new Error("A replacement response must refer to the same question");
  }
  const updated = [...responses];
  updated[questionIndex] = event;
  return updated;
}
