import type { Metadata } from "next";

import { AppSection } from "@/components/liquid/story/app-section";
import { AttendanceFigure } from "@/components/liquid/story/attendance-figure";
import { ClaimLabel } from "@/components/liquid/story/claim-label";
import { CostsFigure, RouterFigure } from "@/components/liquid/story/costs-figure";
import { EdgesFigure, KeepCityFigure } from "@/components/liquid/story/edges-figure";
import { LadderFigure } from "@/components/liquid/story/ladder-figure";
import { CalibrationFigure, CandidatesFigure, ChainFigure, RoutingFigure } from "@/components/liquid/story/mechanism";
import { OneResident } from "@/components/liquid/story/one-resident";
import { OutcomeStrip, OutcomesFigure } from "@/components/liquid/story/outcomes-figure";
import { PlaneFigure } from "@/components/liquid/story/plane";
import { ResultFigure } from "@/components/liquid/story/result-figure";
import { LiquidFigure, LiquidHeading, LiquidText } from "@/components/liquid/story/section-heading";
import { StoryDataProvider } from "@/components/liquid/story/story-data";
import { SweepsFigure } from "@/components/liquid/story/sweeps-figure";
import { ThreeWaysFigure } from "@/components/liquid/story/three-ways";
import { TurnoutProvider } from "@/components/liquid/story/turnout";
import { TurnoutCity } from "@/components/liquid/story/turnout-city";
import { dec, pct, pointsLabel, resident, share } from "@/lib/liquid/format";
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
  const { measures, results, city } = await loadLiquidStory();
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

  // §5–8: every quoted value read from the frozen summaries
  const grid = measures.protocol.turnout_grid;
  const result = (l: number) => results.levels[levelKey(l)];
  const measured = (l: number) => measures.levels[levelKey(l)];
  const { threshold, rules } = results;
  const lowest = grid[0];
  const highest = grid[grid.length - 1];
  const leadAtSwiss = result(swiss).h1.estimate;
  const worthwhile = grid.filter((l) => result(l).size === "gain of at least delta established");
  const failing = grid.filter((l) => result(l).h1.estimate > 0 && result(l).cap_share < rules.feasible_share);
  const crossingCities = result(threshold.bracket[1]);
  const emptyFidelity = grid.map((l) => measured(l).liquid.empty_record_fidelity ?? 0);
  const lightWorse = grid.filter(
    (l) => (measured(l).liquid.light_record_fidelity ?? 0) < (measured(l).representative.light_record_fidelity ?? 0)
  );
  const passed = grid.findIndex((l) => measured(l).direct.fidelity > measured(l).liquid.fidelity);
  const [beforePass, afterPass] = [grid[passed - 1], grid[passed]];
  const ladder = result(swiss).decomposition;
  const specialisationSizes = Array.from(
    new Set(grid.map((l) => result(l).specialisation.size).filter((size) => !size.startsWith("not assessable")))
  );
  const floor = (l: number, f: number) => result(l).frontier.find((entry) => entry.floor === f)?.estimate ?? 0;
  /** A share as quoted: 7.5%, 4%, 98.5%. */
  const quoted = (value: number) => pct(value, Math.round(value * 1000) % 10 ? 1 : 0);

  // §9–11
  const { sweeps } = results;
  const sweepLead = (point: string) => sweeps.points[point].levels[levelKey(swiss)].h1;
  const sweepPanel = (title: string) => sweeps.panels.find((panel) => panel.title.startsWith(title))?.series ?? [];
  const historyKeys = sweepPanel("History").map((s) => ({ key: s.point, label: s.label }));
  const evenKey = sweepPanel("Turnout spread")[0].point;
  const coherentKey = sweepPanel("Within-topic")[0].point;
  const districtKeys = sweepPanel("Districts").filter((s) => !s.baseline).map((s) => s.point);
  const driftKey = sweepPanel("Evaluation topic mix").filter((s) => !s.baseline).slice(-1)[0].point;
  const sweepKeys = Object.keys(sweeps.points).filter((k) => sweeps.points[k].family !== "primary");
  const sweepCount = sweepKeys.length;
  const sweepCities = sweeps.points[sweeps.reference].cities;
  const unbounded = sweepKeys.filter((k) => sweeps.points[k].confidence.every((bound) => bound === null)).length;
  const lifecycle = grid.map((l) => measured(l).liquid.lifecycle_overhead ?? 0);
  const winners = city.levels[levelKey(swiss)].winners;
  const cityQuestions = winners.full_turnout.length;
  const missesOf = (name: "direct" | "liquid" | "representative") =>
    Array.from(winners[name]).filter((w, q) => w !== winners.full_turnout[q]).length;
  const cityMisses = { direct: missesOf("direct"), liquid: missesOf("liquid"), representative: missesOf("representative") };

  return (
    <>
      <div className="story liquid-story min-h-screen pb-24">
        <StoryDataProvider measures={measures} results={results} city={city}>
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
                handing over everything, is an exploratory figure later on.
              </p>
            </LiquidText>

            {/* §5 The result */}
            <LiquidHeading id="result" kicker="The result" claim="frozen">
              Far ahead in the middle, not established at the ends
            </LiquidHeading>
            <LiquidText>
              <p>
                Liquid delegation overtakes the district representative near turnout {dec(threshold.crossing, 2)}. The
                95% range for where it crosses runs from {threshold.confidence[0]} to {threshold.confidence[1]}.
              </p>
              <p>
                From there the lead grows. At Swiss turnout liquid is {pointsLabel(100 * leadAtSwiss)} points ahead,
                and at every level from {worthwhile[0]} to {worthwhile[worthwhile.length - 1]} the lead clears{" "}
                {100 * rules.delta} points, the smallest lead the study set out to count as worthwhile.
              </p>
              <p>
                The test had one more condition: at every level where liquid leads, at least{" "}
                {pct(rules.feasible_share, 0)} of cities must keep its overhead at or under {pct(rules.cap, 0)}.{" "}
                {failing.map((l, i) => `${i === 0 ? "Only " : ""}${quoted(result(l).cap_share)}${i === 0 ? " do" : ""} at ${l}`).join(" and ")}. So the verdict,
                fixed in advance, is <em>{measures.verdict.text}</em>.
              </p>
            </LiquidText>
            <LiquidFigure>
              <ResultFigure />
            </LiquidFigure>
            <LiquidText>
              <p className="text-sm text-story-ink-2">
                Why the crossing&apos;s range ends at {threshold.confidence[1]}: at {threshold.bracket[1]} only{" "}
                {crossingCities.cap_meeting_cities} cities keep liquid under the cap, and the band over those cities
                still dips below zero ({pointsLabel(100 * (crossingCities.band_cap?.lower ?? 0))} points).
              </p>
            </LiquidText>

            {/* §6 The two edges */}
            <LiquidHeading id="edges" kicker="The two edges" claim="frozen">
              Two failures for opposite reasons
            </LiquidHeading>
            <LiquidText>
              <h3 className="text-lg font-semibold text-story-ink">Low turnout: overhead nobody uses</h3>
              <p>
                A resident with no votes in the record has nothing to choose a delegate by. They keep their own vote,
                and they rarely use it. At {lowest} liquid&apos;s overhead is {pct(measured(lowest).liquid.overhead)},
                and {pct(measured(lowest).liquid.empty_record_share ?? 0)} of residents have an empty record: the
                overhead is these residents.
              </p>
              <p>
                They are barely represented. Their fidelity under liquid is between{" "}
                {Math.min(...emptyFidelity).toFixed(3)} and {Math.max(...emptyFidelity).toFixed(3)} at every level,
                against about {dec(measured(swiss).representative.empty_record_fidelity ?? 0, 2)} under the
                representative. Residents with a light record, under 10% of the past questions, do slightly worse
                under liquid than under the representative at every level up to {lightWorse[lightWorse.length - 1]}:{" "}
                {dec(measured(swiss).liquid.light_record_fidelity ?? 0)} against{" "}
                {dec(measured(swiss).representative.light_record_fidelity ?? 0)} at Swiss turnout, where they are{" "}
                {pct(measured(swiss).liquid.light_record_share ?? 0, 0)} of the city.
              </p>
              <p>
                It isn&apos;t caused by topics. The personal proxy has the same floor (
                {pct(measured(threshold.bracket[1]).proxy.overhead)} overhead at {threshold.bracket[1]}), so the cause
                is choosing by record.
              </p>
              <h3 className="pt-4 text-lg font-semibold text-story-ink">High turnout: overhead people do use</h3>
              <p>
                When nearly everyone delegates, voters on a loop decide for themselves. At {highest},{" "}
                {pct(measured(highest).liquid.loop_share ?? 0)} of voter-question pairs sit on a loop, and
                liquid&apos;s overhead is {pct(measured(highest).liquid.overhead)}. The questions liquid&apos;s voters
                keep match them {pct(measured(highest).liquid.fidelity_kept ?? 0, 0)} of the time.
              </p>
              <p>
                This one is specific to topic delegation. The single proxy&apos;s loop share is{" "}
                {pct(measured(highest).proxy.loop_share ?? 0)}, and it meets the cap in{" "}
                {quoted(result(highest).proxy_cap_share)} of cities. Meanwhile direct voting, with full overhead,
                passes liquid between {beforePass} ({dec(measured(beforePass).direct.fidelity)} against{" "}
                {dec(measured(beforePass).liquid.fidelity)}) and {afterPass} (
                {dec(measured(afterPass).direct.fidelity)} against {dec(measured(afterPass).liquid.fidelity)}): the cap
                pushes people who would vote into delegating.
              </p>
              <p>One overhead number cannot tell a burden people carry from one they drop.</p>
            </LiquidText>
            <LiquidFigure>
              <EdgesFigure />
            </LiquidFigure>
            <LiquidFigure>
              <KeepCityFigure />
            </LiquidFigure>

            {/* §7 The ladder */}
            <LiquidHeading id="ladder" kicker="Where the lead comes from" claim="frozen">
              Most of it arrives with the single proxy
            </LiquidHeading>
            <LiquidText>
              <p>
                The study declared a chain of arrangements from the representative to liquid delegation, each run on
                the same cities, so the lead splits into steps. At Swiss turnout, choosing one delegate for everything
                from the whole city adds {pointsLabel(100 * ladder.city_wide_proxy_combined.estimate)} of the{" "}
                {pointsLabel(100 * ladder.h1.estimate)} points.
              </p>
              <p>
                The signature feature adds least. Handing each topic to its own delegate adds{" "}
                {pointsLabel(100 * ladder.specialisation.estimate)} points (95% interval{" "}
                {pointsLabel(100 * ladder.specialisation.lower)} to {pointsLabel(100 * ladder.specialisation.upper)}).
                It is real, but it never clears the same {100 * rules.delta}-point minimum: where it can be assessed it
                reads {specialisationSizes.join(" or ")}.
              </p>
              <p>
                The proxy step bundles several changes at once, and no matched arm separates them. So most of the lead
                arrives with the single proxy, and the study cannot say which part of that step causes it.
              </p>
            </LiquidText>
            <LiquidFigure>
              <LadderFigure />
            </LiquidFigure>

            {/* §8 Attendance */}
            <LiquidHeading id="attendance" kicker="Delegates who don't show up" claim="frozen">
              Attendance is not the bottleneck
            </LiquidHeading>
            <LiquidText>
              <p>
                Delegates vote at their own rate. Whoever holds someone&apos;s vote at Swiss turnout votes{" "}
                {pct(measured(swiss).liquid.resolver_attendance ?? 0, 0)} of the time, and{" "}
                {pct(measured(lowest).liquid.resolver_attendance ?? 0, 0)} at {lowest}.
              </p>
              <p>
                A floor helps a little. If every delegate always voted, liquid would gain{" "}
                {pointsLabel(100 * (floor(lowest, 1) - floor(lowest, 0)))} points at {lowest}, about{" "}
                {pointsLabel(100 * (floor(swiss, 1) - floor(swiss, 0)))} at Swiss turnout, and less above.
              </p>
              <p>
                It cannot rescue the low end. At {lowest} liquid trails the representative by{" "}
                {(-100 * floor(lowest, 0)).toFixed(1)} points, and still by {(-100 * floor(lowest, 1)).toFixed(1)} if
                every delegate always votes: the shortfall is residents who keep their own vote.
              </p>
            </LiquidText>
            <LiquidFigure>
              <AttendanceFigure />
            </LiquidFigure>

            {/* §9 The sweeps */}
            <LiquidHeading id="sweeps" kicker="What the lead depends on" claim="frozen">
              Liquid borrows engagement; it does not create it
            </LiquidHeading>
            <LiquidText>
              <p>
                Each sweep reruns the benchmark on {sweepCities} cities with one setting changed. At Swiss turnout
                the baseline leads by {pointsLabel(100 * sweepLead(sweeps.reference))} points.
              </p>
              <ul>
                <li>
                  <strong>The public record.</strong> The lead grows with the record people choose from:{" "}
                  {historyKeys.map((k) => `${pointsLabel(100 * sweepLead(k.key))} with ${k.label}`).join(", ")}{" "}
                  questions per topic. With {historyKeys[0].label} the cap fails at every level.
                </li>
                <li>
                  <strong>Turnout spread.</strong> In an even electorate, where nearly everyone votes sometimes, the
                  lead at Swiss turnout falls to {pointsLabel(100 * sweepLead(evenKey))} points and the crossing moves
                  to about {dec(sweeps.points[evenKey].crossing ?? 0, 2)}. It is also the only setting whose reading
                  is a clean crossing: wherever liquid leads, every city stays under the cap.
                </li>
                <li>
                  <strong>Within-topic coherence</strong> is the only setting that shifts the whole curve. With half the
                  spread of views within a topic, the lead at Swiss turnout is{" "}
                  {pointsLabel(100 * sweepLead(coherentKey))}, the highest in the sweeps.
                </li>
                <li>
                  <strong>Districts</strong> make no difference ({districtKeys
                    .map((k) => `${pointsLabel(100 * sweepLead(k))}`)
                    .join(" and ")}{" "}
                  points with two and ten districts).
                </li>
                <li>
                  <strong>Agenda drift,</strong> one topic weighing more in the later questions than in the record,
                  leaves the lead where it was but breaks the cap: at Swiss turnout only{" "}
                  {quoted(sweeps.points[driftKey].levels[levelKey(swiss)].cap_share)} of cities stay under it.
                </li>
                <li>
                  <strong>The belief generator.</strong> Swapping the fitted model for a one-factor generator matched
                  to the survey costs liquid {(100 * (sweepLead(sweeps.reference) - sweepLead(sweeps.structural_baseline))).toFixed(1)}{" "}
                  points at Swiss turnout.
                </li>
              </ul>
            </LiquidText>
            <LiquidFigure>
              <SweepsFigure />
            </LiquidFigure>
            <LiquidText>
              <p className="text-sm text-story-ink-2">
                Why {unbounded} of the {sweepCount} sweep settings have no bound on where they cross: at {sweepCities}{" "}
                cities, levels where only a few cities stay under the cap meet the frozen band&apos;s rule, which then
                cannot rule any level out. Changing that rule would be a dated exploratory amendment.
              </p>
            </LiquidText>

            {/* §10 Costs */}
            <LiquidHeading id="costs" kicker="Costs the headline does not show" claim="frozen">
              Concentration, absences and a cold start
            </LiquidHeading>
            <LiquidText>
              <p>
                <strong>Concentration.</strong> A district representative decides{" "}
                {pct(measured(swiss).representative.mean_largest_share ?? 0, 0)} of every question. Under liquid at
                Swiss turnout, the largest single delegate decides {pct(measured(swiss).liquid.mean_largest_share ?? 0)}{" "}
                of a question&apos;s votes on average, and {pct(measured(swiss).liquid.max_largest_share ?? 0)} on a
                city&apos;s worst question. At {threshold.bracket[1]} that share is{" "}
                {pct(measured(threshold.bracket[1]).liquid.mean_largest_share ?? 0)}, and at {lowest}{" "}
                {pct(measured(lowest).liquid.mean_largest_share ?? 0)}.
              </p>
              <p>
                <strong>Two kinds of poor representation.</strong> Under liquid,{" "}
                {pct(measured(swiss).liquid.share_below_half ?? 0)} of voters are represented on fewer than half their
                questions; under the representative, {pct(measured(swiss).representative.share_below_half ?? 0)}.
                Liquid&apos;s failures are absences: no ballot on {pct(measured(swiss).liquid.below_half_none_share ?? 0, 0)}{" "}
                of those voters&apos; questions. The representative&apos;s are contradictions: a ballot against them on{" "}
                {pct(measured(swiss).representative.below_half_contrary_share ?? 0, 0)}.
              </p>
              <p>
                <strong>The cold start.</strong> The {pct(rules.cap, 0)} is a steady state. Counting the history
                period, when everyone decides every question so that the records exist, liquid&apos;s overhead is{" "}
                {pct(measured(swiss).liquid.lifecycle_overhead ?? 0, 0)} at Swiss turnout, and between{" "}
                {pct(Math.min(...lifecycle), 0)} and {pct(Math.max(...lifecycle), 0)} across the dial.
              </p>
            </LiquidText>
            <LiquidFigure>
              <CostsFigure />
            </LiquidFigure>
            <LiquidText>
              <p>
                <strong>Routing.</strong> The study files every question under its true topic. A real router reads a
                question and decides which of a voter&apos;s written categories it falls under, and it can be wrong
                either way: a false delegation sends a vote to someone it was not meant for and costs fidelity; a false
                keep leaves a vote with its owner and costs overhead. Running the benchmark under routing error is a
                declared follow-up, not a result.
              </p>
            </LiquidText>
            <LiquidFigure>
              <RouterFigure />
            </LiquidFigure>

            {/* §11 Individuals and outcomes */}
            <LiquidHeading id="outcomes" kicker="Individuals and outcomes" claim="frozen">
              Worst for individuals, best for outcomes
            </LiquidHeading>
            <LiquidText>
              <p>
                Fidelity scores each voter. A different question is whether an arrangement picks the winner the whole
                city would pick if everyone voted. At Swiss turnout direct voting matches it on{" "}
                {pct(measured(swiss).direct.outcome_agreement ?? 0)} of questions, liquid on{" "}
                {pct(measured(swiss).liquid.outcome_agreement ?? 0)}, the personal proxy on{" "}
                {pct(measured(swiss).proxy.outcome_agreement ?? 0)} and the representative on{" "}
                {pct(measured(swiss).representative.outcome_agreement ?? 0)}. Direct voting represents individuals
                worst and outcomes best.
              </p>
              <p>
                <span className="mr-1.5 inline-block align-middle">
                  <ClaimLabel claim="exploratory" />
                </span>
                An interpretation the study did not test: random abstention is a fair sample, so the voters who turn
                up decide as the whole city would. Delegation instead copies one person&apos;s deviations onto everyone
                who follows them.
              </p>
              <p>
                The largest caveat on any outcome claim: in this model turnout is independent of opinion, and real
                abstention is not.
              </p>
            </LiquidText>
            <LiquidFigure>
              <OutcomesFigure />
            </LiquidFigure>
            <LiquidText>
              <p>
                In the illustrative city the representatives&apos; council loses the issue-by-issue majority on{" "}
                {cityMisses.representative} of its {cityQuestions} questions at Swiss turnout. These are
                Ostrogorski-style cases: a body elected on bundled platforms that does not carry the majority on each
                issue. Liquid
                misses {cityMisses.liquid} there and direct voting {cityMisses.direct}; across all{" "}
                {measures.protocol.cities} cities liquid does better than the representative, as above.
              </p>
            </LiquidText>
            <LiquidFigure>
              <OutcomeStrip />
            </LiquidFigure>
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
