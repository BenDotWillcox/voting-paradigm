/**
 * Shapes of the liquid walkthrough's static data (public/data/liquid-story/),
 * written by scripts/build_liquid_story.py and
 * scripts/build_liquid_example_city.py. Client-safe: figures receive these
 * as props from the server page.
 */

/** The page's arrangements, in its order. */
export const ARRANGEMENTS = [
  "full_turnout",
  "direct",
  "representative",
  "proxy",
  "liquid",
] as const;
export type Arrangement = (typeof ARRANGEMENTS)[number];

export const ARRANGEMENT_LABEL: Record<Arrangement, string> = {
  full_turnout: "Full turnout",
  direct: "Direct voting",
  representative: "District representative",
  proxy: "Personal proxy",
  liquid: "Liquid delegation",
};

/** A turnout level as the data keys it: "0.1", "0.45", ... */
export type LevelKey = string;

export interface ArrangementMeasures {
  fidelity: number;
  contrary_share: number;
  none_share: number;
  overhead: number;
  /** Null where an arrangement has none (a representative has no loops). */
  empty_record_share: number | null;
  empty_record_fidelity: number | null;
  light_record_share: number | null;
  light_record_fidelity: number | null;
  loop_share: number | null;
  /** Fidelity on the questions voters decide themselves. */
  fidelity_kept: number | null;
  /** How often whoever decides for others actually votes. */
  resolver_attendance: number | null;
  /** The share of a question's votes the largest single decider holds (mean, and the worst question). */
  mean_largest_share: number | null;
  max_largest_share: number | null;
  /** Voters represented on fewer than half their questions, and how they fail. */
  share_below_half: number | null;
  below_half_none_share: number | null;
  below_half_contrary_share: number | null;
  /** Overhead counting the history period, when everyone decides everything. */
  lifecycle_overhead: number | null;
  /** Share of questions whose winner is the full-turnout winner. */
  outcome_agreement: number | null;
  /** Liquid: fidelity on delegated pairs, and the delegated and lost shares. */
  fidelity_resolved: number | null;
  delegated_share: number | null;
  lost_share: number | null;
}

/** One point of liquid's handover curve: every voter hands over their `depth` best topics. */
export interface HandoverPoint {
  depth: number;
  fidelity: number;
  overhead: number;
  contrary_share: number;
  none_share: number;
}

/** The analyses made after the freeze, and one proposal's arithmetic (exploratory.json). */
export interface StoryExploratory {
  label: "exploratory";
  handover: { source: string; commit: string; declared: string; cities: number; levels: Record<LevelKey, HandoverPoint[]> };
  wrong_ballot: {
    source: string;
    levels: Record<LevelKey, Record<Arrangement, { match: number; contrary: number; none: number; w0: number; w1: number }>>;
  };
  everyone_votes: EveryoneVotes;
  agent_bars: {
    label: "proposal";
    formula: { representative: string; delegate: string };
    levels: Record<LevelKey, { representative: number; delegate: number }>;
  };
}

/**
 * The everyone-votes reference point (exploratory; delegation_everyone_votes_v1):
 * every arrangement with every resident, office holder and delegate voting.
 * Descriptive: it has no verdict.
 */
export interface EveryoneVotes {
  source: string;
  commit: string;
  declared: string;
  cities: number;
  setting: string;
  measures: Record<
    Arrangement,
    ArrangementMeasures & { fidelity_lower: number; fidelity_upper: number; overhead_lower: number; overhead_upper: number }
  >;
  /** The frozen runner's declared contrasts (h1, specialisation and the ladder's steps). */
  contrasts: Record<string, Interval>;
  /** How many cities' calibrated arrangements stay at or under the cap. */
  cap: Record<"proxy" | "liquid", { cities: number; meets_cap: number; history_feasible: number }>;
}

