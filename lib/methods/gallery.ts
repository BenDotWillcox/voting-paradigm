/**
 * Content for the paradox gallery: the criteria, and the cells no search can
 * settle. A cell with a specimen fails, shown by example. A search that finds
 * nothing never fills a cell on its own: a pass needs a proof, a failure the
 * search cannot reach needs a citation, and anything else stays open.
 */

import type {
  CriterionId,
  Specimen,
  SpecimenSearch,
  SpecimenTransformation,
  VotingMethod,
} from "@/types/methods";

import { formatUtility } from "./profile";

/**
 * The gallery's rows. Ranked methods are searched over rankings; rated
 * methods over voter types with utilities, cast into ballots by sincere-v1.
 */
export const GALLERY_GROUPS: { label: string; methods: VotingMethod[] }[] = [
  { label: "Searched over rankings", methods: ["plurality", "irv", "borda", "ranked_pairs"] },
  { label: "Searched over utilities, ballots by sincere-v1", methods: ["approval", "score", "quadratic"] },
];

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
    definition: "Ranking or rating the winner higher never makes it lose.",
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
  verdict: "passes" | "fails" | "open";
  reason: string;
}

/**
 * Cells settled by proof or citation rather than by a specimen, and open cells
 * with a reason. Pass claims use the search's decisive-count scope: no result
 * tiebreaks or simultaneous IRV eliminations. The rated proofs use sincere-v1's rules: approve above your
 * average utility, score by rescaling your utilities from 0 to 10, and cast
 * quadratic votes in proportion to each utility's distance from your average.
 */
export const CITED: Record<VotingMethod, Partial<Record<CriterionId, CitedCell>>> = {
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
      reason:
        "For decisive counts, a Condorcet loser cannot win a majority or the final head-to-head race. The package eliminates tied last-place candidates together; those excluded rounds can elect a Condorcet loser.",
    },
    clones: {
      verdict: "passes",
      reason:
        "With one-at-a-time eliminations, a clone's ballots transfer to its twin (Tideman 1987). The package can instead eliminate tied last-place clones together and change the winner outside the clone group. That exception is excluded from the decisive counts shown here.",
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
  approval: {
    monotonicity: {
      verdict: "passes",
      reason:
        "Raising the winner's utility lifts the voter's average, so the winner can only gain an approval and every other candidate can only lose one.",
    },
    participation: {
      verdict: "passes",
      reason:
        "A voter who approves a candidate approves everyone they like more, so turning out gives the old winner at least as many approvals as anyone the voter likes less.",
    },
    consistency: {
      verdict: "passes",
      reason: "Approvals add up across electorates.",
    },
  },
  score: {
    monotonicity: {
      verdict: "passes",
      reason:
        "Scores rescale each voter's utilities from 0 to 10, so raising the winner can only raise its score and lower the others'.",
    },
    participation: {
      verdict: "passes",
      reason:
        "A voter scores everyone they like more at least as high, so turning out gives the old winner at least as many points as anyone the voter likes less.",
    },
    consistency: {
      verdict: "passes",
      reason: "Scores add up across electorates.",
    },
    clones: {
      verdict: "passes",
      reason:
        "An exact clone leaves every voter's lowest and highest utility in place, so every score stays the same and the clone scores what the original does. If the original won, it ties with its clone and the tiebreak picks one of the two.",
    },
  },
  quadratic: {
    participation: {
      verdict: "open",
      reason:
        "Exact votes would satisfy it: a voter puts at least as many net votes on everyone they like more. But votes are rounded to whole numbers and trimmed to the 100-credit budget, which can leave two close favorites one vote out of order, and no proof covers that.",
    },
    consistency: {
      verdict: "passes",
      reason: "Net votes add up across electorates.",
    },
  },
};

export type GalleryCell =
  | { kind: "specimen"; specimen: Specimen; maxVoters: number }
  | { kind: "cited"; cited: CitedCell; maxVoters: number }
  | { kind: "open"; reason: string | null; maxVoters: number };

export function galleryCell(
  searches: SpecimenSearch[],
  method: VotingMethod,
  criterion: CriterionId
): GalleryCell {
  const search = searches.find((s) => s.method === method && s.criterion === criterion);
  const maxVoters = search?.max_voters ?? 0;
  if (search?.specimen) return { kind: "specimen", specimen: search.specimen, maxVoters };
  const cited = CITED[method][criterion];
  if (!cited || cited.verdict === "open") {
    return { kind: "open", reason: cited?.reason ?? null, maxVoters };
  }
  return { kind: "cited", cited, maxVoters };
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
  const candidates = specimen.profiles[0].candidates;
  switch (t.kind) {
    case "raise":
      return `${voters(t.voters)} ranking ${t.ranking.join(" › ")} move ${t.candidate} up to ${ordinal(t.position + 1)}.`;
    case "raise_utility": {
      const i = candidates.indexOf(t.candidate);
      const pure = t.before.every((u, j) => j === i || u === t.after[j]);
      if (pure) {
        return `${voters(t.voters)} rating ${utilitiesText(candidates, t.before)} raise ${t.candidate} from ${formatUtility(t.before[i])} to ${formatUtility(t.after[i])}.`;
      }
      // A raise followed by a rescaling back onto the 0–100 scale
      return `${voters(t.voters)} rating ${utilitiesText(candidates, t.before)} change to ${utilitiesText(candidates, t.after)}. Sincere ballots depend only on how each voter's utilities are spaced, so this raises ${t.candidate} against every rival.`;
    }
    case "add_voters":
      return `${t.voters} more ${t.voters === 1 ? "voter" : "voters"}, ranking ${t.ranking.join(" › ")}, turn out.`;
    case "add_utility_voters":
      return `${t.voters} more ${t.voters === 1 ? "voter" : "voters"}, rating ${utilitiesText(candidates, t.utilities)}, turn out.`;
    case "combine":
      return "The two electorates vote together.";
    case "remove_candidate":
      return `${t.candidate}, a losing candidate, withdraws.`;
    case "add_clone":
      return specimen.ballot_model
        ? `${t.clone} joins as an exact clone of ${t.candidate}: every voter gives it ${t.candidate}'s utility.`
        : `${t.clone} joins as a clone of ${t.candidate}, ranked next to it by every voter.`;
  }
}

function voters(count: number): string {
  return `${count} ${count === 1 ? "voter" : "voters"}`;
}

/** Utilities in candidate order on the instrument's 0–10 scale: "A 0 · B 5 · C 10". */
function utilitiesText(candidates: string[], utilities: number[]): string {
  return candidates.map((id, i) => `${id} ${formatUtility(utilities[i])}`).join(" · ");
}

function ordinal(n: number): string {
  return n === 1 ? "first" : n === 2 ? "second" : n === 3 ? "third" : `${n}th`;
}
