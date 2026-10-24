/**
 * The methods page's chapters and their steps, in order. `?step=` names a
 * step; the slide names of the earlier six-slide page still resolve through
 * `?section=`. Plain data, so the server page can read a link before the
 * client renders.
 */

export const CHAPTERS = [
  {
    title: "Ballots and counts",
    steps: [
      "voters",
      "ballot-single",
      "count-plurality",
      "ballot-ranked",
      "count-irv",
      "count-borda",
      "head-to-head",
      "count-ranked-pairs",
      "ballot-approval",
      "count-approval",
      "ballot-score",
      "count-score",
      "ballot-quadratic",
      "count-quadratic",
    ],
  },
  { title: "Same voters, different winners", steps: ["comparison", "examples"] },
  {
    title: "When methods break",
    steps: ["fairness", "paradox-spoiler", "paradox-no-show", "paradox-monotonicity", "gallery"],
  },
  { title: "Across many elections", steps: ["atlas", "at-scale"] },
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
  "at-scale": "at-scale",
};

export function isStep(value: string | undefined): value is StepId {
  return (STEPS as readonly string[]).includes(value ?? "");
}

// Steps renamed since their links were shared
const RENAMED_STEPS: Record<string, StepId> = { ballots: "voters" };

/** The step a link names, by `?step=` or by an old `?section=`. */
export function linkedStep(step: string | undefined, section: string | undefined): StepId | null {
  if (isStep(step)) return step;
  if (step && RENAMED_STEPS[step]) return RENAMED_STEPS[step];
  return section ? (SECTION_STEPS[section] ?? null) : null;
}

/** What a preset's notes describe: its seven counts, and its two-way races. */
export type ExampleSlide = "counts" | "head-to-head";

/** One example electorate on the "change the voters" step. */
export interface SlideExample {
  presetId: string;
  label: string;
}
