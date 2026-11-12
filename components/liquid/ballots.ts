import type {
  DelegationQuestion,
  DelegationScenario,
  QuestionTally,
} from "@/types/delegation";

/**
 * One vote, as it travels: a single option id, every option in order for a
 * ranked question, or the approved options.
 */
export type Choice = string[];

export function findQuestion(
  scenario: DelegationScenario,
  questionId: string
): DelegationQuestion | undefined {
  for (const paper of scenario.ballot_papers) {
    const found = paper.questions.find((question) => question.id === questionId);
    if (found) return found;
  }
  return undefined;
}

export function optionName(question: DelegationQuestion | undefined, id: string): string {
  return question?.options.find((option) => option.id === id)?.name ?? id;
}

/** A choice in words: "Yes", "1. Leaf, 2. Waves", or "Civic Square and the depot". */
export function choiceLabel(question: DelegationQuestion | undefined, choice: Choice): string {
  const names = choice.map((id) => optionName(question, id));
  if (question?.ballot_type === "ranked") {
    return names.map((name, index) => `${index + 1}. ${name}`).join(", ");
  }
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** A shorter form for lists: the first choice, and how many more. */
export function choiceShort(question: DelegationQuestion | undefined, choice: Choice): string {
  const first = optionName(question, choice[0] ?? "");
  if (question?.ballot_type === "ranked") return `${first} first`;
  return choice.length > 1 ? `${first} +${choice.length - 1}` : first;
}

/** What happened: a yes/no measure passed or did not; otherwise an option won. */
export function outcomeLabel(question: DelegationQuestion | undefined, winners: string[]): string {
  if (!question || question.ballot_type === "single_choice") {
    return winners.includes("yes") ? "passed" : "did not pass";
  }
  return `${winners.map((id) => optionName(question, id)).join(" / ")} won`;
}

export const BALLOT_TEXT: Record<DelegationQuestion["ballot_type"], string> = {
  single_choice: "Yes or no",
  ranked: "Ranked choice",
  approval: "Approval vote",
};

export const METHOD_TEXT: Record<QuestionTally["method"], string> = {
  plurality: "by simple majority of the ballots cast",
  irv: "by instant-runoff: the last-placed option is dropped and its ballots move to their next choice, until one has a majority",
  approval: "by approval: the option approved on the most ballots",
};
