import * as React from "react";

import { ScrollyReveal } from "@/components/story/scrolly-reveal";
import { ScrollyStep } from "@/components/story/scrolly-step";
import type { EssayData } from "@/lib/apportionment/essay-data";
import { citableFact } from "@/lib/apportionment/facts";

import { clipOf } from "./clip";
import { FactSources } from "./fact-note";
import { FREEZE_YEAR, perSeatSeries } from "./freeze-chart";
import type { HouseStep } from "./house-stage";

/** The first census after the House reached 435: the one it never acted on. */
const DEADLOCK = 1920;

/**
 * Act II, "The freeze": the 1920 census the House never acted on, the 1929
 * act that made apportionment automatic at whatever size the House already
 * was, and what that has meant for a seat since. It continues on Act I's
 * stage: the locked chamber, then the act as a clip, then the chamber
 * shrinks into the legend of a people-per-seat chart drawn census by census.
 */
export function actTwoHouseSteps(data: EssayData): HouseStep[] {
  const actClip = clipOf(
    citableFact("permanent-apportionment-act-1929-text"),
    "Permanent Apportionment Act, sec. 22 · June 18, 1929",
    {
      highlights: [
        { text: "the then existing number of Representatives", at: 0.35 },
        { text: "fails to enact a law apportioning Representatives among the several States", at: 0.55 },
        { text: "each State shall be entitled", at: 0.7 },
      ],
      excerpt: [
        "the number of Representatives to which each State would be entitled under an apportionment of the then existing number of Representatives",
        "(b) If the Congress to which the statement required by subdivision (a) of this section is transmitted, fails to enact a law apportioning Representatives among the several States, then each State shall be entitled, in the second succeeding Congress and in each Congress thereafter until the taking effect of a reapportionment under this Act or subsequent statute, to the number of Representatives shown in the statement",
      ],
    }
  );
  const frozenYears = data.history.filter((a) => a.year > DEADLOCK).map((a) => a.year);
  const present = frozenYears[frozenYears.length - 1];

  return [
    { year: DEADLOCK, lock: true },
    { year: DEADLOCK, label: "1929", caption: "The Permanent Apportionment Act", lock: true, clip: { at: 0, clip: actClip } },
    {
      year: DEADLOCK,
      label: `1790–${DEADLOCK}`,
      caption: "People per House seat at each census",
      chart: { through: DEADLOCK, morph: true },
    },
    { years: frozenYears, chart: { from: DEADLOCK, through: present } },
    { year: present, label: `${present} census`, caption: "Still 435 seats", chart: { from: present, through: present } },
  ];
}

/** Act II's words, one <ScrollyStep> per entry of `actTwoHouseSteps`. */
export function ActTwoSteps({ data }: { data: EssayData }) {
  const series = perSeatSeries(data.history);
  const at = (year: number) => {
    const point = series.find((p) => p.year === year);
    if (!point) throw new Error(`No people-per-seat figure for ${year}`);
    return point.perSeat;
  };
  const about = (n: number) => (Math.round(n / 1000) * 1000).toLocaleString("en-US");
  const first = series[0];
  const final = series[series.length - 1];
  if (at(final.year) / at(DEADLOCK) <= 3) throw new Error("The essay says people per seat more than tripled");

  return (
    <>
      <ScrollyStep hold={0.5} id="act-2">
        <p>
          The 1920 census was the first to count more Americans in cities than
          in rural areas: 51.2 percent. Apportionment had been slowly shifting
          seats from smaller rural states to larger urban ones. Now rural and
          urban factions fought over it, and Congress could not agree.
        </p>
        <ScrollyReveal at={0.4}>
          <p>
            For the only time in its history, the House did not reapportion
            itself after a census.
          </p>
          <FactSources ids={["urban-majority-1920", "rural-urban-apportionment-shift", "no-reapportionment-1920"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.8}>
        <p>
          In 1929, Congress made sure it would never be stuck again. The
          Permanent Apportionment Act never names a size for the House.
        </p>
        <ScrollyReveal at={0.35}>
          <p>
            After each census it divides up “the then existing number of
            Representatives,” which was 435. If Congress passes nothing, that
            division takes effect on its own.
          </p>
          <FactSources ids={["permanent-apportionment-act-1929-text", "permanent-apportionment-act-1929"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.8}>
        <p>
          Here is what the freeze means for a single seat. Each point is a
          census: how many people shared one seat in the House.
        </p>
        <ScrollyReveal at={0.6}>
          <p>
            The House grew, but it was already growing more slowly than the
            population: people per seat rose from about {about(first.perSeat)} in {first.year} to
            about {about(at(FREEZE_YEAR))} in {FREEZE_YEAR}. The freeze stopped even that partial
            adjustment.
          </p>
          <FactSources ids={["house-growth-1790-1910"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={1.3}>
        <p>
          Since then the House has stayed at 435. Every census has added
          people, not seats.
        </p>
        <ScrollyReveal at={0.12}>
          <p>In 1941, Congress settled the method too: equal proportions, still the law today.</p>
          <p className="font-sans text-sm text-story-ink-2">
            Admitting Alaska and Hawaii briefly raised the House to 437 seats;
            it went back to 435 after the 1960 census.
          </p>
          <FactSources ids={["equal-proportions-1941", "temporary-437"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.5}>
        <p className="font-story-serif text-3xl font-medium leading-tight tracking-[-0.01em] sm:text-4xl">
          By {final.year}, one seat for every {final.perSeat.toLocaleString("en-US")} people.
        </p>
        <p>More than three times as many as in {DEADLOCK}.</p>
        <FactSources ids={["national-average-per-seat-2020", "per-seat-1920-2020"]} />
      </ScrollyStep>
    </>
  );
}
