// TypeScript types mirroring the Python voting package dataclasses.

export type VotingMethod =
  | "plurality"
  | "approval"
  | "irv"
  | "borda"
  | "ranked_pairs"
  | "score"
  | "quadratic";

// Base result — all methods return at least this
export interface ElectionResult {
  winners: string[];
  vote_counts: Record<string, number>;
  total_ballots: number;
  abstentions: number;
  tiebreak_applied: boolean;
}

// Approval
export interface ApprovalResult extends ElectionResult {
  avg_approvals_per_ballot: number;
  approval_rates: Record<string, number>;
}

// IRV
export interface IRVRound {
  round_number: number;
  vote_counts: Record<string, number>;
  exhausted_ballots: number;
  active_ballots: number;
  eliminated: string[];
  elimination_was_tiebreak: boolean;
}

export interface IRVResult extends ElectionResult {
  rounds: IRVRound[];
  total_exhausted: number;
  winning_round: number;
}

// Borda
export interface BordaResult extends ElectionResult {
  point_totals: Record<string, number>;
  max_points_per_ballot: number;
  avg_points_per_candidate: number;
}

// Ranked Pairs / Condorcet
export interface RankedPairsResult extends ElectionResult {
  pairwise_matrix: Record<string, Record<string, number>>;
  had_condorcet_winner: boolean;
  locked_victories: [string, string, number][];
  skipped_victories: [string, string, number][];
}

// Score
export interface ScoreResult extends ElectionResult {
  score_totals: Record<string, number>;
  avg_scores: Record<string, number>;
  max_possible_score: number;
  score_percentages: Record<string, number>;
}

// Quadratic
export interface QuadraticResult extends ElectionResult {
  vote_totals: Record<string, number>;
  total_credits_spent: number;
  total_credits_available: number;
  overall_utilization: number;
  avg_voter_utilization: number;
  candidates_with_negative_totals: number;
}

// Union of all result types
export type AnyElectionResult =
  | ElectionResult
  | ApprovalResult
  | IRVResult
  | BordaResult
  | RankedPairsResult
  | ScoreResult
  | QuadraticResult;

// Candidate as returned from API
export interface CandidateData {
  id: string;
  name: string;
}

// Scenario from the API
export interface MethodScenario {
  method: VotingMethod;
  title: string;
  description: string;
  candidates: CandidateData[];
  ballots: Record<string, unknown>[];
  ballot_type: string;
  voter_count: number;
  key_insight: string;
}

// Combined scenario + result for display
export interface MethodDemo {
  scenario: MethodScenario;
  result: AnyElectionResult;
}
