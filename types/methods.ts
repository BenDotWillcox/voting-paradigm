// TypeScript types mirroring the Python voting package and the voting API.

export type VotingMethod =
  | "plurality"
  | "approval"
  | "irv"
  | "borda"
  | "ranked_pairs"
  | "score"
  | "quadratic";

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

// ---------------------------------------------------------------------------
// Paradox gallery (public/data/methods/specimens.json)
// ---------------------------------------------------------------------------

export type CriterionId =
  | "majority"
  | "condorcet_winner"
  | "condorcet_loser"
  | "monotonicity"
  | "participation"
  | "consistency"
  | "iia"
  | "clones";

export type SpecimenRole = "profile" | "before" | "after" | "first" | "second" | "combined";

export type SpecimenTransformation =
  | { kind: "raise"; candidate: string; ranking: string[]; position: number; voters: number }
  | { kind: "add_voters"; ranking: string[]; voters: number }
  | { kind: "combine" }
  | { kind: "remove_candidate"; candidate: string }
  | { kind: "add_clone"; candidate: string; clone: string };

/** The smallest profiles found on which a method fails a criterion. */
export interface Specimen {
  id: string;
  method: RankedMethod;
  criterion: CriterionId;
  voters: number;
  focus: string | null;
  transformation: SpecimenTransformation | null;
  profiles: {
    role: SpecimenRole;
    candidates: string[];
    rows: [number, string[]][];
    winner: string;
  }[];
}

export interface SpecimenSearch {
  method: RankedMethod;
  criterion: CriterionId;
  max_voters: number;
  specimen: Specimen | null;
}
