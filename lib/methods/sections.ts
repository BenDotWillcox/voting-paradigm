/**
 * The methods page's sections, in slide order. `?section=` names one. Plain
 * data, so the server page can read a link before the client renders.
 */

export const SECTIONS = ["ballots", "counts", "head-to-head", "paradoxes", "atlas", "at-scale"] as const;

export type SectionId = (typeof SECTIONS)[number];

export function isSection(value: string | undefined): value is SectionId {
  return (SECTIONS as readonly string[]).includes(value ?? "");
}
