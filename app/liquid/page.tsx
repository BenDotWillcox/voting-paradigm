import type { Metadata } from "next";
import Link from "next/link";
import * as React from "react";

import { AppSection } from "@/components/liquid/story/app-section";
import { ClaimLabel, type Claim } from "@/components/liquid/story/claim-label";
import { DesignScene } from "@/components/liquid/story/design-scene";
import {
  BallotArrivesFigure,
  VotesTravelFigure,
  WhoDecidesFigure,
} from "@/components/liquid/story/delegation-scene";
import { RouterFigure } from "@/components/liquid/story/costs-figure";
import { EmptyRecordFigure, LoopFigure, LostVoteFigure } from "@/components/liquid/story/breaks-scene";
import { ExplainerVideo } from "@/components/liquid/story/explainer-video";
import { AgentScene, CeilingScene, ColdStartScene, RoutingScene } from "@/components/liquid/story/limits-scene";
import { OneResident } from "@/components/liquid/story/one-resident";
import { StructureFigure, VoteEndToEndFigure } from "@/components/liquid/story/structures-scene";
import { PlaneFigure } from "@/components/liquid/story/plane";
import { ResultFigure } from "@/components/liquid/story/result-figure";
import {
  LiquidFigure,
  LiquidHeading,
  LiquidText,
  STUDY_HREF,
  StudyLinks,
} from "@/components/liquid/story/section-heading";
import { Reveal } from "@/components/liquid/story/stage";
import { StoryDataProvider } from "@/components/liquid/story/story-data";
import { ThreeWaysFigure } from "@/components/liquid/story/three-ways";
import { TurnoutProvider } from "@/components/liquid/story/turnout";
import { EXPLAINER_VIDEO } from "@/lib/liquid/explainer-video";
import { dec, pct, resident, share } from "@/lib/liquid/format";
import { loadLiquidStory } from "@/lib/liquid/story-data";
import { levelKey, topicLabel } from "@/lib/liquid/story-types";

export const metadata: Metadata = {
  title: "Who Votes for You? · Liquid democracy",
  description:
    "Liquid delegation lets you hand each kind of decision to someone you choose. How it works, where it breaks, and what we would build to fix it, from a pre-registered simulation of 200 cities.",
};

/** The published repository, for the benchmarks and the design doc. */
const REPOSITORY = "https://github.com/BenDotWillcox/voting-paradigm/tree/main";

/** The story's three parts after the opening, for the row that skips to them. */
const PARTS = [
  { id: "breaks", label: "Where the machinery breaks" },
  { id: "struggles", label: "Where it's still hard" },
  { id: "build", label: "What we'd build" },
] as const;

/** A small heading inside a part. */
function Beat({ children, className }: { children: React.ReactNode; className?: string }) {
  return <h3 className={`pt-4 text-lg font-semibold text-story-ink ${className ?? ""}`}>{children}</h3>;
}

/** The fix or answer that follows a problem, with its label and the evidence for it. */
function Fix({
  title = "The fix",
  claim = "proposal",
  children,
  evidence,
}: {
  title?: string;
  claim?: Claim;
  children: React.ReactNode;
  evidence: React.ReactNode;
}) {
  return (
    <div className="space-y-2 border-l-2 border-story-rule pl-4 text-story-ink-2">
      <p>
        <span className="mr-1.5 font-medium text-story-ink">{title}</span>
        <span className="mr-1.5 inline-block align-middle">
          <ClaimLabel claim={claim} />
        </span>
        {children}
      </p>
      <p className="text-sm">
        <span className="font-medium text-story-ink">Evidence:</span> {evidence}
      </p>
    </div>
  );
}

const NOT_YET = "None yet: untested here.";

/** A difference in points, unsigned: 0.178 -> "17.8". */
function pts(value: number): string {
  return (100 * value).toFixed(1);
}

/**
 * Demo 5: "Who Votes for You?", the liquid-democracy story
 * (prompts/demo-5-walkthrough.md, "The story" and "The video opening and the
 * trim"). The opening carries Ben's video on the idea, with a readable
 * version of it below: the idea and the basic mechanism, as if everyone
 * votes. Then three parts: the breaks real turnout opens, each with its fix;
 * the limits no rule settles, each with our answer, where the verdict lands;
 * and what we'd build, ending in the app. It shows highlights only; every
 * part links to the full study at /liquid/study.
 * Plain for now: the styling comes once the core is built. Static: every
 * number comes from public/data/liquid-story/. Only the account app talks to
 * the Python service, from the browser.
 */
