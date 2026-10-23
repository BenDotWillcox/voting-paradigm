/**
 * The methods page's chapters and their steps, in order. `?step=` names a
 * step; the slide names of the earlier six-slide page still resolve through
 * `?section=`. Plain data, so the server page can read a link before the
 * client renders.
 */

export const CHAPTERS = [
  { title: "Ballots and counts", steps: ["ballots", "head-to-head"] },
  { title: "Same voters, different winners", steps: ["comparison"] },
  { title: "When methods break", steps: ["gallery"] },
  { title: "Across many elections", steps: ["atlas", "at-scale"] },
] as const;

export type StepId = (typeof CHAPTERS)[number]["steps"][number];

export const STEPS: readonly StepId[] = CHAPTERS.flatMap((chapter) => chapter.steps);

// The six slides' names, each to the step that now holds its content
const SECTION_STEPS: Record<string, StepId> = {
  counts: "comparison",
  "head-to-head": "head-to-head",
  ballots: "ballots",
  paradoxes: "gallery",
  atlas: "atlas",
  "at-scale": "at-scale",
};

export function isStep(value: string | undefined): value is StepId {
  return (STEPS as readonly string[]).includes(value ?? "");
}

/** The step a link names, by `?step=` or by an old `?section=`. */
export function linkedStep(step: string | undefined, section: string | undefined): StepId | null {
  if (isStep(step)) return step;
  return section ? (SECTION_STEPS[section] ?? null) : null;
}

/** The steps that show the shared electorate, with examples to switch it. */
export type ExampleSlide = "counts" | "head-to-head" | "ballots";

/** One example on a step: a preset, and on the ballots step a voter type. */
export interface SlideExample {
  presetId: string;
  label: string;
  /** The voter type it selects; unset leaves the first. */
  voterType?: number;
  /** What to notice while the example is showing. */
  note: string;
}
