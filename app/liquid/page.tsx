import type { Metadata } from "next";

import { AppSection } from "@/components/liquid/story/app-section";
import { ClaimLabel } from "@/components/liquid/story/claim-label";
import { CalibrationFigure, CandidatesFigure, ChainFigure, RoutingFigure } from "@/components/liquid/story/mechanism";
import { OneResident } from "@/components/liquid/story/one-resident";
import { PlaneFigure } from "@/components/liquid/story/plane";
import { LiquidFigure, LiquidHeading, LiquidText } from "@/components/liquid/story/section-heading";
import { StoryDataProvider } from "@/components/liquid/story/story-data";
import { ThreeWaysFigure } from "@/components/liquid/story/three-ways";
import { TurnoutProvider } from "@/components/liquid/story/turnout";
import { TurnoutCity } from "@/components/liquid/story/turnout-city";
import { dec, pct, resident, share } from "@/lib/liquid/format";
import { loadLiquidStory } from "@/lib/liquid/story-data";
import { levelKey, topicLabel } from "@/lib/liquid/story-types";

export const metadata: Metadata = {
  title: "Who Votes for You? · Liquid democracy",
  description:
    "Liquid delegation lets you hand each kind of decision to someone you choose. A pre-registered simulation of 200 cities asks whether that represents people better than an elected representative, without asking much more of them.",
};

/** A step inside "How it works": a small heading, its text, its figure. */
function Step({ title, children, figure }: { title: string; children: React.ReactNode; figure: React.ReactNode }) {
  return (
    <section className="mt-14">
      <LiquidText>
        <h3 className="text-lg font-semibold text-story-ink">{title}</h3>
        {children}
      </LiquidText>
      <LiquidFigure>{figure}</LiquidFigure>
    </section>
  );
}

/**
 * Demo 5: the liquid-democracy walkthrough (prompts/demo-5-walkthrough.md).
 * A long page that tells the study's story from top to bottom. Its look is
 * deliberately plain for now: the design and animation come once the
 * content is complete. Static: every number comes from
 * public/data/liquid-story/ (scripts/build_liquid_story.py,
 * scripts/build_liquid_example_city.py). Only the account app at the bottom
 * talks to the Python service, from the browser.
 */
