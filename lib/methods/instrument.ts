import type {
  ProfileMethodResult,
  ProfileResolveResponse,
  VotingMethod,
} from "@/types/methods";

/** How each method is named and summarized in the instrument. */
export const METHOD_META: Record<VotingMethod, { label: string; rule: string }> = {
  plurality: { label: "Plurality", rule: "Most first choices wins" },
  irv: { label: "Instant runoff", rule: "Drop the weakest, transfer, repeat" },
  borda: { label: "Borda count", rule: "Points for every position" },
  ranked_pairs: { label: "Ranked Pairs", rule: "Lock the strongest head-to-head wins" },
  approval: { label: "Approval", rule: "Most approvals wins" },
  score: { label: "Score voting", rule: "Highest total score wins" },
  quadratic: { label: "Quadratic voting", rule: "Most net votes wins" },
};

/** The five ballot formats, each with the methods that read it. */
export const BALLOT_GROUPS: { label: string; methods: VotingMethod[] }[] = [
  { label: "Single-choice ballot", methods: ["plurality"] },
  { label: "Ranked ballot", methods: ["irv", "borda", "ranked_pairs"] },
  { label: "Approval ballot", methods: ["approval"] },
  { label: "Score ballot", methods: ["score"] },
  { label: "Quadratic ballot", methods: ["quadratic"] },
];

export type CriterionCheck = "pass" | "fail" | "none";

/** Whether a result honors the three single-profile criteria. */
export function criteriaChecks(
  result: ProfileMethodResult,
  criteria: ProfileResolveResponse["criteria"]
): { majority: CriterionCheck; condorcetWinner: CriterionCheck; condorcetLoser: CriterionCheck } {
  const elects = (candidate: string | null): CriterionCheck =>
    candidate === null ? "none" : result.winner === candidate ? "pass" : "fail";
  const avoids = (candidate: string | null): CriterionCheck =>
    candidate === null ? "none" : result.winner === candidate ? "fail" : "pass";
  return {
    majority: elects(criteria.majority_winner),
    condorcetWinner: elects(criteria.condorcet_winner),
    condorcetLoser: avoids(criteria.condorcet_loser),
  };
}

/** The per-candidate numbers a method's channel shows, if any. */
export function channelTally(result: ProfileMethodResult): Record<string, number> | null {
  const trace = result.trace;
  switch (trace.kind) {
    case "plurality":
      return trace.first_choices;
    case "borda":
      return trace.points;
    case "irv":
      return trace.rounds[trace.rounds.length - 1]?.counts ?? null;
    case "approval":
      return trace.approvals;
    case "score":
      return trace.totals;
    case "quadratic":
      return trace.net_votes;
    default:
      return null;
  }
}
