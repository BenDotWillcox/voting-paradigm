export type JournalVote = "yes" | "no";

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

interface BallotRecord {
  id: string;
  measure: JournalMeasure;
  lockedAt: string;
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
      /** Actual packet used by the locked prediction if corrected after voting. */
      forecastMeasure?: JournalMeasure;
    });
