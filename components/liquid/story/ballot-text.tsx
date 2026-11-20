import { district, pct, resident } from "@/lib/liquid/format";
import type { Arrangement, BallotCode, LevelKey, StoryCity } from "@/lib/liquid/story-types";

/** Whose ballot counted for a resident on the featured question, in words. */
export function whoseBallot(city: StoryCity, key: LevelKey, arrangement: Arrangement, voter: number): string {
  const code = city.levels[key].codes[arrangement][voter] as BallotCode;
  const own = code === "M" || code === "N";
  if (own) {
    if (arrangement === "liquid" && city.levels[key].liquid_resolver[voter] === voter) {
      return code === "M" ? "Their own: they decide this topic, and voted" : "Their own: they decide this topic, but did not vote";
    }
    if (arrangement === "representative") {
      return code === "M" ? "Their own: they are the representative" : "Their own, as representative: they did not vote";
    }
    return code === "M" ? "Their own: they voted" : "None: they did not vote";
  }
  switch (arrangement) {
    case "representative":
      return `Their representative's (${resident(city.representatives[city.district[voter]])})`;
    case "proxy":
      return "Their proxy's";
    case "liquid": {
      const by = city.levels[key].liquid_resolver[voter];
      return `${resident(by)}'s, through their delegation for this topic`;
    }
    default:
      return "Someone else's";
  }
}

const OUTCOME: Record<BallotCode, string> = {
  M: "Matches them",
  m: "Matches them",
  c: "Against them",
  N: "No ballot counted",
  n: "No ballot counted: the person deciding did not vote",
};

/** The hover card for one resident under one arrangement. */
export function BallotTooltip({
  city,
  levelKey,
  arrangement,
  voter,
}: {
  city: StoryCity;
  levelKey: LevelKey;
  arrangement: Arrangement;
  voter: number;
}) {
  const code = city.levels[levelKey].codes[arrangement][voter] as BallotCode;
  return (
    <div className="space-y-0.5 font-sans">
      <div className="font-semibold">
        {resident(voter)} · {district(city.district[voter])}
      </div>
      <div className="text-story-ink-2">Votes on {pct(city.turnout[levelKey][voter] / 1000, 0)} of questions</div>
      <div>Ballot: {whoseBallot(city, levelKey, arrangement, voter)}</div>
      <div className="font-medium">{OUTCOME[code]}</div>
    </div>
  );
}
