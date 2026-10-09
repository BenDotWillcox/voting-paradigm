import * as React from "react";

import { ScrollyReveal } from "@/components/story/scrolly-reveal";
import { ScrollyStep } from "@/components/story/scrolly-step";
import { SWEEP_START, SWEEP_STOP, awardOrder, sizeSweep } from "@/lib/apportionment-sweep";
import { citableFact } from "@/lib/apportionment/facts";
import { US_2020_APPORTIONMENT_POPULATIONS as POPULATIONS } from "@/lib/us-state-populations";

import { clipOf } from "./clip";
import { FactSources } from "./fact-note";
import type { HouseStep } from "./house-stage";

/** Salary plus the average office allowance (CRS, 2026); see fact member-cost. */
const COST_PER_MEMBER = 2_102_107;
const TOTAL = Object.values(POPULATIONS).reduce((sum, n) => sum + n, 0);

/**
 * Act IV, "Just add seats?": the same states at each proposed House size,
 * keeping two gaps apart throughout (how many people a member represents,
 * and how unequal that is across states), then every size from 435 to
 * 11,036, then what a bigger House costs, how other democracies compare,
 * and what the arithmetic cannot settle. Numbers come from the sweep
 * (identical to the build's house-sizes.json) and the fact register.
 */
export function actFourHouseSteps(): HouseStep[] {
  const federalistClip = clipOf(citableFact("federalist-55"), "The Federalist No. 55 · 1788", {
    highlights: [
      { text: "passion never fails to wrest the sceptre from reason", at: 0.3 },
      { text: "every Athenian assembly would still have been a mob", at: 0.55 },
    ],
  });
  return [
    { year: 2020, label: "435 seats", caption: "Today’s House", bigger: { scene: "swarm", size: 435 } },
    { year: 2020, label: "573 seats", caption: "The Wyoming Rule", bigger: { scene: "swarm", size: 573 } },
    { year: 2020, label: "692 seats", caption: "The cube-root rule", bigger: { scene: "swarm", size: 692 } },
    { year: 2020, label: "1,000 seats", caption: "A round thousand", bigger: { scene: "swarm", size: 1000 } },
    {
      year: 2020,
      label: "11,036 seats",
      caption: "The 30,000-person benchmark",
      bigger: { scene: "swarm", size: 11_036 },
    },
    { year: 2020, label: "Every size", caption: "From 435 to 11,036 seats", bigger: { scene: "envelope" } },
    { year: 2020, label: "1,000 seats", caption: "What a bigger House costs", bigger: { scene: "chamber", size: 1000 } },
    { year: 2020, label: "11,036 seats", caption: "What a bigger House costs", bigger: { scene: "chamber", size: 11_036 } },
    { year: 2020, label: "2018", caption: "Other democracies", bigger: { scene: "peers" } },
    {
      year: 2020,
      label: "1788",
      caption: "The Federalist No. 55",
      bigger: { scene: "chamber", size: 11_036 },
      clip: { at: 0, clip: federalistClip },
    },
    { year: 2020, label: "1,000 seats", caption: "What the arithmetic shows", bigger: { scene: "swarm", size: 1000 } },
    { year: 2020, label: "435 seats", caption: "Today’s House", bigger: { scene: "chamber", size: 435 } },
  ];
}

