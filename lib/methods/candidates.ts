/**
 * Candidates in the methods instrument are abstract: a letter, a glyph
 * shape and a color, always in this order. Shape and letter double-encode
 * the color, so identity never rests on color alone.
 */

export const CANDIDATE_IDS = ["A", "B", "C", "D", "E"] as const;

export type CandidateId = (typeof CANDIDATE_IDS)[number];

export type GlyphShape = "circle" | "triangle" | "square" | "diamond" | "star";

export const MIN_CANDIDATES = 3;
export const MAX_CANDIDATES = CANDIDATE_IDS.length;

const SHAPES: Record<CandidateId, GlyphShape> = {
  A: "circle",
  B: "triangle",
  C: "square",
  D: "diamond",
  E: "star",
};

export function isCandidateId(value: string): value is CandidateId {
  return (CANDIDATE_IDS as readonly string[]).includes(value);
}

export function glyphShape(id: string): GlyphShape {
  return isCandidateId(id) ? SHAPES[id] : "circle";
}

/** The candidate's fill, as a CSS custom property on `.methods-instrument`. */
export function candidateColor(id: string): string {
  return `var(--mi-cand-${id.toLowerCase()})`;
}

/** The first `count` candidates, in order. */
export function candidatesFor(count: number): CandidateId[] {
  return CANDIDATE_IDS.slice(0, count);
}
