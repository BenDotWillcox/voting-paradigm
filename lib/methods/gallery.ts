/**
 * Content for the paradox gallery: the criteria, and the cells no search can
 * settle. A cell with a specimen fails, shown by example. A search that finds
 * nothing never fills a cell on its own: a pass needs a proof, and a failure
 * the search cannot reach needs a citation.
 */

import type {
  CriterionId,
  RankedMethod,
  Specimen,
  SpecimenSearch,
  SpecimenTransformation,
} from "@/types/methods";

export const GALLERY_METHODS: RankedMethod[] = ["plurality", "irv", "borda", "ranked_pairs"];

export const CRITERIA: { id: CriterionId; label: string; short: string; definition: string }[] = [
  {
    id: "majority",
    label: "Majority",
    short: "Majority",
    definition: "A candidate ranked first by more than half the voters wins.",
  },
  {
    id: "condorcet_winner",
    label: "Condorcet winner",
    short: "Cond. winner",
    definition: "A candidate who beats every rival head to head wins.",
  },
  {
    id: "condorcet_loser",
    label: "Condorcet loser",
    short: "Cond. loser",
    definition: "A candidate who loses to every rival head to head never wins.",
  },
  {
    id: "monotonicity",
    label: "Monotonicity",
    short: "Monotonic",
    definition: "Ranking the winner higher never makes it lose.",
  },
  {
    id: "participation",
    label: "Participation",
    short: "Participation",
    definition: "Turning out to vote sincerely never elects someone you like less than the winner without you.",
  },
  {
    id: "consistency",
    label: "Consistency",
    short: "Consistent",
    definition: "If two electorates each elect a candidate, together they elect it too.",
  },
  {
    id: "iia",
    label: "Independence of irrelevant alternatives",
    short: "IIA",
    definition: "Removing a losing candidate never changes the winner.",
  },
  {
    id: "clones",
    label: "Independence of clones",
    short: "Clones",
    definition:
      "Adding a candidate every voter ranks next to an existing one never changes the winner, except to the clone.",
  },
];

export interface CitedCell {
  verdict: "passes" | "fails";
  reason: string;
}

/** Cells settled by proof or citation rather than by a specimen. */
export const CITED: Record<RankedMethod, Partial<Record<CriterionId, CitedCell>>> = {
  plurality: {
    majority: {
      verdict: "passes",
      reason: "A majority's favorite has more than half the first choices, so it has the most.",
    },
    monotonicity: {
      verdict: "passes",
      reason: "Raising the winner can only add to its first choices.",
    },
    participation: {
      verdict: "passes",
      reason:
        "A new ballot adds a first choice only for that voter's favorite, so it can only move the win to the candidate that voter likes best.",
    },
    consistency: {
      verdict: "passes",
      reason: "First choices add up across electorates. Every scoring rule is consistent (Young 1975).",
    },
  },
  irv: {
    majority: {
      verdict: "passes",
      reason: "A majority's favorite wins in the first round.",
    },
    condorcet_loser: {
      verdict: "passes",
      reason: "The last round is a head-to-head race, which a Condorcet loser always loses.",
    },
    clones: {
      verdict: "passes",
      reason:
        "When a clone is eliminated its ballots move to its twin, so the clones rise or fall together (Tideman 1987).",
    },
  },
  borda: {
    condorcet_loser: {
      verdict: "passes",
      reason:
        "A Borda score adds up head-to-head wins, so a Condorcet loser scores below average and cannot score highest.",
    },
    monotonicity: {
      verdict: "passes",
      reason: "Raising the winner adds to its points and takes points only from the candidates it passes.",
    },
    participation: {
      verdict: "passes",
      reason: "A new ballot gives more points to every candidate it ranks higher.",
    },
    consistency: {
      verdict: "passes",
      reason: "Points add up across electorates. Every scoring rule is consistent (Young 1975).",
    },
  },
  ranked_pairs: {
    majority: {
      verdict: "passes",
      reason: "A majority's favorite beats every rival head to head, so it is the Condorcet winner.",
    },
    condorcet_winner: {
      verdict: "passes",
      reason: "None of its victories can close a cycle, so all of them lock and nothing points to it.",
    },
    condorcet_loser: {
      verdict: "passes",
      reason: "It wins no race, so no victory over it can close a cycle; they all lock and it cannot win.",
    },
    monotonicity: {
      verdict: "passes",
      reason: "Raising the winner only strengthens its victories (Tideman 1987).",
    },
    participation: {
      verdict: "fails",
      reason:
        "Every Condorcet method fails participation once there are four or more candidates (Moulin 1988). With three candidates the search found no specimen.",
    },
    clones: {
      verdict: "passes",
      reason:
        "Independent of clones (Tideman 1987), except in exact ties of victory strength, where the tiebreak decides.",
    },
  },
};

export type GalleryCell =
  | { kind: "specimen"; specimen: Specimen; maxVoters: number }
  | { kind: "cited"; cited: CitedCell; maxVoters: number }
  | { kind: "open"; maxVoters: number };

export function galleryCell(
  searches: SpecimenSearch[],
  method: RankedMethod,
  criterion: CriterionId
): GalleryCell {
  const search = searches.find((s) => s.method === method && s.criterion === criterion);
  const maxVoters = search?.max_voters ?? 0;
  if (search?.specimen) return { kind: "specimen", specimen: search.specimen, maxVoters };
  const cited = CITED[method][criterion];
  return cited ? { kind: "cited", cited, maxVoters } : { kind: "open", maxVoters };
}

const ROLE_LABELS: Record<Specimen["profiles"][number]["role"], string> = {
  profile: "Electorate",
  before: "Before",
  after: "After",
  first: "First electorate",
  second: "Second electorate",
  combined: "Together",
};

export function roleLabel(role: Specimen["profiles"][number]["role"]): string {
  return ROLE_LABELS[role];
}

/** What changes between a specimen's profiles, in words. */
export function describeTransformation(specimen: Specimen): string {
  const t: SpecimenTransformation | null = specimen.transformation;
  if (!t) {
    const focus = specimen.focus ?? "";
    if (specimen.criterion === "majority") return `${focus} is ranked first by a majority.`;
    if (specimen.criterion === "condorcet_winner") return `${focus} beats every rival head to head.`;
    return `${focus} loses to every rival head to head.`;
  }
  switch (t.kind) {
    case "raise":
      return `${t.voters} ${t.voters === 1 ? "voter" : "voters"} ranking ${t.ranking.join(" › ")} move ${t.candidate} up to ${ordinal(t.position + 1)}.`;
    case "add_voters":
      return `${t.voters} more ${t.voters === 1 ? "voter" : "voters"}, ranking ${t.ranking.join(" › ")}, turn out.`;
    case "combine":
      return "The two electorates vote together.";
    case "remove_candidate":
      return `${t.candidate}, a losing candidate, withdraws.`;
    case "add_clone":
      return `${t.clone} joins as a clone of ${t.candidate}, ranked next to it by every voter.`;
  }
}

function ordinal(n: number): string {
  return n === 1 ? "first" : n === 2 ? "second" : n === 3 ? "third" : `${n}th`;
}