export interface SweepPoint {
  family: string;
  label: string;
  cities: number;
  /** The point it is compared with. */
  baseline: string | null;
  verdict: string;
  status: string;
  crossing: number | null;
  /** The crossing's confidence set; a null bound is unbounded. */
  confidence: [number | null, number | null];
  gate_holds: boolean;
  levels: Record<LevelKey, { h1: number; cap_share: number }>;
}

export interface SweepPanel {
  title: string;
  series: Array<{ point: string; label: string; baseline: boolean; accent: number | null }>;
}

export interface RouterAt {
  threshold: number;
  coverage: number;
  false_delegation_rate: number;
  false_keep_rate: number;
  false_delegations: number;
  false_keeps: number;
  delegable: number;
  scored: number;
}

export interface Interval {
  estimate: number;
  lower: number;
  upper: number;
}

/** One level of the frozen result, ladder and attendance frontier. */
export interface ResultLevel {
  /** Share of cities whose liquid overhead stays at or under the cap. */
  cap_share: number;
  cap_meeting_cities: number;
  proxy_cap_share: number;
  /** Liquid minus the representative, all cities, with its t-interval. */
  h1: Interval;
  /** The simultaneous band around that curve. */
  band: { lower: number; upper: number };
  /** The same over the cities under the cap; null where none are. */
  h1_cap: Interval | null;
  band_cap: { lower: number; upper: number } | null;
  /** The per-level reading under the frozen rules. */
  direction: string;
  size: string;
  /** Topic specialisation's reading against its own pre-set minimum. */
  specialisation: { direction: string; size: string };
  /** The declared contrasts, keyed as in decomposition.csv. */
  decomposition: Record<string, Interval>;
  /** Liquid minus the representative with delegates voting at least `floor`. */
  frontier: Array<{ floor: number } & Interval>;
}

export interface StoryResults {
  source: string;
  label: "frozen";
  rules: { cap: number; delta: number; feasible_share: number; confidence: number };
  threshold: {
    status: string;
    bracket: [number, number];
    crossing: number;
    confidence: [number, number];
    first_supported: number | null;
    gate_holds: boolean;
  };
  levels: Record<LevelKey, ResultLevel>;
  sweeps: {
    /** The sweeps' shared baseline (the first 48 primary cities). */
    reference: string;
    /** The belief-structure family's own baseline. */
    structural_baseline: string;
    panels: SweepPanel[];
    points: Record<string, SweepPoint>;
  };
  router: {
    source: string;
    model: string;
    fixture: { categories: number; nested_categories: number; questions: number; voter_cases: number };
    operating: RouterAt;
    by_threshold: RouterAt[];
  };
}

export interface StoryMeasures {
  source: string;
  label: "frozen";
  protocol: {
    frozen: string;
    commit: string;
    cities: number;
    cap: number;
    swiss_marker: number;
    turnout_grid: number[];
  };
  verdict: {
    text: string;
    crossing: number;
    confidence: [number, number];
    gate_holds: boolean;
  };
  levels: Record<LevelKey, Record<Arrangement, ArrangementMeasures>>;
}

/**
 * One resident's ballot on one question. Own ballot: M (cast; it matches)
 * or N (not cast). Someone else's: m (matched), c (contrary) or n (not
 * cast).
 */
export type BallotCode = "M" | "N" | "m" | "c" | "n";

export interface Candidate {
  person: number;
  district: number;
  matches: number;
  trials: number;
  mean: number;
  lower: number;
}

export interface CityTotals {
  match: number;
  contrary: number;
  none: number;
  fidelity: number;
  overhead: number;
}

export interface CityLevel {
  acceptance: number;
  meets_cap: boolean;
  /** One BallotCode per resident, by resident index. */
  codes: Record<Arrangement, string>;
  /** Liquid: whose ballot counted for each resident on the featured question. */
  liquid_resolver: number[];
  /**
   * Liquid: why each resident's ballot is or is not their own. d delegated,
   * l on a loop, e an empty record, k kept (no candidate good enough).
   */
  liquid_reason: string;
  /** Each arrangement's winner on every question: y or n, in question order. */
  winners: Record<Arrangement, string>;
  totals: Record<Arrangement, CityTotals>;
}

