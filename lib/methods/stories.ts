/**
 * Chapter 3's paradox stories: three of the gallery's smallest specimens,
 * each told as before, the change, and after. The counts come from
 * specimen-resolutions.json, and the copy is written from them. Display only.
 */

import { numberWord } from "@/lib/methods/claims";
import { CRITERIA } from "@/lib/methods/gallery";
import { METHOD_META } from "@/lib/methods/instrument";
import type { StepCopy } from "@/lib/methods/walkthrough";
import type { ProfileMethodResult, ProfileResolveResponse, Specimen } from "@/types/methods";

/** The stories, in step order, each by its gallery specimen. */
export const STORIES = [
  { step: "paradox-spoiler", specimen: "plurality-clones-3c", name: "The spoiler" },
  { step: "paradox-no-show", specimen: "irv-participation-3c", name: "The no-show" },
  { step: "paradox-monotonicity", specimen: "irv-monotonicity-3c", name: "Ranking higher, losing" },
] as const;

export type StoryStep = (typeof STORIES)[number]["step"];

export interface Story {
  step: StoryStep;
  name: string;
  specimen: Specimen;
  /** The failing method's count of the electorate before and after the change. */
  before: ProfileResolveResponse;
  after: ProfileResolveResponse;
}

function counted(resolution: ProfileResolveResponse, story: Story): ProfileMethodResult {
  const found = resolution.results.find((r) => r.method === story.specimen.method);
  if (!found) throw new Error(`No ${story.specimen.method} count for ${story.specimen.id}`);
  return found;
}

/** A count of voters to open a sentence: "Two". */
function voters(count: number): string {
  const word = numberWord(count);
  return word.charAt(0).toUpperCase() + word.slice(1);
}

/** Who goes out first in an instant runoff, if anyone. */
function firstOut(result: ProfileMethodResult): string | null {
  return result.trace.kind === "irv" ? (result.trace.rounds[0]?.eliminated[0] ?? null) : null;
}

export function storyCopy(story: Story): StepCopy {
  const before = counted(story.before, story);
  const after = counted(story.after, story);
  const method = METHOD_META[story.specimen.method].label;
  const criterion = CRITERIA.find((c) => c.id === story.specimen.criterion);
  const t = story.specimen.transformation;
  const transition = `${method} fails ${criterion?.label.toLowerCase() ?? story.specimen.criterion}.`;

  if (t?.kind === "add_clone" && before.trace.kind === "plurality" && after.trace.kind === "plurality") {
    const lead = before.trace.first_choices;
    const split = after.trace.first_choices;
    return {
      transition,
      title: `${story.name}: adding a copy of ${t.candidate} elects ${after.winner}`,
      takeaway: `With two candidates, ${before.winner} beats ${after.winner} ${lead[before.winner]}–${lead[after.winner]}. ${t.clone} joins, a near-copy of ${t.candidate}; ${t.candidate}'s voters split ${split[t.candidate]}–${split[t.clone]}, and ${after.winner} wins with ${split[after.winner]}.`,
    };
  }

  const outBefore = firstOut(before);
  const outAfter = firstOut(after);
  const why =
    outBefore && outAfter && outBefore !== outAfter
      ? ` Before, ${outBefore} went out first and its ballots carried ${before.winner}; after, ${outAfter} goes out first instead, and its ballots carry ${after.winner}.`
      : "";

  if (t?.kind === "add_voters") {
    const last = t.ranking[t.ranking.length - 1];
    return {
      transition,
      title: `${story.name}: more voters, a worse result for them`,
      takeaway: `${voters(t.voters)} more voters turn out, ranking ${t.ranking.join(" › ")}, and ${after.winner}${
        after.winner === last ? ", their last choice," : ""
      } beats ${before.winner}.${why}`,
    };
  }
  if (t?.kind === "raise") {
    return {
      transition,
      title: `${story.name}: moving ${t.candidate} up makes ${t.candidate} lose`,
      takeaway: `${voters(t.voters)} voters move ${t.candidate}, the winner, up their ballots, and ${t.candidate} loses to ${after.winner}.${why}`,
    };
  }
  return {
    transition,
    title: story.name,
    takeaway: `${method} elects ${before.winner}, then ${after.winner}.`,
  };
}

/** The eight criteria in plain words, in three groups. */
export const CRITERION_GROUPS: { title: string; criteria: string[] }[] = [
  { title: "Who should win", criteria: ["majority", "condorcet_winner", "condorcet_loser"] },
  { title: "What should not backfire", criteria: ["monotonicity", "participation"] },
  { title: "What should not matter", criteria: ["consistency", "iia", "clones"] },
];
