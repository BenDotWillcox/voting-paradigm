/**
 * The methods page's sections, in slide order. `?section=` names one. Plain
 * data, so the server page can read a link before the client renders.
 */

export const SECTIONS = ["counts", "head-to-head", "ballots", "paradoxes", "atlas", "at-scale"] as const;

export type SectionId = (typeof SECTIONS)[number];

/** The slides that show the shared electorate, with examples to switch it. */
export type ExampleSlide = Extract<SectionId, "counts" | "head-to-head" | "ballots">;

/** One example on a slide: a preset, and on the ballots slide a voter type. */
export interface SlideExample {
  presetId: string;
  label: string;
  /** The voter type it selects; unset leaves the first. */
  voterType?: number;
  /** What to notice while the example is showing. */
  note: string;
}

export function isSection(value: string | undefined): value is SectionId {
  return (SECTIONS as readonly string[]).includes(value ?? "");
}