export interface CityMechanism {
  level: number;
  acceptance: number;
  history_overhead: number;
  cap: number;
  credible_mass: number;
  showcase: {
    voter: number;
    topic: number;
    record: number;
    candidates: Candidate[];
    /** Per topic: the delegate's index, or -1 when kept. */
    delegates: number[];
    /** Per topic: whose ballot counts for them in the end. */
    resolvers: number[];
  };
  /** How many residents hand over 0, 1, ... every topic. */
  handed_over: number[];
  short_record: {
    voter: number;
    topic: number;
    /** Their ballots in the showcase topic. */
    record: number;
    /** Their ballots in the whole record. */
    total_record: number;
    candidates: Candidate[];
  };
  empty_records: { count: number; example: number | null };
  ballot: Array<{ question: number; topic: number; resolver: number; code: BallotCode }>;
  /**
   * The longest path from a resident to whoever decides for them. It ends
   * at someone who keeps the topic, or at a loop member; `cycle` is that
   * loop, from the chain's end round to it again (empty when it keeps).
   */
  chain: { topic: number; path: number[]; ends: "loop" | "keeps"; cycle: number[] };
  loop: { topic: number; members: number[] };
  loops_per_topic: number[];
  /** Handed-over (resident, topic) pairs, and how many end with a loop member. */
  handed_pairs: number;
  handed_pairs_ending_on_loop: number;
  /** A resident who hands over every topic, with turnout near the city's mean. */
  typical: {
    voter: number;
    turnout: number;
    /** The topic of every evaluation question, in question order. */
    questions: number[];
    /** Their ballot on every evaluation question, per arrangement. */
    strips: Record<"direct" | "representative" | "liquid", string>;
  };
  lost: { voter: number; resolver: number; question: number } | null;
  calibration: Array<{ acceptance: number; overhead: number }>;
}

export interface StoryCity {
  city_version: number;
  generator: string;
  benchmark: string;
  position: number;
  seed: number;
  design: {
    residents: number;
    districts: number;
    residents_per_district: number;
    candidates_per_district: number;
    topics: number;
    history_per_topic: number;
    evaluation_per_topic: number;
    turnout_logit_sd: number;
    office_rate: number;
    cap: number;
  };
  topics: string[];
  district_names: string[];
  district: number[];
  representatives: number[];
  /** Resident indices in drawing order: by district, then own turnout rate. */
  order: number[];
  /** Each resident's own turnout rate per level, in thousandths. */
  turnout: Record<LevelKey, number[]>;
  question: { index: number; id: string; topic: number };
  levels: Record<LevelKey, CityLevel>;
  mechanism: CityMechanism;
  /** The same city with everyone voting (exploratory), for the story's first two parts. */
  everyone: CityLevel & {
    label: "exploratory";
    source: string;
    /** The typical resident's ballot on every evaluation question, per arrangement. */
    typical_strips: Record<"direct" | "representative" | "liquid", string>;
  };
}

/** The data keys turnout levels by Python's repr: 0.1 -> "0.1". */
export function levelKey(level: number): LevelKey {
  return String(level);
}

/** Readable topic names for the fitted model's topic keys. */
export const TOPIC_LABEL: Record<string, string> = {
  civil_rights_liberties: "Civil rights and liberties",
  environment_energy: "Environment and energy",
  guns_policing: "Guns and policing",
  health_care: "Health care",
  housing: "Housing",
  immigration: "Immigration",
  reproductive_rights: "Reproductive rights",
  taxes_spending: "Taxes and spending",
};

export function topicLabel(key: string): string {
  return TOPIC_LABEL[key] ?? key.replace(/_/g, " ");
}