export default async function LiquidWalkthroughPage() {
  const { measures, city } = await loadLiquidStory();
  const swiss = measures.protocol.swiss_marker;
  const at = measures.levels[levelKey(swiss)];
  const { design } = city;
  const m = city.mechanism;
  const scored = design.topics * design.evaluation_per_topic;
  const showcaseTopic = topicLabel(city.topics[m.showcase.topic]).toLowerCase();
  const kept = m.showcase.delegates
    .map((delegate, topic) => (delegate < 0 ? topicLabel(city.topics[topic]).toLowerCase() : null))
    .filter((topic): topic is string => topic !== null);
  const top = m.showcase.candidates[0];
  const shortBest = m.short_record.candidates[0];
  const everything = m.handed_over[m.handed_over.length - 1];
  const chainTopic = topicLabel(city.topics[m.chain.topic]).toLowerCase();

  return (
    <>
      <div className="story liquid-story min-h-screen pb-24">
        <StoryDataProvider measures={measures} city={city}>
          <TurnoutProvider levels={measures.protocol.turnout_grid} swiss={swiss}>
            <header id="top" className="mx-auto max-w-2xl px-4 pt-14 pb-6">
              <p className="text-sm font-medium text-story-muted">Demo 05 · Liquid democracy</p>
              <h1 className="mt-3 text-4xl font-semibold tracking-tight text-balance text-story-ink sm:text-5xl">
                Who Votes for You?
              </h1>
              <p className="mt-4 text-lg leading-relaxed text-story-ink-2">
                Liquid delegation lets you hand each kind of decision to someone you choose, and keep the rest. We
                simulated {measures.protocol.cities} cities to ask whether that represents people better than an
                elected representative, without asking much more of them.
              </p>
              <div className="mt-8 rounded-lg bg-story-surface p-5 ring-1 ring-story-rule">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium tracking-wide text-story-ink-2 uppercase">
                    The pre-registered verdict
                  </span>
                  <ClaimLabel claim="frozen" />
                </div>
                <p className="mt-2 text-xl font-semibold text-story-ink">
                  &ldquo;{measures.verdict.text.charAt(0).toUpperCase() + measures.verdict.text.slice(1)}.&rdquo;
                </p>
                <p className="mt-3 leading-relaxed text-story-ink-2">
                  In the middle of the turnout range, liquid delegation represents people far better than an elected
                  representative. At both ends it asks too much of them: it cannot keep their workload within the
                  limit fixed before the study ran. This page explains both halves of that sentence.
                </p>
                <p className="mt-3 text-xs text-story-muted">
                  Protocol frozen {measures.protocol.frozen}, run from commit {measures.protocol.commit.slice(0, 7)}.
                </p>
              </div>
            </header>

            {/* §0 Three ways to be represented */}
            <LiquidHeading id="three-ways" kicker="Three ways to be represented" claim="frozen">
              Never wrong, but usually absent
            </LiquidHeading>
            <LiquidText>
              <p>
                Every resident of a simulated city has a view on each of the {scored} questions they are scored on.
                If every one of them voted on every question, each ballot would match its voter.
              </p>
              <p>
                Real people do not vote on everything. At Swiss turnout an average resident votes on{" "}
                {pct(at.direct.fidelity)} of questions. Voting yourself is never wrong, but usually absent:{" "}
                {pct(at.direct.none_share)} of their questions carry no ballot for them at all.
              </p>
              <p>
                Elect a district representative instead. They vote on nearly everything, so only{" "}
                {pct(at.representative.none_share)} of questions go without a ballot. But the representative votes
                against the resident on {pct(at.representative.contrary_share)} of their questions: about a third of
                the time.
              </p>
              <p>
                Liquid delegation hands each topic to someone the resident chose from the public record. They keep a
                topic when nobody they could choose agrees with them well enough. Their ballot matches the resident
                on {pct(at.liquid.fidelity)} of questions; {pct(at.liquid.contrary_share)} are against them and{" "}
                {pct(at.liquid.none_share)} are empty.
              </p>
            </LiquidText>
            <LiquidFigure>
              <ThreeWaysFigure />
            </LiquidFigure>
            <LiquidText>
              <p>
                Each dot is one resident of one real city of the {measures.protocol.cities}, on one question; the bars
                average all {scored} questions over all {measures.protocol.cities} cities. The turnout dial under a
                figure moves every figure on the page.
              </p>
            </LiquidText>

            {/* §1 The city */}
            <LiquidHeading id="city" kicker="The city" claim="design">
              One run of the whole experiment
            </LiquidHeading>
            <LiquidText>
              <p>
                A city has {design.residents} residents in {design.districts} districts of{" "}
                {design.residents_per_district}. Their beliefs are drawn from a model fitted to the CES 2024 Common
                Content, a national survey of American voters, and each district elects one of{" "}
                {design.candidates_per_district} candidates as its representative.
              </p>
              <p>
                There are {design.topics} topics, each with {design.history_per_topic} past questions and{" "}
                {design.evaluation_per_topic} later ones. The past votes are the public record residents choose
                delegates from. Every arrangement is scored on the later questions, which nobody sees in advance.
              </p>
              <p>
                Each resident votes at their own rate. The dial sets the city&apos;s mean, and the spread around it
                follows Geneva&apos;s voting register, so at every mean some residents almost never vote and some
                almost always do. Office holders, the representative among them, vote on{" "}
                {pct(design.office_rate, 0)} of questions: the rate of the 118th House, from Voteview.
              </p>
            </LiquidText>
            <LiquidFigure>
              <TurnoutCity />
            </LiquidFigure>
            <LiquidText>
              <p>
                The benchmark has {measures.protocol.cities} such cities, identical except for their random seed.
                Each is run at every turnout level with the same residents.
              </p>
            </LiquidText>

            {/* §2 Two measures */}
            <LiquidHeading id="measures" kicker="Two measures" claim="frozen">
              How faithful, and how much work
            </LiquidHeading>
            <LiquidText>
              <p>
                <strong>Fidelity</strong> is the share of a voter&apos;s questions on which the ballot counted for
                them matches what they would have chosen themself.
              </p>
              <p>
                <strong>Overhead</strong> is the share of questions a voter decides themself: the work an
                arrangement asks of them. Voting yourself scores an overhead of one, and a representative close to
                zero.
              </p>
            </LiquidText>
            <LiquidFigure>
              <OneResident />
            </LiquidFigure>

            {/* §3 How it works */}
            <LiquidHeading id="how" kicker="How it works" claim="illustration">
              From the record to the ballot
            </LiquidHeading>
            <LiquidText>
              <p>
                The steps below run on the same city at Swiss turnout. Every resident, count and setting in them is
                the frozen code&apos;s own. <a href="#plane">Skip to the five arrangements</a>.
              </p>
            </LiquidText>
            <Step title="Choosing a delegate from the record" figure={<CandidatesFigure />}>
              <p>
                {resident(m.showcase.voter)} has to decide who, if anyone, should vote for them on {showcaseTopic}.
                Every other resident&apos;s past votes on it are lined up against theirs and the agreements counted:{" "}
                {resident(top.person)} matched {top.matches} of {top.trials}.
              </p>
              <p>
                Candidates are ranked by a cautious estimate, the lower end of a credible interval, so a short record
                counts for less than a long one. The topic goes to the best candidate if that estimate clears the
                city&apos;s acceptance level, {dec(m.acceptance)}.
              </p>
            </Step>
            <Step title="A short record, and an empty one" figure={<CandidatesFigure short />}>
              <p>
                A resident with almost no record has little to go on. {resident(m.short_record.voter)} has cast{" "}
                {m.short_record.total_record} ballot{m.short_record.total_record === 1 ? "" : "s"} in the whole record.
                Their best candidate&apos;s lower bound, {dec(shortBest.lower)}, falls just short of the acceptance
                level, so they keep the topic.
              </p>
              <p>
                {m.empty_records.count} residents have cast no ballot at all. With nothing to compare, they keep every
                topic. They matter later.
              </p>
            </Step>
            <Step title="A ballot arrives" figure={<RoutingFigure />}>
              <p>
                When a ballot arrives, each question is filed under its topic. It goes to the resident&apos;s delegate
                for that topic, or stays with them. {resident(m.showcase.voter)} keeps {kept.join(" and ")} and hands
                the other {design.topics - kept.length} topics on.
              </p>
              <p>
                That makes them unusual. At this turnout {everything} of the city&apos;s {design.residents} residents
                hand over all {design.topics} topics.
              </p>
            </Step>
            <Step title="Votes travel on" figure={<ChainFigure mode="chain" />}>
              <p>
                A delegate applies their own delegations to the votes they receive, so a vote can pass through several
                people. In this city one resident&apos;s vote on {chainTopic} passes through {m.chain.path.length}.
              </p>
            </Step>
            <Step title="Loops" figure={<ChainFigure mode="loop" />}>
              <p>
                When nearly everyone delegates, delegations close into loops. The rule fixed before the run: everyone
                on a loop decides for themself. Here {share(m.handed_pairs_ending_on_loop, m.handed_pairs)} of
                handed-over votes end with someone on a loop. Loops are where the work of voting lands.
              </p>
            </Step>
            <Step title="A delegate who does not vote" figure={<ChainFigure mode="lost" />}>
              <p>
                A delegate votes at their own rate, like anyone else. One who skips a question leaves every vote they
                hold on it empty.
              </p>
            </Step>
            <Step title="The calibration" figure={<CalibrationFigure />}>
              <p>
                One setting remains: how good a candidate must be. Each city takes the strictest acceptance level at
                which overhead on the past questions stays at or under {pct(m.cap, 0)}. Here that is{" "}
                {dec(m.acceptance)}.
              </p>
              <p>
                The rule uses no later question, so the scores below are not tuned to the answers. The personal proxy,
                one delegate for everything, is held to the same cap.
              </p>
            </Step>

            {/* §4 Five arrangements on one plane */}
            <LiquidHeading id="plane" kicker="Five arrangements" claim="frozen">
              Every arrangement on one plane
            </LiquidHeading>
            <LiquidText>
              <p>
                Every arrangement has a place given by its two numbers. Full turnout sits in the top right corner:
                everyone represented, everyone working. Direct voting has the same overhead and keeps only its turnout
                as fidelity.
              </p>
              <p>
                The representative asks almost nothing and returns {pct(at.representative.fidelity)}. Liquid delegation
                and the personal proxy are held to the same {pct(measures.protocol.cap, 0)} overhead, and at Swiss
                turnout liquid comes out ahead of both, at {pct(at.liquid.fidelity)}.
              </p>
            </LiquidText>
            <LiquidFigure>
              <PlaneFigure />
            </LiquidFigure>
            <LiquidText>
              <p>
                The plane holds only the calibrated arrangements. Liquid&apos;s whole curve, from voting yourself to
                handing over everything, is an exploratory figure later on. The full frozen results are in the
                benchmark&apos;s README, <code>eval/benchmarks/delegation_frontier_v1</code>.
              </p>
            </LiquidText>
          </TurnoutProvider>
        </StoryDataProvider>
      </div>

      {/* §16 The account app, at the bottom for now */}
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
            A design idea, not part of the study&apos;s claim. This is a separate, smaller city of 240 residents,
            where you write your own categories in plain words and a decision model files each question under them.
            The people, their delegations and the votes are made up; the routing is real.
          </p>
        </div>
        <AppSection />
      </section>
    </>
  );
}
