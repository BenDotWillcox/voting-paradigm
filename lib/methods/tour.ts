import type { SpecimenRole } from "@/types/methods";

export type TourTarget =
  | { kind: "preset"; id: string }
  | { kind: "specimen"; id: string; role: SpecimenRole }
  | { kind: "free" };

export interface TourStep {
  title: string;
  caption: string;
  target: TourTarget;
}

/**
 * The tour: two presets, then three gallery specimens, then the reader's
 * turn. It is an index into the gallery, not separate content.
 */
export const TOUR: TourStep[] = [
  {
    title: "Majority cycle",
    caption:
      "Fifteen voters, and every candidate loses one head-to-head race, so majority rule has no answer. The seven counts pick three different winners.",
    target: { kind: "preset", id: "majority-cycle" },
  },
  {
    title: "Center squeeze",
    caption:
      "C beats both rivals head to head but has the fewest first choices. Plurality and instant runoff never see it; every method that reads whole rankings or ratings elects C.",
    target: { kind: "preset", id: "center-squeeze" },
  },
  {
    title: "Spoiler",
    caption:
      "Plurality elects A. Remove C, who loses anyway, and B wins: C's voters prefer B, and C was splitting the vote against A.",
    target: { kind: "specimen", id: "plurality-iia-3c", role: "before" },
  },
  {
    title: "Teaming",
    caption:
      "Borda elects A over B. Add C, a clone every voter ranks right next to B, and B wins: on B voters' ballots the clone sits between B and A and widens B's lead, while on A voters' ballots it sits last and changes nothing.",
    target: { kind: "specimen", id: "borda-clones-3c", role: "before" },
  },
  {
    title: "Monotonicity",
    caption:
      "Instant runoff elects A. Two voters raise A to first, and A loses: C drops below B in first choices, is eliminated instead, and C's voters elect B.",
    target: { kind: "specimen", id: "irv-monotonicity-3c", role: "before" },
  },
  {
    title: "Your turn",
    caption:
      "Move voters, add candidates, or open any cell of the gallery below. Every failure there is the smallest example a search could find.",
    target: { kind: "free" },
  },
];
