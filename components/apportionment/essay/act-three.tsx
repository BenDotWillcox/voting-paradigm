import * as React from "react";

import { ScrollyReveal } from "@/components/story/scrolly-reveal";
import { ScrollySkip } from "@/components/story/scrolly-skip";
import { ScrollyStep } from "@/components/story/scrolly-step";
import type { EssayData } from "@/lib/apportionment/essay-data";
import { citableFact } from "@/lib/apportionment/facts";

import { clipOf } from "./clip";
import { LadderText } from "./deal-figure";
import { FactSources } from "./fact-note";
import type { HouseStep } from "./house-stage";

const MONTANA = "30";
const DELAWARE = "10";

/**
 * Act III, "Dealing the seats": how the 435 are divided after a census. The
 * chamber grows back out of Act II's chart, empty; every state gets its
 * guaranteed seat; one state's claims show the method of equal proportions;
 * seats 51 to 435 are raced for; and whole seats leave districts unequal,
 * which Montana took to the Supreme Court in 1992.
 */
export function actThreeHouseSteps(): HouseStep[] {
  const montanaClip = clipOf(
    citableFact("montana-v-commerce-text"),
    "U.S. Department of Commerce v. Montana · Supreme Court · 1992",
    {
      highlights: [
        { text: "inexorably compels a significant departure from the ideal", at: 0.3 },
        {
          text: "virtually impossible to have the same size district in any pair of States, let alone in all 50",
          at: 0.55,
        },
      ],
    }
  );
  return [
    { year: 2020, label: "2020 census", caption: "Every state gets one seat", deal: { scene: "guarantee" } },
    { year: 2020, deal: { scene: "ladder" } },
    { year: 2020, label: "Seats 51–435", caption: "Each goes to the strongest claim", deal: { scene: "race" } },
    { year: 2020, label: "2020 census", caption: "People per seat, by state", deal: { scene: "spread" } },
    {
      year: 2020,
      label: "1992",
      caption: "U.S. Department of Commerce v. Montana",
      deal: { scene: "spread", spotlight: MONTANA },
      clip: { at: 0, clip: montanaClip },
    },
    {
      year: 2020,
      label: "2020 census",
      caption: "Montana: the lowest average per seat",
      deal: { scene: "spread", spotlight: MONTANA },
    },
  ];
}

/** Act III's words, one <ScrollyStep> per entry of `actThreeHouseSteps`. */
export function ActThreeSteps({ data }: { data: EssayData }) {
  const ordered = [...data.states].sort((a, b) => a.averagePerSeat - b.averagePerSeat);
  const smallest = ordered[0];
  const largest = ordered[ordered.length - 1];
  if (smallest.fips !== MONTANA || largest.fips !== DELAWARE) {
    throw new Error("Act III says Montana has the smallest districts and Delaware the largest");
  }
  const more = Math.round((largest.averagePerSeat / smallest.averagePerSeat - 1) * 100);
  // The race's first award, worked by hand: the two largest states' claims
  // to a second seat.
  const [first, second] = [...data.states].sort((a, b) => b.population - a.population);
  const claim2 = (population: number) => Math.round(population / Math.SQRT2).toLocaleString("en-US");

  return (
    <>
      <ScrollyStep hold={0.7} id="act-3">
        <p>
          After every census, the 435 seats are dealt out again. The
          Constitution guarantees each state one, so the first 50 are spoken
          for.
        </p>
        <FactSources ids={["constitution-apportionment-clause", "priority-values"]} />
      </ScrollyStep>
      <ScrollyStep hold={1}>
        <p>
          The other 385 go one at a time, each to the state with the strongest
          claim to another seat: its population divided by √(<i>n</i>(<i>n</i> − 1)),
          where <i>n</i> is the seat it would get.
        </p>
        <ScrollyReveal at={0.35}>
          <p>
            <LadderText />
          </p>
        </ScrollyReveal>
        <ScrollyReveal at={0.65}>
          <p className="font-sans text-sm text-story-ink-2">
            √(<i>n</i>(<i>n</i> − 1)) is the geometric mean of <i>n</i> − 1 and <i>n</i>. Dividing
            by it is the method of equal proportions, the law since 1941.
          </p>
          <FactSources ids={["priority-values", "equal-proportions-1941"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={2.4}>
        <p>
          Then the race. Seat 51 goes to the strongest claim to a second seat:{" "}
          {first.name}’s, {first.population.toLocaleString("en-US")} ÷ √2 = {claim2(first.population)}, ahead
          of {second.name}’s {claim2(second.population)}. The winner’s next claim, a weaker one,
          drops back into the pack, and the strongest claim wins again.
        </p>
        <p data-scroll-hint="" className="font-sans text-sm text-story-muted">
          Keep scrolling to deal each seat, at your own pace, or{" "}
          <ScrollySkip>skip to the result</ScrollySkip>.
        </p>
        <ScrollyReveal at={0.88}>
          <p>
            By the end, the leading claims are nearly tied. Seat 435 goes to
            Minnesota, for its eighth seat, just ahead of New York and Ohio.
          </p>
          <FactSources ids={["seat-435-2020"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.7}>
        <p>
          Seats only come whole, so the average number of people per seat
          can’t come out equal across states.
        </p>
        <ScrollyReveal at={0.3}>
          <p>
            Using the 2020 census, {largest.name} averages {largest.averagePerSeat.toLocaleString("en-US")}{" "}
            people per House seat; {smallest.name} averages{" "}
            {smallest.averagePerSeat.toLocaleString("en-US")}.
          </p>
          <FactSources ids={["per-seat-spread-2020"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.8}>
        <p>
          Montana took this to court. The 1990 census had cost it its second
          seat, leaving one district of 803,655 people.
        </p>
        <ScrollyReveal at={0.4}>
          <p>
            In 1992 the Supreme Court ruled against Montana unanimously. The
            method was within Congress’s power, and equal districts across the
            states were “virtually impossible.”
          </p>
          <FactSources ids={["montana-v-commerce", "montana-v-commerce-text"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.6}>
        <p className="font-story-serif text-3xl font-medium leading-tight tracking-[-0.01em] sm:text-4xl">
          After 2020, Montana got its second seat back.
        </p>
        <p>
          It now has the lowest average per seat of any state. {largest.name}, the highest, has{" "}
          {more} percent more people per seat.
        </p>
        <FactSources ids={["montana-seat-history", "per-seat-spread-2020"]} />
      </ScrollyStep>
    </>
  );
}
