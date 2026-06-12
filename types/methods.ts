// TypeScript types mirroring the Python voting package and demo API.

export type VotingMethod =
  | "plurality"
  | "approval"
  | "irv"
  | "borda"
  | "ranked_pairs"
  | "score"
  | "quadratic";

export interface ElectionResult {
  winners: string[];
  vote_counts: Record<string, number>;
  total_ballots: number;
  abstentions: number;
  tiebreak_applied: boolean;
}

export interface ApprovalResult extends ElectionResult {
  avg_approvals_per_ballot: number;
  approval_rates: Record<string, number>;
}

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

export interface BordaResult extends ElectionResult {
  point_totals: Record<string, number>;
  max_points_per_ballot: number;
  avg_points_per_candidate: number;
}

export interface RankedPairsResult extends ElectionResult {
  pairwise_matrix: Record<string, Record<string, number>>;
  had_condorcet_winner: boolean;
  locked_victories: [string, string, number][];
  skipped_victories: [string, string, number][];
}

export interface ScoreResult extends ElectionResult {
  score_totals: Record<string, number>;
  avg_scores: Record<string, number>;
  max_possible_score: number;
  score_percentages: Record<string, number>;
}

export interface QuadraticResult extends ElectionResult {
  vote_totals: Record<string, number>;
  total_credits_spent: number;
  total_credits_available: number;
  overall_utilization: number;
  avg_voter_utilization: number;
  candidates_with_negative_totals: number;
}

export type AnyElectionResult =
  | ElectionResult
  | ApprovalResult
  | IRVResult
  | BordaResult
  | RankedPairsResult
  | ScoreResult
  | QuadraticResult;

export interface CandidateData {
  id: string;
  name: string;
}

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

export interface MethodDemo {
  scenario: MethodScenario;
  result: AnyElectionResult;
}

export interface ScenarioControl {
  id: string;
  label: string;
  description: string;
  min: number;
  max: number;
  step: number;
  default: number;
  low_label: string;
  high_label: string;
}

export interface VoterBloc {
  id: string;
  name: string;
  description: string;
  share: number;
  voters?: number;
  color: string;
  utilities: Record<string, number>;
  preference_summary?: string;
  strategic_target?: string;
}

export interface DemoScenario {
  id: string;
  title: string;
  domain: string;
  thesis: string;
  lesson: string;
  voter_count: number;
  candidates: CandidateData[];
  controls: ScenarioControl[];
  default_controls: Record<string, number>;
  blocs: VoterBloc[];
}

export interface MethodComparisonResult {
  method: VotingMethod;
  winner: string | null;
  winner_name: string;
  basis: string;
  reason: string;
}

export interface FailureModeAnnotation {
  type: string;
  label: string;
  severity: "success" | "warning" | "info";
  description: string;
}

export interface DerivedMethodBallots {
  plurality: Record<string, unknown>[];
  approval: Record<string, unknown>[];
  ranked: Record<string, unknown>[];
  score: Record<string, unknown>[];
  quadratic: Record<string, unknown>[];
}

export interface DemoScenarioResolution {
  scenario: DemoScenario;
  controls: Record<string, number>;
  results: Record<VotingMethod, AnyElectionResult>;
  comparison: Record<VotingMethod, MethodComparisonResult>;
  annotations: FailureModeAnnotation[];
  derived_ballots: DerivedMethodBallots;
}
