import type { z } from "zod";
import type {
  categoryJudgmentsRequestSchema,
  categoryJudgmentsResponseSchema,
  categorySchema,
  resolveBallotPaperRequestSchema,
  resolveBallotPaperResponseSchema,
  scenarioResponseSchema,
  validateDelegationRequestSchema,
  validateDelegationResponseSchema,
  viewerDelegationSchema,
} from "@/lib/validations/delegation-schemas";

/** One category the viewer has handed to someone, in the viewer's words. */
export type ViewerDelegation = z.infer<typeof viewerDelegationSchema>;

export type DelegationCategory = z.infer<typeof categorySchema>;

export type DelegationScenario = z.infer<typeof scenarioResponseSchema>;
export type DelegationPerson = DelegationScenario["persons"][number];
export type DelegationBallotPaper = DelegationScenario["ballot_papers"][number];
export type DelegationQuestion = DelegationBallotPaper["questions"][number];

export type ValidateDelegationRequest = z.infer<typeof validateDelegationRequestSchema>;
export type ValidateDelegationResponse = z.infer<typeof validateDelegationResponseSchema>;

export type CategoryJudgmentsRequest = z.infer<typeof categoryJudgmentsRequestSchema>;
export type CategoryJudgmentsResponse = z.infer<typeof categoryJudgmentsResponseSchema>;

export type ResolveBallotPaperRequest = z.infer<typeof resolveBallotPaperRequestSchema>;
export type ResolveBallotPaperResponse = z.infer<typeof resolveBallotPaperResponseSchema>;
export type QuestionResult = ResolveBallotPaperResponse["questions"][number];
export type QuestionTally = QuestionResult["delegated"];
export type VoteReceipt = NonNullable<QuestionResult["receipt"]>;
