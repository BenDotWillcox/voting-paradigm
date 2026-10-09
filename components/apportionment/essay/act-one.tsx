import * as React from "react";

import { ScrollyReveal } from "@/components/story/scrolly-reveal";
import { ScrollyStep } from "@/components/story/scrolly-step";
import type { EssayData } from "@/lib/apportionment/essay-data";
import { citableFact } from "@/lib/apportionment/facts";

import { clipOf } from "./clip";
import { ConstituencyText } from "./constituency";
import { FactSources } from "./fact-note";
import type { HouseStep } from "./house-stage";

/**
 * Act I, "The Representation Gap": one person, then everyone who shares
 * their representative, then the question of scale, then the House across
 * its history until 1913, ending as the country keeps growing past a House
 * that stopped. Its steps open the stage (see HouseStory); primary sources
 * come in front of the chamber as clips. Every number comes from the build
 * artifacts and every historical claim and quote from facts.json.
 */
export function actOneHouseSteps(data: EssayData): HouseStep[] {
  const present = data.history[data.history.length - 1];
  const censusYears = data.history
    .filter((a) => a.year >= 1790 && a.year <= 1910 && a.reapportioned)
    .map((a) => a.year);
  if (!data.history.some((a) => a.year === 1787)) throw new Error("History is missing the 1787 allocation");

  const constitutionClip = clipOf(
    citableFact("constitution-apportionment-clause"),
    "U.S. Constitution, Article I, Section 2 · 1787",
    {
      highlights: [
        { text: "The Number of Representatives shall not exceed one for every thirty Thousand", at: 0.55 },
        { text: "each State shall have at Least one Representative", at: 0.7 },
      ],
      // The operative clause; the original allocation by state is in the
      // full passage.
      excerpt: [
        "The Number of Representatives shall not exceed one for every thirty Thousand, but each State shall have at Least one Representative",
      ],
    }
  );
  const federalistClip = clipOf(
    citableFact("federalist-58-growth"),
    "The Federalist No. 58 · James Madison · 1788",
    {
      highlights: [
        {
          text: "the number of members will not be augmented from time to time, as the progress of population may demand",
          at: 0.1,
        },
        {
          text: "the greater the number composing them may be, the fewer will be the men who will in fact direct their proceedings",
          at: 0.5,
        },
      ],
    }
  );
  const amendmentClip = clipOf(
    citableFact("article-the-first-text"),
    "Article the first, as Congress sent it to the states · September 25, 1789",
    {
      highlights: [{ text: "nor more than one Representative for every fifty thousand persons", at: 0.25 }],
      excerpt: [
        "After the first enumeration required by the first article of the Constitution, there shall be one Representative for every thirty thousand",
        "after which the proportion shall be so regulated by Congress, that there shall not be less than two hundred Representatives, nor more than one Representative for every fifty thousand persons.",
      ],
      stamp: { text: "Never ratified", at: 0.6 },
      moreSources: [citableFact("twelve-amendments-ten-ratified")],
    }
  );

  // One entry per scrolly step from the third on (the first two are the crowd).
  return [
    { year: present.year },
    { year: 1787, clip: { at: 0.45, clip: constitutionClip } },
    { year: 1787, clip: { at: 0, clip: federalistClip } },
    { year: 1787, caption: "The first proposed amendment", clip: { at: 0, clip: amendmentClip } },
    // Back from the amendment at the First Congress, so growth starts at 65.
    { years: [1787, ...censusYears] },
    { year: 1910, label: "1913", caption: "The first House with 435 seats" },
    // Act II tells the 1920 story; here the chamber simply stays put.
    { years: [1910, 1920], caption: "The House: still 435 seats", tear: true },
  ];
}

