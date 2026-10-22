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
  /** Candidate priority that ordered equal-strength victories; empty if unused. */
  tiebreak_priority: string[];
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

// ---------------------------------------------------------------------------
// Profile resolution (POST /api/voting/profile/resolve)
// ---------------------------------------------------------------------------

export type RankedMethod = "plurality" | "irv" | "borda" | "ranked_pairs";

/** How many voters cast one complete ranking, most preferred first. */
export interface RankedRow {
  count: number;
  ranking: string[];
}

/** An anonymous profile of complete rankings. */
export interface RankedProfile {
  ballot_type: "ranked";
  candidates: string[];
  rows: RankedRow[];
}

/** How many voters share one set of utilities (0 worst, 100 best). */
export interface UtilityRow {
  count: number;
  utilities: Record<string, number>;
}

/** Voter types with utilities; rows keep their order and are not merged. */
export interface UtilityProfile {
  ballot_type: "utility";
  candidates: string[];
  rows: UtilityRow[];
}

/** A profile tagged with its type. */
export type Profile = RankedProfile | UtilityProfile;

export interface ProfileResolveRequest {
  profile: Profile;
  /** Seed for each method's tiebreak; defaults to 0 on the server. */
  tiebreak_seed?: number;
}

/** One tie the tiebreak settled: the sorted tied candidates and its pick. */
export interface TiebreakEvent {
  tied: string[];
  chose: string;
}

export interface PluralityTrace {
  kind: "plurality";
  first_choices: Record<string, number>;
}

export interface IRVRoundTrace {
  round_number: number;
  counts: Record<string, number>;
  exhausted_ballots: number;
  eliminated: string[];
  elimination_was_tiebreak: boolean;
}

export interface IRVTrace {
  kind: "irv";
  rounds: IRVRoundTrace[];
  winning_round: number;
}

export interface BordaTrace {
  kind: "borda";
  points: Record<string, number>;
  max_points_per_ballot: number;
}

export interface Victory {
  winner: string;
  loser: string;
  margin: number;
}

export interface RankedPairsTrace {
  kind: "ranked_pairs";
  had_condorcet_winner: boolean;
  locked: Victory[];
  skipped: Victory[];
  /** Candidate priority that ordered equal-strength victories; empty if unused. */
  tiebreak_priority: string[];
}

export interface ApprovalTrace {
  kind: "approval";
  approvals: Record<string, number>;
  abstentions: number;
}

export interface ScoreTrace {
  kind: "score";
  totals: Record<string, number>;
  max_score: number;
}

export interface QuadraticTrace {
  kind: "quadratic";
  /** Votes for minus votes against. */
  net_votes: Record<string, number>;
  credits_spent: number;
  credits_available: number;
}

export type MethodTrace =
  | PluralityTrace
  | IRVTrace
  | BordaTrace
  | RankedPairsTrace
  | ApprovalTrace
  | ScoreTrace
  | QuadraticTrace;

/** The ballots one voter type casts in every format, under the ballot model. */
export interface VoterBallots {
  row: number;
  count: number;
  choice: string;
  ranking: string[];
  approvals: string[];
  scores: Record<string, number>;
  /** Quadratic votes; nonzero only. */
  allocations: Record<string, number>;
  credits_used: number;
  credit_budget: number;
}

export interface ProfileMethodResult {
  method: VotingMethod;
  winner: string;
  /** No tiebreak applied and, for IRV, no batch elimination of a last-place tie. */
  decisive: boolean;
  tiebreaks: TiebreakEvent[];
  trace: MethodTrace;
}

export interface SingleProfileCriteria {
  majority_winner: string | null;
  condorcet_winner: string | null;
  condorcet_loser: string | null;
}

export interface ProfileResolveResponse {
  /** The request's profile: ranked comes back canonical, utility as given. */
  profile: Profile;
  /** The ranked ballots, canonical; ranked methods and criteria read these. */
  rankings: RankedProfile;
  /** The model that turned utilities into ballots; null for ranked input. */
  ballot_model: string | null;
  /** Each voter type's ballots, in row order; empty for ranked input. */
  voter_ballots: VoterBallots[];
  total_voters: number;
  tiebreak_seed: number;
  /** pairwise[a][b] = voters ranking a above b. */
  pairwise: Record<string, Record<string, number>>;
  criteria: SingleProfileCriteria;
  /** Plurality, IRV, Borda, Ranked Pairs, then approval, score, quadratic for utility input. */
  results: ProfileMethodResult[];
}
