import type { VotingMethod } from "@/types/methods";

/** Four main parts, followed by reference material outside their sequence. */

export const CHAPTERS = [
  { title: "Compare outcomes", optional: false, steps: ["comparison"] },
  { title: "Change an outcome", optional: false, steps: ["experiment"] },
  { title: "Explore the implementation", optional: false, steps: ["implementation"] },
  { title: "See how it was tested", optional: false, steps: ["testing"] },
  {
    title: "Ballots & preferences",
    optional: true,
    returnTo: "implementation",
    steps: ["voters", "ballot-single", "ballot-ranked", "head-to-head", "ballot-approval", "ballot-score", "ballot-quadratic"],
  },
  {
    title: "Theory & examples",
    optional: true,
    returnTo: "testing",
    steps: ["examples", "fairness", "paradox-spoiler", "paradox-no-show", "paradox-monotonicity", "gallery"],
  },
  {
    title: "Simulation evidence",
    optional: true,
    returnTo: "testing",
    steps: ["one-election", "atlas", "disagreement", "efficiency"],
  },
] as const;

export type StepId = (typeof CHAPTERS)[number]["steps"][number];

export const STEPS: readonly StepId[] = CHAPTERS.flatMap((chapter) => chapter.steps);

// The six slides' names, each to the step that now holds its content
const SECTION_STEPS: Record<string, StepId> = {
  counts: "comparison",
  "head-to-head": "head-to-head",
  ballots: "voters",
  paradoxes: "gallery",
  atlas: "atlas",
  "at-scale": "disagreement",
};

export function isStep(value: string | undefined): value is StepId {
  return (STEPS as readonly string[]).includes(value ?? "");
}

// Steps renamed since their links were shared
const RENAMED_STEPS: Record<string, StepId> = { ballots: "voters", "at-scale": "disagreement" };

const COUNT_STEP_METHODS: Record<string, VotingMethod> = {
  "count-plurality": "plurality",
  "count-irv": "irv",
  "count-borda": "borda",
  "count-ranked-pairs": "ranked_pairs",
  "count-approval": "approval",
  "count-score": "score",
  "count-quadratic": "quadratic",
};

function lookup<T extends string>(values: Record<string, T>, key: string | undefined): T | undefined {
  return key && Object.prototype.hasOwnProperty.call(values, key) ? values[key] : undefined;
}

/** The step a link names, by `?step=` or by an old `?section=`. */
export function linkedStep(step: string | undefined, section: string | undefined): StepId | null {
  if (isStep(step)) return step;
  if (lookup(COUNT_STEP_METHODS, step)) return "implementation";
  return lookup(RENAMED_STEPS, step) ?? lookup(SECTION_STEPS, section) ?? null;
}

/** Explicit valid selection wins; old count-step links retain their method. */
export function linkedMethod(step?: string, method?: string): VotingMethod {
  const explicit = Object.values(COUNT_STEP_METHODS).find((value) => value === method);
  return explicit ?? lookup(COUNT_STEP_METHODS, step) ?? "plurality";
}

/** A reference returns to the main part that introduces its material. */
export function referenceReturn(step: string | undefined): "implementation" | "testing" | null {
  const chapter = CHAPTERS.find((item) => (item.steps as readonly string[]).includes(step ?? ""));
  return chapter && "returnTo" in chapter ? chapter.returnTo : null;
}

/** What a preset's notes describe: its seven counts, and its two-way races. */
export type ExampleSlide = "counts" | "head-to-head";

/** One example electorate on the "change the voters" step. */
export interface SlideExample {
  presetId: string;
  label: string;
}