export default async function LiquidStoryPage() {
  const { measures, results, exploratory, city } = await loadLiquidStory();
  const { protocol } = measures;
  const swiss = protocol.swiss_marker;
  const { design } = city;
  const m = city.mechanism;

  // Parts 1 and 2: the everyone-votes reference point (exploratory)
  const everyone = exploratory.everyone_votes;
  const e = everyone.measures;
  const topicList = city.topics.map((t) => topicLabel(t).toLowerCase());

  // Parts 3 and 4: every quoted value read from the frozen summaries
  const grid = protocol.turnout_grid;
  const result = (l: number) => results.levels[levelKey(l)];
  const measured = (l: number) => measures.levels[levelKey(l)];
  const at = measured(swiss);
  const { threshold, rules, router, sweeps } = results;
  const lowest = grid[0];
  const highest = grid[grid.length - 1];
  const worthwhile = grid.filter((l) => result(l).size === "gain of at least delta established");
  const failing = grid.filter((l) => result(l).h1.estimate > 0 && result(l).cap_share < rules.feasible_share);
  /** A share as quoted: 7.5%, 4%, 98.5%. */
  const quoted = (value: number) => pct(value, Math.round(value * 1000) % 10 ? 1 : 0);
  const ladder = result(swiss).decomposition;
  const emptyFidelity = grid.map((l) => measured(l).liquid.empty_record_fidelity ?? 0);
  const passed = grid.findIndex((l) => measured(l).direct.fidelity > measured(l).liquid.fidelity);
  const [beforePass, afterPass] = [grid[passed - 1], grid[passed]];
  const sweepLead = (point: string) => sweeps.points[point].levels[levelKey(swiss)].h1;
  const sweepPanel = (title: string) => sweeps.panels.find((panel) => panel.title.startsWith(title))?.series ?? [];
  const shortestHistory = sweepPanel("History")[0];
  const evenKey = sweepPanel("Turnout spread")[0].point;
  const operating = router.operating;
  // The fallback study (R2): the representative as default
  const fallback = exploratory.fallback;
  const defaulted = (l: number) => fallback.levels[levelKey(l)];

  // The ceiling's exploratory evidence, and the agent's bars
  const handoverAt = (l: number) => exploratory.handover.levels[levelKey(l)];
  const rises = (l: number) => handoverAt(l).every((p, i, all) => i === 0 || p.fidelity > all[i - 1].fidelity);
  const lastRise = grid.filter(rises).slice(-1)[0];
  const firstFall = grid[grid.indexOf(lastRise) + 1];
  const highCurve = handoverAt(highest);
  const agentBars = exploratory.agent_bars.levels[levelKey(swiss)];
  const video = EXPLAINER_VIDEO;

  return (
    <>
      <div className="story liquid-story min-h-screen pb-24">
        <StoryDataProvider measures={measures} results={results} exploratory={exploratory} city={city}>
          <TurnoutProvider levels={grid} swiss={swiss}>
            {/* The opening: the question, the video, and a way past it. The answer waits for part 2. */}
            <header id="top" className="mx-auto max-w-2xl px-4 pt-14 pb-6">
              <p className="text-sm font-medium text-story-muted">Demo 05 · Liquid democracy</p>
              <h1 className="mt-3 text-4xl font-semibold tracking-tight text-balance text-story-ink sm:text-5xl">
                Who Votes for You?
              </h1>
              <p className="mt-4 text-lg leading-relaxed text-story-ink-2">
                Liquid delegation lets you hand each kind of decision to someone you choose, and keep the rest. Can
                people hand most of their civic decisions to delegates they choose, and still be represented better
                than by an elected representative?
              </p>
              <p className="mt-4 leading-relaxed text-story-ink-2">
                This page shows how liquid delegation works, where it breaks, and what we would build to fix it. The
                answer comes from a test declared before {protocol.cities} synthetic cities were run, and part 2 gives
                it.
              </p>
              {video ? <ExplainerVideo video={video} /> : null}
              <nav aria-label="Skip ahead" className="mt-8 text-sm text-story-ink-2 [&_a]:underline [&_a]:underline-offset-4">
                <p>
                  <span className="font-medium text-story-ink">Already know liquid democracy? Skip to:</span>{" "}
                  {PARTS.map((part, index) => (
                    <React.Fragment key={part.id}>
                      {index > 0 ? <span aria-hidden="true"> · </span> : null}
                      <a href={`#${part.id}`} className="hover:text-story-ink">
                        {part.label}
                      </a>
                    </React.Fragment>
                  ))}
                  <span aria-hidden="true"> · </span>
                  <a href="#app" className="hover:text-story-ink">
                    The app
                  </a>
                </p>
                <p className="mt-2">
                  <Link href={STUDY_HREF}>Read the full study</Link>
                </p>
              </nav>
            </header>

            {/*
              The video's readable version: the idea and the basic version, as if everyone votes. Closed while
              the video is there, open until it is. The dial arrives in part 1.
            */}
            <details id="read" open={!video} className="group/read mt-6">
              <summary className="mx-auto max-w-2xl cursor-pointer list-none px-4 [&::-webkit-details-marker]:hidden">
                <span className="inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium text-story-ink ring-1 ring-story-rule hover:bg-story-surface">
                  <span aria-hidden="true" className="inline-block transition-transform group-open/read:rotate-90">
                    ▸
                  </span>
                  {video
                    ? "Prefer reading? The idea and the basic version, in text and animation"
                    : "The idea and the basic version, as if everyone votes"}
                </span>
              </summary>
            <TurnoutProvider
              levels={grid}
              swiss={swiss}
              everyone
              fixed="Everyone votes here. You set the turnout from part 1."
            >
              {/* The idea */}
              <LiquidHeading id="idea" kicker="The idea" claim="exploratory">
                Between voting on everything and handing everything over
              </LiquidHeading>
              <LiquidText>
                <p>
                  Start with a city where everyone votes on every question they are asked. There are several ways to
                  turn what its residents want into decisions, and each asks a different amount of them.
                </p>
              </LiquidText>
              <LiquidFigure>
                <VoteEndToEndFigure />
              </LiquidFigure>
              <LiquidText>
                <p>
                  Each arrangement below changes one thing: whose ballot counts for you. The figures follow one
                  resident, {resident(city.everyone.typical.voter)}, and their {design.topics} topics, each in its own
                  colour. Under each, two bars: <strong>fidelity</strong>, how often the ballot counted for you
                  matches what you want, and <strong>overhead</strong>, how many questions you decide yourself.
                </p>
                <Beat>Direct voting</Beat>
                <p>
                  Everyone decides every question themself. Every ballot is the voter&apos;s own, so it always matches
                  what they want. But the work is the problem: every resident decides every question.
                </p>
              </LiquidText>
              <LiquidFigure>
                <StructureFigure kind="direct" />
              </LiquidFigure>
              <LiquidText>
                <Beat>A district representative</Beat>
                <p>
                  Each district elects one person, who votes on every question for everyone in it. Residents decide
                  almost nothing themselves, but the representative&apos;s ballot matches a resident on only{" "}
                  {pct(e.representative.fidelity)} of their questions. Representation costs fidelity twice:
                </p>
                <ul>
                  <li>
                    <em>Dilution:</em> you share the representative with your whole district, whose views differ from
                    yours, and they were elected by all of it.
                  </li>
                  <li>
                    <em>Bundling:</em> one person stands for you on every issue, and you will not agree with anyone on
                    everything.
                  </li>
                </ul>
              </LiquidText>
              <LiquidFigure>
                <StructureFigure kind="representative" />
              </LiquidFigure>
              <LiquidText>
                <Beat>A proxy you choose</Beat>
                <p>
                  Instead of sharing a representative, each resident picks their own person, anyone in the city, to
                  vote for them on everything. That removes dilution: the proxy&apos;s ballots match on{" "}
                  {pct(e.proxy.fidelity)} of questions.
                </p>
              </LiquidText>
              <LiquidFigure>
                <StructureFigure kind="proxy" />
              </LiquidFigure>
              <LiquidText>
                <Beat>Liquid delegation</Beat>
                <p>
                  Liquid delegation picks a person for each topic, so it removes bundling too. Its ballots match on{" "}
                  {pct(e.liquid.fidelity)} of questions, {pts(everyone.contrasts.h1.estimate)} points more
                  than the representative. Most of that gain comes from choosing your own person at all: splitting the
                  choice by topic adds {pts(everyone.contrasts.specialisation.estimate)} of them.
                </p>
              </LiquidText>
              <LiquidFigure>
                <StructureFigure kind="liquid" />
              </LiquidFigure>
              <LiquidText>
                <Beat className="pt-0">The trade-off, on two measures</Beat>
                <p>
                  The two bars are the trade-off. <strong>Fidelity</strong> is the share of your questions on which
                  the ballot counted for you matches what you would have chosen. <strong>Overhead</strong> is the
                  share you decide yourself: the work an arrangement asks of you. Direct voting scores 100% on both.
                </p>
                <p>
                  Liquid delegation aims between the corners: far less work than voting on everything yourself, and
                  more faithful than a representative. Here residents decide {pct(e.liquid.overhead)} of their
                  questions themselves under liquid delegation, against {pct(e.direct.overhead, 0)} under direct voting
                  and {pct(e.representative.overhead, 0)} under a representative.
                </p>
              </LiquidText>
              <LiquidFigure>
                <OneResident />
              </LiquidFigure>
              <LiquidFigure>
                <PlaneFigure />
              </LiquidFigure>
              <LiquidText>
                <p className="text-sm text-story-ink-2">
                  <span className="font-medium text-story-ink">* What this assumes.</span> Everything here has
                  everyone voting on every question, and residents choosing delegates by how often they have agreed in
                  the past. Neither holds in a real city: part 1 drops the first assumption and part 2 the second.
                  These numbers come from an analysis made after the study&apos;s test was fixed. They describe the
                  setting and test nothing.
                </p>
                <Beat>The city</Beat>
                <p>
                  To measure all this we built synthetic cities. Each has {design.residents} residents in{" "}
                  {design.districts} districts, with views drawn from a model fitted to the CES 2024 survey of American
                  voters, and {design.topics} topics, each with a public record of {design.history_per_topic} past
                  votes. The study ran {protocol.cities} such cities. Each figure&apos;s dots are one of them.
                </p>
              </LiquidText>
              <StudyLinks
                links={[
                  { anchor: "three-ways", label: "Three ways to be represented" },
                  { anchor: "city", label: "The city" },
                  { anchor: "measures", label: "Two measures" },
                  { anchor: "plane", label: "Five arrangements on one plane" },
                ]}
              />

              {/* How it works: the basic version */}
              <LiquidHeading id="how" kicker="How it works" claim="illustration">
                The basic version
              </LiquidHeading>
              <LiquidText>
                <p>
                  Liquid delegation runs on a few rules. This is the version most proposals share, still with everyone
                  voting.
                </p>
                <Beat>Topics are fixed in advance</Beat>
                <p>
                  The city agrees on a list of topics. Ours have {design.topics}: {topicList.slice(0, -1).join(", ")}{" "}
                  and {topicList[topicList.length - 1]}. Every question on a ballot arrives tagged with one of them.
                </p>
                <Beat>For each topic, you name a delegate or keep it</Beat>
                <p>
                  You can hand any topic to anyone in the city, and take it back at any time. In the basic version you
                  pick someone you trust. The simulated residents cannot trust anyone, so they pick by record: the
                  person whose past votes on that topic agree with theirs most, as long as there is enough record to
                  tell. Part 2 shows how.
                </p>
                <Beat>A ballot arrives</Beat>
                <p>
                  Each question goes where its topic says. A question in a topic you delegated goes to your delegate,
                  and the rest come to you. Once you hand a topic over, your own ballot on it does not count, even if
                  you cast one. Some systems let your own vote replace your delegate&apos;s; the study does not model
                  that.
                </p>
              </LiquidText>
              <LiquidFigure>
                <BallotArrivesFigure />
              </LiquidFigure>
              <LiquidText>
                <Beat className="pt-0">Votes travel on</Beat>
                <p>
                  Your delegate&apos;s own delegations apply to the votes they hold. If your housing delegate has
                  handed housing to someone else, your vote goes there too, so a vote can pass through several people
                  before someone decides it.
                </p>
              </LiquidText>
              <LiquidFigure>
                <VotesTravelFigure />
              </LiquidFigure>
              <LiquidText>
                <Beat className="pt-0">Who ends up deciding</Beat>
                <p>
                  Everyone who decides a question casts one ballot, and it counts for everyone whose vote reached them.
                  Votes gather around the people many others agree with on a topic. That is the mechanism working: with
                  everyone voting, the largest single decider holds {pct(e.liquid.mean_largest_share ?? 0)} of a
                  question&apos;s votes on average, against a district representative&apos;s{" "}
                  {pct(e.representative.mean_largest_share ?? 0, 0)}.
                </p>
                <p>
                  The study files every question under its true topic. Filing real questions is the first problem in
                  part 2.
                </p>
              </LiquidText>
              <LiquidFigure>
                <WhoDecidesFigure />
              </LiquidFigure>
              <StudyLinks links={[{ anchor: "how", label: "How it works" }]} />
            </TurnoutProvider>
            </details>

            {/* The two measures every later figure reads in */}
            <LiquidText className="mt-12">
              <div className="rounded-lg bg-story-surface p-5 ring-1 ring-story-rule">
                <p className="text-xs font-medium tracking-wide text-story-ink-2 uppercase">Two measures, throughout</p>
                <p className="mt-2">
                  <strong>Fidelity</strong> is how often the ballot counted for you matches what you would have chosen.{" "}
                  <strong>Overhead</strong> is the share of questions you decide yourself: the work an arrangement asks
                  of you.
                </p>
                <p className="mt-2 text-story-ink-2">
                  Liquid delegation aims for less overhead than direct voting and more fidelity than a district
                  representative.
                </p>
              </div>
            </LiquidText>

            {/* Part 1. Where the machinery breaks, and the fix for each. Its dials start at everyone votes. */}
            <TurnoutProvider levels={grid} swiss={swiss} everyoneStop>
            <LiquidHeading id="breaks" kicker="Part 1 · Where the machinery breaks" claim="frozen">
              Real people miss votes
            </LiquidHeading>
            <LiquidText>
              <p>
                So far everyone voted. Real people miss votes. In the study each resident votes at their own rate,
                some almost never and some almost always, around a city-wide average. That one change opens gaps in
                the rules. Each break below says what goes wrong, how often, and the fix we would build.
              </p>
              <p>
                From here you set the turnout with the dial under each figure. It starts with everyone voting, marked
                All; the average levels run from {lowest} to {highest}, and {swiss} is Swiss turnout. At Swiss turnout, voting yourself is never wrong but usually absent:{" "}
                {pct(at.direct.none_share)} of a resident&apos;s questions carry no ballot for them. A representative
                leaves {pct(at.representative.none_share)} empty, and liquid delegation {pct(at.liquid.none_share)}.
              </p>
            </LiquidText>
            <LiquidFigure>
              <ThreeWaysFigure />
            </LiquidFigure>

            <LiquidText>
              <Beat>A delegate who does not vote</Beat>
              <p>
                A delegate votes at their own rate, like anyone else. One who skips a question leaves every vote they
                hold on it uncast. At Swiss turnout that loses {pct(at.liquid.lost_share ?? 0)} of delegated votes, and{" "}
                {pct(measured(lowest).liquid.lost_share ?? 0)} at {lowest}. Whoever holds someone else&apos;s vote at
                Swiss turnout casts it {pct(at.liquid.resolver_attendance ?? 0, 0)} of the time.
              </p>
            </LiquidText>
            <LiquidFigure>
              <LostVoteFigure />
            </LiquidFigure>
            <LiquidText>
              <Fix
                title="The fixes"
                evidence={
                  <>
                    <span className="mr-1 inline-block align-middle">
                      <ClaimLabel claim="exploratory" />
                    </span>
                    The fallback study tested the representative as default: at {lowest}, votes with no ballot fall
                    from {pct(measured(lowest).liquid.none_share)} to {pct(defaulted(lowest).liquid_default.none_share ?? 0)}.
                    The backup delegate and the personal agent are untested.
                  </>
                }
              >
                Catch the vote: you vote yourself, a backup delegate takes it (an existing idea known as ranked
                delegation), the district representative takes it as the last default, or a personal agent casts it.
              </Fix>

              <Beat>Nobody to delegate to</Beat>
              <p>
                A resident who never votes has no record, so there is nobody to choose by. They keep every topic and
                rarely use it. At {lowest}, {pct(measured(lowest).liquid.empty_record_share ?? 0)} of residents have
                an empty record, and they are nearly all of liquid&apos;s {pct(measured(lowest).liquid.overhead)}{" "}
                overhead there.
              </p>
              <p>
                They are barely represented: their fidelity under liquid is between{" "}
                {Math.min(...emptyFidelity).toFixed(3)} and {Math.max(...emptyFidelity).toFixed(3)} at every level,
                against about {dec(at.representative.empty_record_fidelity ?? 0, 2)} under the representative. One
                chosen proxy for everything has the same floor, so the cause is choosing by record, not delegating by
                topic.
              </p>
              <Fix
                evidence={
                  <>
                    <span className="mr-1 inline-block align-middle">
                      <ClaimLabel claim="exploratory" />
                    </span>
                    Tested in the fallback study, declared before it ran, and {fallback.outcome}: at{" "}
                    {fallback.hypothesis_levels.join(", ")}, liquid with the default leads the representative by{" "}
                    {fallback.hypothesis_levels.map((l) => pts(defaulted(l).h1.estimate)).join(", ")} points, and{" "}
                    {pct(Math.min(...fallback.hypothesis_levels.map((l) => defaulted(l).cap_share)), 0)} of cities stay
                    under the cap. At {lowest}, residents with no record go from{" "}
                    {pct(measured(lowest).liquid.empty_record_fidelity ?? 0)} fidelity to{" "}
                    {pct(defaulted(lowest).liquid_default.empty_record_fidelity ?? 0)}.
                  </>
                }
              >
                The representative as default delegate: anyone with no delegate for a topic is represented by their
                district&apos;s representative rather than not at all. A backup delegate cannot help here: it is
                chosen from the same record.
              </Fix>
            </LiquidText>
            <LiquidFigure>
              <EmptyRecordFigure />
            </LiquidFigure>

            <LiquidText>
              <Beat>Loops</Beat>
              <p>
                When nearly everyone hands a topic over, chains have nowhere to end but a loop: people who have handed
                the topic to each other. In this city at Swiss turnout,{" "}
                {share(m.handed_pairs_ending_on_loop, m.handed_pairs)} of handed-over votes end at one.
              </p>
            </LiquidText>
            <LiquidFigure>
              <LoopFigure />
            </LiquidFigure>
            <LiquidText>
              <p>
                The cost is work handed back, and it grows as turnout rises. At {lowest},{" "}
                {pct(measured(lowest).liquid.loop_share ?? 0)} of all voter-question pairs sit on a loop; at Swiss
                turnout {pct(at.liquid.loop_share ?? 0)}; at {highest}, {pct(measured(highest).liquid.loop_share ?? 0)},
                which is all of liquid&apos;s overhead there; and with everyone voting, {pct(e.liquid.loop_share ?? 0)}.
              </p>
              <Fix title="The rule" claim="design" evidence="Applied in the frozen study, so no vote on a loop is lost.">
                From the literature: everyone on a loop decides for themself.
              </Fix>
              <Fix evidence={NOT_YET}>
                A backup delegate outside the loop could take that work over, but at high turnout it costs fidelity.
                At {highest}, a delegated vote matches {pct(measured(highest).liquid.fidelity_resolved ?? 0, 0)} of the
                time, while a resident voting for themself matches about {pct(measured(highest).direct.fidelity, 0)}.
                Whether it helps depends on turnout, and part 2 takes that up.
              </Fix>
            </LiquidText>
            <StudyLinks
              links={[
                { anchor: "edges", label: "The two edges" },
                { anchor: "attendance", label: "Delegates who don't show up" },
                { anchor: "how", label: "How it works" },
              ]}
            />
            </TurnoutProvider>

            {/* Part 2. Where it's still hard, and our answer to each */}
            <LiquidHeading id="struggles" kicker="Part 2 · Where it's still hard" claim="frozen">
              Three limits no rule settles
            </LiquidHeading>
            <LiquidText>
              <p>
                Each break in part 1 has a rule that closes it. Three limits remain that no rule settles: filing
                questions under topics, building the history people choose by, and getting enough people to vote.
                Each comes with the answer we would build and the bar it must clear.
              </p>
              <Beat>Strict categories</Beat>
              <p>
                Real questions do not arrive tagged, and one question can touch several topics. Filing them is a
                judgment, and it can go wrong either way: a false delegation sends a vote to someone it was not meant
                for and costs fidelity; a false keep leaves a vote with its owner and costs overhead.
              </p>
              <Fix title="Our answer" evidence={<>Measured on the router benchmark, below.</>}>
                A decision model that reads each question against the categories a voter wrote in their own words,
                and keeps the question with the voter when it is unsure. At its operating threshold, {operating.threshold}
                , {pct(operating.false_delegation_rate)} of the votes it sends on go to a category they are not about,
                and it keeps {pct(operating.false_keep_rate)} of the votes that had a fitting category.
              </Fix>
            </LiquidText>
            <LiquidFigure>
              <RoutingScene />
            </LiquidFigure>
            <LiquidFigure>
              <Reveal>
                <RouterFigure />
              </Reveal>
            </LiquidFigure>

            <LiquidText>
              <Beat>The initial history</Beat>
              <p>
                Choosing by record needs a record. The simulated residents line up every other resident&apos;s past
                votes on a topic against their own and count the agreements. Candidates are ranked by a cautious
                estimate, the lower end of a credible interval, so a short record counts for less than a long one, and
                the topic goes to the best candidate only if that estimate clears the city&apos;s acceptance level.
                Each city sets that level as strictly as it can while keeping overhead on past questions at or under{" "}
                {pct(m.cap, 0)}.
              </p>
              <p>
                <strong>The cold start.</strong> Before anyone can choose by record, the record has to be built, and
                meanwhile everyone decides every question. Counting that history, liquid&apos;s overhead at Swiss
                turnout is {pct(at.liquid.lifecycle_overhead ?? 0, 0)} instead of {pct(at.liquid.overhead, 0)}, and the
                figure depends on how long the city runs after its history. With a history of only{" "}
                {shortestHistory.label} questions per topic, too few cities stay within the {pct(rules.cap, 0)} limit
                at any level.
              </p>
            </LiquidText>
            <LiquidFigure>
              <ColdStartScene />
            </LiquidFigure>
            <LiquidText>
              <Fix
                title="Our answers"
                evidence="The fallback study tested the default against a mature record, not a launch; the agent is untested."
              >
                The representative as default lets a city start as representative democracy while records build,
                though a resident who never votes still never builds one. And a personal agent, a model of the voter
                built from one interview (the preference elicitation of demo 2), could cast the ballots they would
                leave empty. Its bars at Swiss turnout: its ballots must match the voter more than{" "}
                {pct(agentBars.representative)} of the time to beat a representative default, and more than{" "}
                {pct(agentBars.delegate)} to beat a chosen delegate. No accuracy is claimed, and one model serving
                everyone would share its errors across every ballot it casts.
              </Fix>
            </LiquidText>
            <LiquidFigure>
              <AgentScene />
            </LiquidFigure>
            <LiquidText>
              <Beat className="pt-0">Turnout: how much is enough</Beat>
              <p>
                This is the question the study was built to answer. Liquid delegation overtakes the district
                representative near turnout {dec(threshold.crossing, 2)}; the 95% range for where it crosses runs from{" "}
                {threshold.confidence[0]} to {threshold.confidence[1]}. At Swiss turnout it is{" "}
                {pts(result(swiss).h1.estimate)} points ahead, and at every level from {worthwhile[0]} to{" "}
                {worthwhile[worthwhile.length - 1]} the lead clears {100 * rules.delta} points, the smallest lead the
                study set out to count as worthwhile.
              </p>
              <p>
                The test had one more condition: at every level where liquid leads, at least{" "}
                {pct(rules.feasible_share, 0)} of cities must keep its overhead at or under {pct(rules.cap, 0)}.{" "}
                {failing
                  .map((l, i) => `${i === 0 ? "Only " : ""}${quoted(result(l).cap_share)}${i === 0 ? " do" : ""} at ${l}`)
                  .join(" and ")}
                .
              </p>
            </LiquidText>
            <LiquidText className="mt-6">
              <div className="rounded-lg bg-story-surface p-5 ring-1 ring-story-rule">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium tracking-wide text-story-ink-2 uppercase">
                    The pre-registered verdict
                  </span>
                  <ClaimLabel claim="frozen" />
                </div>
                <p className="mt-1 text-lg font-semibold text-story-ink">
                  &ldquo;{measures.verdict.text.charAt(0).toUpperCase() + measures.verdict.text.slice(1)}.&rdquo;
                </p>
                <p className="mt-3 text-xs font-medium tracking-wide text-story-ink-2 uppercase">How we know</p>
                <ul className="mt-2 text-sm text-story-ink-2">
                  <li>
                    The hypothesis, the measures and the rules for reading them were fixed on {protocol.frozen}, before
                    any city ran, and the runs were made from commit <code>{protocol.commit.slice(0, 7)}</code>.
                  </li>
                  <li>
                    {protocol.cities} cities, each run at every turnout level with the same residents, and a further set
                    of sweeps changing one setting at a time.
                  </li>
                  <li>The verdict is quoted word for word, including the condition that was not met.</li>
                </ul>
              </div>
            </LiquidText>
            <LiquidFigure>
              <Reveal>
                <ResultFigure />
              </Reveal>
            </LiquidFigure>
            <LiquidText>
              <p>
                The two ends fail for opposite reasons. The low end is part 1&apos;s empty record, which the
                representative as default closes in the fallback study. At the high end, the
                city-wide limit pushes people who would vote into delegating: direct voting, with full overhead,
                passes liquid between {beforePass} ({dec(measured(beforePass).direct.fidelity)} against{" "}
                {dec(measured(beforePass).liquid.fidelity)}) and {afterPass} (
                {dec(measured(afterPass).direct.fidelity)} against {dec(measured(afterPass).liquid.fidelity)}).
              </p>
              <p>
                Where the lead comes from: at Swiss turnout, having one chosen delegate for everything adds{" "}
                {pts(ladder.city_wide_proxy_combined.estimate)} of the{" "}
                {pts(ladder.h1.estimate)} points, and topic delegates add{" "}
                {pts(ladder.specialisation.estimate)}, as with everyone voting.
              </p>
              <p>
                Concentration grows as turnout falls. The largest single decider holds{" "}
                {pct(measured(highest).liquid.mean_largest_share ?? 0)} of a question&apos;s votes on average at{" "}
                {highest}, {pct(at.liquid.mean_largest_share ?? 0)} at Swiss turnout and{" "}
                {pct(measured(lowest).liquid.mean_largest_share ?? 0)} at {lowest}: fewer people voting leaves fewer
                people for trust to flow to. The risk that stays open is capture, because someone holding many votes
                is a cheap target for lobbying.
              </p>
              <Fix
                title="Our answer for the high end"
                evidence={
                  <>
                    <span className="mr-1 inline-block align-middle">
                      <ClaimLabel claim="exploratory" />
                    </span>
                    An analysis made after the freeze hands over one more topic at a time. Up to {lastRise}, every topic
                    handed over raises fidelity. From {firstFall} it does not: at {highest}, every topic handed over
                    lowers it, from {dec(highCurve[0].fidelity)} to {dec(highCurve[highCurve.length - 1].fidelity)}.
                  </>
                }
              >
                A ceiling set by each voter instead of one city-wide limit, so people keep the questions they would
                answer themselves.
              </Fix>
            </LiquidText>
            <LiquidFigure>
              <CeilingScene />
            </LiquidFigure>
            <LiquidText>
              <Beat className="pt-0">What delegation cannot change</Beat>
              <p>
                <strong>It borrows engagement; it does not create it.</strong> Liquid delegation moves votes from
                people who rarely vote to people who often do. In an electorate where nearly everyone votes sometimes,
                the lead at Swiss turnout falls to {pts(sweepLead(evenKey))} points and the crossing moves
                to about {dec(sweeps.points[evenKey].crossing ?? 0, 2)}.
              </p>
              <p>
                <strong>Better for individuals, not for outcomes.</strong> Whether an arrangement picks the winner the
                whole city would pick if everyone voted is a different question from fidelity. At Swiss turnout direct
                voting matches it on {pct(at.direct.outcome_agreement ?? 0)} of questions, liquid on{" "}
                {pct(at.liquid.outcome_agreement ?? 0)} and the representative on{" "}
                {pct(at.representative.outcome_agreement ?? 0)}.
              </p>
              <p>
                <span className="mr-1.5 inline-block align-middle">
                  <ClaimLabel claim="exploratory" />
                </span>
                An interpretation the study did not test: random abstention is a fair sample, so the voters who turn up
                decide as the whole city would. Delegation instead copies one person&apos;s deviations onto everyone
                who follows them. The largest caveat on any outcome claim: in this model turnout is independent of
                opinion, and real abstention is not.
              </p>
              <p>None of our proposals creates engagement.</p>
            </LiquidText>
            <StudyLinks
              links={[
                { anchor: "how", label: "How delegates are chosen" },
                { anchor: "result", label: "The result" },
                { anchor: "ladder", label: "Where the lead comes from" },
                { anchor: "costs", label: "Costs the headline does not show" },
                { anchor: "sweeps", label: "What the lead depends on" },
                { anchor: "exploratory", label: "What overhead is worth" },
                { anchor: "outcomes", label: "Individuals and outcomes" },
              ]}
            />

            {/* Part 3. What we'd build */}
            <LiquidHeading id="build" kicker="Part 3 · What we'd build" claim="proposal">
              The fixes, together
            </LiquidHeading>
            <LiquidText>
              <p>
                Put together, the fixes make a system someone could build: the basic version, with every fix from
                parts 1 and 2 in place. Follow one vote through it.
              </p>
            </LiquidText>
            <LiquidFigure>
              <DesignScene />
            </LiquidFigure>
            <LiquidText>
              <p>
                <strong>What none of them fixes:</strong> liquid delegation still borrows engagement rather than
                creating it, and its outcomes still drift further from full turnout than direct voting&apos;s.
              </p>
            </LiquidText>
            <StudyLinks links={[{ anchor: "proposals", label: "What could be built" }]} />
          </TurnoutProvider>
        </StoryDataProvider>
      </div>

      {/* Part 3's payoff: the account app */}
      <section id="app" className="mx-auto max-w-7xl scroll-mt-4 px-4 pb-16 sm:px-6">
        <div className="mb-6 max-w-3xl space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-semibold tracking-[0.18em] text-indigo-700 uppercase dark:text-indigo-300">
              Try it · Liquid democracy
            </p>
            <span className="rounded-full px-2 py-0.5 text-[0.7rem] font-medium text-muted-foreground ring-1 ring-border">
              Illustration
            </span>
          </div>
          <h2 className="text-3xl font-semibold tracking-tight">An account in a city that votes this way</h2>
          <p className="leading-relaxed text-muted-foreground">
            A design idea, not part of the study&apos;s claim. This is a separate, smaller city of 240 residents, where
            you write your own categories in plain words and a decision model files each question under them. The
            people, their delegations and the votes are made up; the routing is real. The fixes above are not built
            into it yet.
          </p>
        </div>
        <AppSection />
      </section>

      {/* The close */}
      <div className="story liquid-story pb-24">
        <LiquidHeading id="left-out" kicker="What is left out" claim="design">
          What this study does not model
        </LiquidHeading>
        <LiquidText className="[&_code]:[overflow-wrap:anywhere]">
          <ul>
            <li>
              <strong>What representatives do</strong> besides voting: deliberation, setting the agenda, brokering
              across issues.
            </li>
            <li>
              <strong>Behaviour:</strong> strategic voting, campaigns, and preferences that change.
            </li>
            <li>
              <strong>Questions of unequal weight.</strong> Every question counts the same.
            </li>
            <li>
              <strong>Real cities and real routing.</strong> The cities are synthetic, and every question reaches the
              right topic.
            </li>
            <li>
              <strong>Turnout that depends on opinion.</strong> Here it does not.
            </li>
          </ul>
          <p>
            <Link href={STUDY_HREF}>The full study</Link> has every figure, interval and table, and the methods. The
            published benchmark is{" "}
            <a href={`${REPOSITORY}/eval/benchmarks/delegation_frontier_v1`}>
              <code>eval/benchmarks/delegation_frontier_v1</code>
            </a>
            , the everyone-votes reference point is{" "}
            <a href={`${REPOSITORY}/eval/benchmarks/delegation_everyone_votes_v1`}>
              <code>eval/benchmarks/delegation_everyone_votes_v1</code>
            </a>
            , and the design is in{" "}
            <a href={`${REPOSITORY}/prompts/demo-5-liquid-democracy.md`}>
              <code>prompts/demo-5-liquid-democracy.md</code>
            </a>
            .
          </p>
        </LiquidText>
      </div>
    </>
  );
}
