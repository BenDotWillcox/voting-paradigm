import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { RepresentationGapChart } from "@/components/apportionment/story/representation-gap-chart";
import { Scrolly } from "@/components/story/scrolly";
import { ScrollyStep } from "@/components/story/scrolly-step";
import {
  BigNumber,
  Prose,
  SectionHeading,
  StoryHeader,
  StoryRoot,
} from "@/components/story/story-layout";
import { StoryFigure } from "@/components/story/story-figure";
import { houseSizeSnapshot } from "@/lib/story/representation-gap";

export const metadata: Metadata = {
  title: "Story kit · Nebula Civitas",
  robots: { index: false, follow: false },
};

const STEPS = [
  { cap: 435, label: "Today" },
  { cap: 574, label: "Wyoming Rule" },
  { cap: 1_000, label: "A thousand seats" },
  { cap: 11_037, label: "Article I ratio" },
] as const;

/**
 * Living reference for the story kit (components/story), built on real
 * apportionment data. Available locally and on Vercel previews; hidden on
 * the production deployment.
 */
export default function StoryKitPage() {
  if (process.env.VERCEL_ENV === "production") notFound();

  const snapshots = STEPS.map((step) => houseSizeSnapshot(step.cap));
  const [today, wyoming, thousand, article] = snapshots;
  const within5 = (snapshot: (typeof snapshots)[number]) =>
    snapshot.states.filter((state) => Math.abs(state.deviation) <= 0.05).length;
  const people = (n: number) => Math.round(n).toLocaleString("en-US");

  return (
    <StoryRoot>
      <StoryHeader
        kicker="Story kit · reference page"
        title="Unequal by arithmetic"
        dek="A working sample of the storytelling components: editorial header, prose, a pinned scrollytelling figure, a hero number, and a figure with source line and data table."
        meta="Not linked from the site. Hidden on the production deployment."
      />

      <Prose>
        <p>
          Every state gets at least one representative, and seats must be whole
          numbers. With only 435 seats to share among 331 million people, that
          rounding produces districts of very different sizes: a vote for the
          House counts for more in some states than in others.
        </p>
        <p>
          Scroll to grow the House. Each dot is a state, placed by how far its
          districts sit from the national average.
        </p>
      </Prose>

      <Scrolly
        label="District size by state as the House grows"
        graphic={
          <RepresentationGapChart
            snapshots={snapshots}
            labels={STEPS.map((step) => step.label)}
          />
        }
      >
        <ScrollyStep>
          <p>
            At <strong>435 seats</strong>, a representative from{" "}
            {today.largest.name} serves {people(today.largest.perSeat)} people.
            One from {today.smallest.name} serves{" "}
            {people(today.smallest.perSeat)}: a {today.ratio.toFixed(2)}× gap.
          </p>
        </ScrollyStep>
        <ScrollyStep>
          <p>
            The <strong>Wyoming Rule</strong> sizes districts to the smallest
            state, giving {wyoming.cap} seats. Most states move closer to the
            average, but the extremes barely move: {wyoming.largest.name} versus{" "}
            {wyoming.smallest.name} is still a {wyoming.ratio.toFixed(2)}× gap.
          </p>
          <p>
            States with one or two seats dominate the rounding error, and a
            modest increase doesn&rsquo;t give them enough seats to round well.
          </p>
        </ScrollyStep>
        <ScrollyStep>
          <p>
            At <strong>{thousand.cap.toLocaleString("en-US")} seats</strong> the
            spread finally collapses: the gap falls to{" "}
            {thousand.ratio.toFixed(2)}×, and {within5(thousand)} of 50 states are
            within 5% of the average.
          </p>
        </ScrollyStep>
        <ScrollyStep>
          <p>
            At Article I&rsquo;s limit of one representative per 30,000
            people, <strong>{article.cap.toLocaleString("en-US")} seats</strong>,
            rounding nearly disappears: a {article.ratio.toFixed(2)}× gap, with
            every state within {Math.ceil(Math.max(...article.states.map((st) => Math.abs(st.deviation))) * 100)}% of
            the average.
          </p>
        </ScrollyStep>
      </Scrolly>

      <BigNumber
        value={`${today.ratio.toFixed(2)}×`}
        label={`The gap between the largest and smallest House districts today: ${today.largest.name} versus ${today.smallest.name}.`}
        note="People per representative, 2020 apportionment."
      />

      <SectionHeading kicker="Figure">The gap by House size</SectionHeading>
      <div className="mx-auto mt-8 max-w-[38rem] px-4">
        <StoryFigure
          title="Largest vs. smallest district"
          subtitle="Ratio of people per representative, largest state to smallest"
          source="2020 Census apportionment counts"
          table={{
            columns: [
              { key: "cap", label: "House size", numeric: true },
              { key: "largest", label: "Largest districts" },
              { key: "smallest", label: "Smallest districts" },
              { key: "ratio", label: "Ratio", numeric: true },
            ],
            rows: snapshots.map((s) => ({
              cap: s.cap,
              largest: `${s.largest.name} (${people(s.largest.perSeat)})`,
              smallest: `${s.smallest.name} (${people(s.smallest.perSeat)})`,
              ratio: `${s.ratio.toFixed(2)}×`,
            })),
          }}
        >
          <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
            {snapshots.map((s, i) => (
              <div key={s.cap}>
                <dt className="text-xs text-story-muted">{STEPS[i].label}</dt>
                <dd className="mt-1 text-2xl font-semibold text-story-ink">
                  {s.ratio.toFixed(2)}×
                </dd>
                <dd className="text-xs text-story-ink-2 tabular-nums">
                  {s.cap.toLocaleString("en-US")} seats
                </dd>
              </div>
            ))}
          </dl>
        </StoryFigure>
      </div>
    </StoryRoot>
  );
}
