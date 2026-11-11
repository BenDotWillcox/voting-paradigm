import type { ScalarBallotState } from "@/types/expressive-scalar";

export type BinaryVote = "yes" | "no";
export type CurveVote = BinaryVote | "abstain";

export interface ScalarComparisonRequest {
  ballot: ScalarBallotState;
  binary_vote: BinaryVote;
}

export interface ScalarComparisonVoter {
  id: string;
  label: string;
  ballot: Omit<ScalarBallotState, "probe">;
  binary_vote: CurveVote;
  curve_vote: CurveVote;
  status_quo_score: number;
  proposal_score: number;
}

export interface ScalarComparisonPoint {
  rate: number;
  mean_score: number;
  approval_count: number;
  user_score: number;
  user_approved: boolean;
  prefer_this: number;
  prefer_binary: number;
  indifferent: number;
}

export interface ScalarComparisonResponse {
  model: "scalar-comparison-v4";
  status_quo: 4.55;
  proposal: 4.4;
  electorate_size: 100;
  candidate_step: 0.05;
  score_tie_tolerance: number;
  user_binary_vote: BinaryVote;
  user_curve_vote: CurveVote;
  electorate: {
    id: string;
    label: string;
    description: string;
    seed: number;
    voters: ScalarComparisonVoter[];
  };
  binary: {
    yes: number;
    no: number;
    abstain: number;
    passed: boolean;
    outcome_rate: number;
  };
  pair: {
    status_quo_mean: number;
    proposal_mean: number;
    winner_rates: number[];
  };
  winner_rates: number[];
  max_mean_score: number;
  points: ScalarComparisonPoint[];
}
