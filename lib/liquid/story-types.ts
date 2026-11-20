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
