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

/** Utilities in candidate order, as utility specimens record them. */
type Utilities = number[];

export type SpecimenTransformation =
  | { kind: "raise"; candidate: string; ranking: string[]; position: number; voters: number }
  | { kind: "raise_utility"; candidate: string; before: Utilities; after: Utilities; voters: number }
  | { kind: "add_voters"; ranking: string[]; voters: number }
  | { kind: "add_utility_voters"; utilities: Utilities; voters: number }
  | { kind: "combine" }
  | { kind: "remove_candidate"; candidate: string }
  | { kind: "add_clone"; candidate: string; clone: string };

interface SpecimenProfileBase {
  role: SpecimenRole;
  candidates: string[];
  winner: string;
}

/**
 * One profile in a specimen. Ranked methods are searched over rankings;
 * approval, score and quadratic voting over voter types with utilities.
 */
export type SpecimenProfile =
  | (SpecimenProfileBase & { ballot_type: "ranked"; rows: [number, string[]][] })
  | (SpecimenProfileBase & { ballot_type: "utility"; rows: [number, Utilities][] });

/** The smallest profiles found on which a method fails a criterion. */
export interface Specimen {
  id: string;
  method: VotingMethod;
  criterion: CriterionId;
  /** The model that turned utilities into ballots; null for ranked methods. */
  ballot_model: string | null;
  voters: number;
  focus: string | null;
  transformation: SpecimenTransformation | null;
  profiles: SpecimenProfile[];
}

export interface SpecimenSearch {
  method: VotingMethod;
  criterion: CriterionId;
  ballot_model: string | null;
  max_voters: number;
  specimen: Specimen | null;
}

// ---------------------------------------------------------------------------
// Atlas (POST /api/voting/atlas, public/data/methods/atlas.json)
// ---------------------------------------------------------------------------

/** A candidate at a point in the unit square; y grows downward. */
export interface AtlasCandidate {
  id: string;
  x: number;
  y: number;
}

export interface AtlasRequest {
  candidates: AtlasCandidate[];
  tiebreak_seed?: number;
}

export interface AtlasPointRequest extends AtlasRequest {
  /** Row-major cell index; the cloud sits at its center. */
  cell: number;
}

export interface AtlasMap {
  method: VotingMethod;
  /** The winner's ID in every cell, row-major from the top left. */
  winners: string;
  /** Cells where a tiebreak decided the winner. */
  ties: number[];
}

export interface AtlasResponse {
  candidates: AtlasCandidate[];
  /** Cells per side. */
  size: number;
  cloud: {
    voters_per_type: number;
    /** Standard deviation of the Gaussian the cloud approximates. */
    spread: number;
    /** Each voter type's offset from the cloud's center. */
    offsets: [number, number][];
  };
  ballot_model: string;
  tiebreak_seed: number;
  maps: AtlasMap[];
  /** The Condorcet winner per cell, "-" where there is none. */
  condorcet: string;
  /** The candidate with the least total distance to the voters, per cell. */
  utilitarian: string;
  /** How many different winners the seven methods produce, one digit per cell. */
  disagreement: string;
}

// ---------------------------------------------------------------------------
// Simulation (public/data/methods/simulation.json, eval/benchmarks/methods_simulation_v1)
// ---------------------------------------------------------------------------

/** A rate with its 95% Wilson interval. */
export interface SimulationRate {
  count: number;
  of: number;
  rate: number | null;
  interval: [number, number];
}

export interface SimulationGroup {
  candidates: number;
  elections: number;
  /** Elections in which a Condorcet winner exists. */
  condorcet_winner: SimulationRate;
  /** Of those, the share in which each method elects it. */
  condorcet_efficiency: Record<VotingMethod, SimulationRate>;
  /** Elections a tie decided, by method. */
  tie_rate: Record<VotingMethod, SimulationRate>;
  /** Instant runoff's ties by kind: the tiebreak, or eliminating the tied together (with or without votes). */
  irv_ties: Record<"tiebreak" | "together" | "together_empty", SimulationRate>;
  /** Each pair once, in method order: how often the two elect different winners. */
  disagreement: (SimulationRate & { a: VotingMethod; b: VotingMethod })[];
}

export interface SimulationSummary {
  study: string;
  config: {
    seed: number;
    voters: number;
    candidate_counts: number[];
    elections: number;
    tiebreak_seed: number;
  };
  methods: VotingMethod[];
  ballot_model: string;
  interval: string;
  by_candidates: SimulationGroup[];
  benchmark: string;
  source_sha256: string;
}