/** Act I's words, one <ScrollyStep> per entry of the figure's steps. */
export function ActOneSteps({ data, nationalAverage }: { data: EssayData; nationalAverage: number }) {
  // The last beat: the country grows from 1910 to 1920 while the House holds.
  const before = data.history.find((a) => a.year === 1910);
  const after = data.history.find((a) => a.year === 1920);
  if (!before?.residentPopulation || !after?.residentPopulation || before.houseSize !== after.houseSize) {
    throw new Error("Act I's last step needs 1910 and 1920 populations and an unchanged House");
  }
  const millions = (n: number | null) =>
    ((n ?? 0) / 1_000_000).toLocaleString("en-US", { maximumFractionDigits: 1 });

  return (
    <>
      <ScrollyStep hold={1.8} id="act-1">
        <p>
          <ConstituencyText part="first-person" nationalAverage={nationalAverage} />
        </p>
        <p>
          Zoom out to the neighbors: 100 people, then 1,000. Every one of
          them has a life as full as this one.
        </p>
        <ScrollyReveal at={0.47}>
          <p>
            By 10,000 people, a single person is too small to see. From here
            on, each dot stands for 1,000 people.
          </p>
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={1}>
        <ConstituencyText part="final-labels" nationalAverage={nationalAverage} />
        <p className="mt-3">
          <ConstituencyText part="final" nationalAverage={nationalAverage} />
        </p>
        <FactSources ids={["at-large-district-population-2020", "state-average-per-seat-2020"]} />
      </ScrollyStep>

      <ScrollyStep hold={0.3}>
        <p>
          We hand government to representatives because none of us can do it
          all. But a representative can only hear so many people. Using the
          2020 census, each one answers to about 761,000 on average.
        </p>
        <p className="font-story-serif text-3xl font-medium leading-tight tracking-[-0.01em] sm:text-4xl">
          How many people should one representative speak for?
        </p>
        <FactSources ids={["national-average-per-seat-2020"]} />
      </ScrollyStep>
      <ScrollyStep hold={0.6}>
        <p>
          The argument is older than the first census. Could the House stay
          close enough to understand the people, yet small enough to do its
          business?
        </p>
        <ScrollyReveal at={0.45}>
          <p>
            The Constitution capped it at one representative for every 30,000
            people, and gave every state at least one.
          </p>
          <FactSources ids={["first-congress-65", "constitution-apportionment-clause"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.6}>
        <p>
          One fear was that the country would outgrow the House. In
          Federalist 58, James Madison answered it.
        </p>
        <ScrollyReveal at={0.5}>
          <p>
            He also warned that in a larger assembly, fewer people might end
            up directing its work.
          </p>
          <FactSources ids={["federalist-58-growth"]} />
        </ScrollyReveal>
      </ScrollyStep>
      <ScrollyStep hold={0.8}>
        <p className="font-story-serif text-2xl font-medium leading-tight tracking-[-0.01em] sm:text-3xl">
          The first proposed amendment concerned representation.
        </p>
        <p>
          In 1789, Congress sent twelve proposed amendments to the states. The
          first set rules for the size of the House.
        </p>
        <ScrollyReveal at={0.6}>
          <p>Ten became the Bill of Rights. The apportionment amendment was never ratified.</p>
          <FactSources
            ids={["article-the-first-text", "twelve-amendments-ten-ratified", "article-the-first-not-ratified"]}
          />
        </ScrollyReveal>
      </ScrollyStep>

      <ScrollyStep hold={1.3}>
        <p>For more than a century, Congress repeatedly enlarged the House.</p>
        <p data-scroll-hint="" className="font-sans text-sm text-story-muted">
          Keep scrolling to move through each census.
        </p>
        <FactSources ids={["house-growth-1790-1910"]} />
      </ScrollyStep>
      <ScrollyStep>
        <p>As the country grew, the House grew.</p>
        <p className="font-sans text-sm text-story-ink-2">
          The Apportionment Act of 1911 set 433 seats, with one more each for
          Arizona and New Mexico when they were admitted. The 63rd Congress,
          which began in 1913, was the first with 435 members.
        </p>
        <FactSources ids={["apportionment-act-1911", "house-435-from-1913"]} />
      </ScrollyStep>
      <ScrollyStep hold={0.8}>
        <p className="font-story-serif text-3xl font-medium leading-tight sm:text-4xl">
          The country kept growing. The House did not.
        </p>
        <p>
          Between the {before.year} and {after.year} censuses, the population grew from{" "}
          {millions(before.residentPopulation)} million to {millions(after.residentPopulation)} million.
          The House stayed at {after.houseSize} seats.
        </p>
        <FactSources ids={["population-1910-1920"]} />
      </ScrollyStep>
    </>
  );
}
