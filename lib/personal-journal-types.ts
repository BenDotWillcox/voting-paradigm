export type JournalVote = "yes" | "no";
export type JournalModelVersion = "reasoning-examples-v1" | "reasoning-examples-v2";

export interface JournalMeasure {
  title: string;
  sourceUrl: string;
  text: string;
  yesMeaning: string;
  noMeaning: string;
  familiar: boolean;
}

export interface JournalPrediction {
  choice: JournalVote;
  probabilityYes: number;
  model: string;
  explanation: string;
  historyCount: number;
}

export interface JournalForecastSet {
  reasoning: JournalPrediction;
  baseline: JournalPrediction;
  withoutReasoning: JournalPrediction;
}

export interface JournalCheck {
  id: string;
  startedAt: string;
  /** Checks created before model versioning used reasoning-examples-v1. */
  modelVersion?: JournalModelVersion;
  evidenceCount: number;
  clarificationCount: number;
  slotIds: string[];
}

export interface JournalQuestion {
  prompt: string;
  trigger: "miss" | "uncertain";
  kind?: "contrast" | "counterfactual" | "weight";
  referenceId?: string;
}

export type JournalFollowUp =
  | { question: JournalQuestion; status: "pending" | "skipped" }
  | { question: JournalQuestion; status: "answered"; answer: string };

interface BallotRecord {
  id: string;
  measure: JournalMeasure;
  lockedAt: string;
  checkId?: string;
  /** An original, uncorrected packet has revision zero. */
  revision?: number;
}

export type JournalEntry =
  | (BallotRecord & { status: "locked" })
  | (BallotRecord & {
      status: "revealed";
      vote: JournalVote;
      reasoning: string;
      votedAt: string;
      prediction: JournalPrediction;
      comparison?: Omit<JournalForecastSet, "reasoning">;
      /** Actual packet used by the locked prediction if corrected after voting. */
      forecastMeasure?: JournalMeasure;
      followUp?: JournalFollowUp;
      /** Saved answer about the original wording, for historical display only. */
      archivedFollowUp?: Extract<JournalFollowUp, { status: "answered" }>;
      /** The question policy ran and found no follow-up to ask. */
      followUpReviewed?: true;
    });