/** Act IV's words, one <ScrollyStep> per entry of `actFourHouseSteps`. */
export function ActFourSteps() {
  const order = awardOrder(POPULATIONS, SWEEP_STOP);
  const sweep = sizeSweep(POPULATIONS, order, SWEEP_START, SWEEP_STOP);
  const at = (size: number) => sweep[size - SWEEP_START];
  const pct = (share: number) => Math.round(Math.abs(share) * 100);
  // How much smaller the average constituency is than at 435 seats (1,000
  // seats is exactly 56.5%, which floating point puts a hair under: round
  // half up, as the fact register does).
  const shrink = (size: number) => Math.round((1 - SWEEP_START / size) * 100 + 1e-9);
  const average = (size: number) => (Math.round(TOTAL / size / 1000) * 1000).toLocaleString("en-US");
  const today = at(435);
  const wyoming = at(573);
  const cube = at(692);
  const thousand = at(1000);
  const limit = at(SWEEP_STOP);
  const spike = at(810);
  const billions = (amount: number) => (amount / 1e9).toFixed(amount < 1e10 ? 2 : 1);
  // The copy's comparisons, checked against the numbers it is written from.
  if (!(wyoming.high > today.high && spike.ratio > cube.ratio && limit.high < 0.0215 && limit.low > -0.02)) {
    throw new Error("Act IV's copy no longer matches the sweep");
  }

  return (
    <>
      <ScrollyStep hold={0.6} id="act-4">
        <p>
          The fix proposed most often is simply a bigger House. Would more
          seats close the representation gap?
        </p>
        <ScrollyReveal at={0.35}>
          <p>
            There are two gaps to watch: how many people each member
            represents, and how unequal that number is across states. Using the
            2020 census, the average is 761,169 people per seat; the highest
            state average is {pct(today.high)} percent above it and the lowest{" "}
            {pct(today.low)} percent below.
          </p>
          <FactSources ids={["national-average-per-seat-2020", "add-seats-extremes"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.6}>
        <p>
          The Wyoming Rule would size the House so the average number of
          people per seat matches the population of the smallest state,
          Wyoming: 573 seats.
        </p>
        <ScrollyReveal at={0.4}>
          <p>
            The average per seat would fall {shrink(573)} percent, to about {average(573)}. But
            the extremes barely move: the highest state average would be{" "}
            {pct(wyoming.high)} percent above the national one, further out than today.
          </p>
          <FactSources ids={["wyoming-rule", "wyoming-rule-2020-size", "constituency-shrink", "add-seats-extremes"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.6}>
        <p>
          Political scientists have observed that lower houses tend to track
          the cube root of a country’s population. For the United States that
          would be 692 seats.
        </p>
        <ScrollyReveal at={0.4}>
          <p>
            At 692 seats, the average constituency would shrink by {shrink(692)} percent. But the
            disparity between the highest and lowest state averages would barely change:{" "}
            {cube.ratio.toFixed(2)} times, against {today.ratio.toFixed(2)} today.
          </p>
          <FactSources ids={["cube-root-law", "constituency-shrink", "add-seats-extremes"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.6}>
        <p>
          At 1,000 seats the average falls {shrink(1000)} percent, to about {average(1000)}, and
          the disparity finally narrows: the highest state average is {pct(thousand.high)} percent
          above the national one, the lowest {pct(thousand.low)} percent below.
        </p>
        <FactSources ids={["constituency-shrink", "add-seats-extremes"]} />
      </ScrollyStep>
      <ScrollyStep hold={0.9}>
        <p>
          Read as a national ratio, the Constitution’s cap of one
          representative per 30,000 people would allow up to 11,036 seats using
          the 2020 census. The average would fall {shrink(SWEEP_STOP)} percent, and every state
          average would land within about 2 percent of the national one.
        </p>
        <ScrollyReveal at={0.4}>
          <p>
            That is a benchmark, not a settled limit. George Washington’s first
            veto, in 1792, applied the cap state by state; at 11,036 seats, 23
            states would average fewer than 30,000 people per seat. And the
            2 percent mark comes much earlier, at 6,279 seats, with thousands of
            larger sizes slipping back past it.
          </p>
          <FactSources
            ids={[
              "article-one-limit-2020",
              "washington-veto-1792",
              "thirty-thousand-per-state-2020",
              "two-percent-threshold",
            ]}
          />
        </ScrollyReveal>
      </ScrollyStep>

      <ScrollyStep hold={1.2}>
        <p>
          In between, more seats don’t steadily help. The disparity between
          the highest and lowest state averages stays wide until about 1,000
          seats, and at 810 seats it is wider than at 692.
        </p>
        <ScrollyReveal at={0.5}>
          <p>
            The extremes are always small states. Up to 1,000 seats, the
            highest and lowest averages belong to states with five seats or
            fewer, where one seat more or less moves the average a long way: a
            state that goes from one seat to two halves it.
          </p>
        </ScrollyReveal>
        <ScrollyReveal at={0.75}>
          <p>
            The typical state gets closer to the average overall, from{" "}
            {(today.typical * 100).toFixed(1)} percent off today to {(thousand.typical * 100).toFixed(1)}{" "}
            percent at 1,000 seats, but not seat by seat: 303 of the 565
            single-seat additions in that range widen its gap. House size
            produces a jagged trade-off, not a smooth curve.
          </p>
          <FactSources ids={["add-seats-extremes", "extremes-small-states", "typical-gap"]} />
        </ScrollyReveal>
      </ScrollyStep>

      <ScrollyStep hold={0.7}>
        <p>
          A bigger House also costs more. Holding today’s resources per member
          constant, which is an estimate rather than a forecast, each
          representative costs about $2.1 million a year in salary and office
          allowance and may hire up to 18 permanent staff.
        </p>
        <ScrollyReveal at={0.4}>
          <p>
            At 1,000 seats that comes to ${billions(1000 * COST_PER_MEMBER)} billion a year in all,
            ${billions((1000 - 435) * COST_PER_MEMBER)} billion more than today.
          </p>
          <FactSources ids={["member-salary-2026", "mra-2026", "mra-staff-limit", "member-cost"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.6}>
        <p>
          At the 30,000-person benchmark, 11,036 members would cost about $
          {billions(SWEEP_STOP * COST_PER_MEMBER)} billion a year on the same terms, $
          {billions((SWEEP_STOP - 435) * COST_PER_MEMBER)} billion more than today, and could hire
          up to 198,648 permanent staff.
        </p>
        <FactSources ids={["member-cost"]} />
      </ScrollyStep>
      <ScrollyStep hold={0.7}>
        <p>
          Other democracies draw the line very differently. In 2018 the United
          States had the most people per lower-house seat of the 35 OECD
          countries, nearly three times as many as Japan, the next highest.
          Eight of them had larger lower chambers than the House; Germany’s
          Bundestag was the largest, with 709 members.
        </p>
        <FactSources ids={["oecd-ratio-2018"]} />
      </ScrollyStep>
      <ScrollyStep hold={0.7}>
        <p>
          The founders also argued about the opposite danger: an assembly
          grown too large to deliberate. That is an argument about how
          assemblies behave, not a measured limit.
        </p>
        <FactSources ids={["federalist-55"]} />
      </ScrollyStep>
      <ScrollyStep hold={0.8}>
        <p>
          What this arithmetic establishes is narrow: a larger House means
          fewer people per member, and it shifts the population disparities
          between states, unevenly.
        </p>
        <ScrollyReveal at={0.3}>
          <p>
            What it cannot establish is whether members would be more
            responsive, accessible or accountable, or whether the House would
            deliberate better or worse. That turns on how much constituent
            service each office can provide, how committees divide and
            specialize the work, how floor time is rationed, and how much
            control shifts to party leaders: questions that need evidence
            beyond population counts.
          </p>
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.6}>
        <p className="font-story-serif text-3xl font-medium leading-tight tracking-[-0.01em] sm:text-4xl">
          A larger House reliably shrinks the number of people each member
          represents.
        </p>
        <p>
          It narrows the gaps between states only unevenly, and it brings
          institutional costs that population arithmetic alone cannot settle.
        </p>
      </ScrollyStep>
    </>
  );
}
