import type { Metadata } from "next";
import Link from "next/link";

import { AppSection } from "@/components/liquid/story/app-section";
import { ClaimLabel } from "@/components/liquid/story/claim-label";
import { CostsFigure, RouterFigure } from "@/components/liquid/story/costs-figure";
import { EdgesFigure, KeepCityFigure } from "@/components/liquid/story/edges-figure";
import { HandoverFigure } from "@/components/liquid/story/exploratory-figures";
import { CalibrationFigure, CandidatesFigure, ChainFigure, RoutingFigure } from "@/components/liquid/story/mechanism";
import { OutcomesFigure } from "@/components/liquid/story/outcomes-figure";
import { ResultFigure } from "@/components/liquid/story/result-figure";
import {
  LiquidFigure,
  LiquidHeading,
  LiquidText,
  STUDY_HREF,
  StudyLinks,
} from "@/components/liquid/story/section-heading";
import { StoryDataProvider } from "@/components/liquid/story/story-data";
import { ThreeWaysFigure } from "@/components/liquid/story/three-ways";
import { TurnoutProvider } from "@/components/liquid/story/turnout";
import { dec, pct, pointsLabel, resident, share } from "@/lib/liquid/format";
import { loadLiquidStory } from "@/lib/liquid/story-data";
import { levelKey, topicLabel } from "@/lib/liquid/story-types";

export const metadata: Metadata = {
  title: "Who Votes for You? · Liquid democracy",
  description:
    "Liquid delegation lets you hand each kind of decision to someone you choose. A pre-registered simulation of 200 cities asks whether that represents people better than an elected representative, where it breaks, and what could be built to fix it.",
};

/** The published repository, for the benchmark and the design doc. */
const REPOSITORY = "https://github.com/BenDotWillcox/voting-paradigm/tree/main";

/** The story's five parts, for the opening's contents. */
const PARTS = [
  { id: "idea", label: "The idea" },
  { id: "how", label: "How it works" },
  { id: "result", label: "Does it work?" },
  { id: "breaks", label: "Where it breaks" },
  { id: "build", label: "What we'd build" },
] as const;

/** A step inside part 2: a small heading, its text, its figure. */
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

/** A small heading inside a part. */
function Beat({ children, className }: { children: React.ReactNode; className?: string }) {
  return <h3 className={`pt-4 text-lg font-semibold text-story-ink ${className ?? ""}`}>{children}</h3>;
}

/** Which part 5 proposal targets a bottleneck, or that none does. */
function Targets({ children }: { children: React.ReactNode }) {
  return (
    <p className="border-l-2 border-story-rule pl-3 text-sm text-story-ink-2">
      <span className="font-medium text-story-ink">In part 5:</span> {children}
    </p>
  );
}

/**
 * Demo 5: "Who Votes for You?", the liquid-democracy story
 * (prompts/demo-5-walkthrough.md, "The story"). Five parts: the idea, how it
 * works, the result, where it breaks, and what could be built, ending with
 * the account app. It shows highlights only; every part links to the full
 * study at /liquid/study, which holds every figure and interval. Plain for
 * now: the styling comes once the core is built. Static: every number comes
 * from public/data/liquid-story/. Only the account app talks to the Python
 * service, from the browser.
 */
export default async function LiquidStoryPage() {
  const { measures, results, exploratory, city } = await loadLiquidStory();
  const { protocol } = measures;
  const swiss = protocol.swiss_marker;
  const at = measures.levels[levelKey(swiss)];
  const { design } = city;
  const m = city.mechanism;

  // Part 2: the illustrative city at Swiss turnout
  const showcaseTopic = topicLabel(city.topics[m.showcase.topic]).toLowerCase();
  const kept = m.showcase.delegates
    .map((delegate, topic) => (delegate < 0 ? topicLabel(city.topics[topic]).toLowerCase() : null))
    .filter((topic): topic is string => topic !== null);
  const top = m.showcase.candidates[0];
  const shortBest = m.short_record.candidates[0];
  const everything = m.handed_over[m.handed_over.length - 1];
  const chainTopic = topicLabel(city.topics[m.chain.topic]).toLowerCase();

  // Parts 3 and 4: every quoted value read from the frozen summaries
  const grid = protocol.turnout_grid;
  const result = (l: number) => results.levels[levelKey(l)];
  const measured = (l: number) => measures.levels[levelKey(l)];
  const { threshold, rules } = results;
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
  const { sweeps } = results;
  const sweepLead = (point: string) => sweeps.points[point].levels[levelKey(swiss)].h1;
  const sweepPanel = (title: string) => sweeps.panels.find((panel) => panel.title.startsWith(title))?.series ?? [];
  const shortestHistory = sweepPanel("History")[0];
  const evenKey = sweepPanel("Turnout spread")[0].point;

  // Part 5
  const handoverAt = (l: number) => exploratory.handover.levels[levelKey(l)];
  const rises = (l: number) => handoverAt(l).every((p, i, all) => i === 0 || p.fidelity > all[i - 1].fidelity);
  const lastRise = grid.filter(rises).slice(-1)[0];
  const firstFall = grid[grid.indexOf(lastRise) + 1];
  const highCurve = handoverAt(highest);
  const agentBars = exploratory.agent_bars.levels[levelKey(swiss)];

  return (
    <>
      <div className="story liquid-story min-h-screen pb-24">
        <StoryDataProvider measures={measures} results={results} exploratory={exploratory} city={city}>
          <TurnoutProvider levels={grid} swiss={swiss}>
            {/* The opening: the question and the answer, unsoftened */}
            <header id="top" className="mx-auto max-w-2xl px-4 pt-14 pb-6">
              <p className="text-sm font-medium text-story-muted">Demo 05 · Liquid democracy</p>
              <h1 className="mt-3 text-4xl font-semibold tracking-tight text-balance text-story-ink sm:text-5xl">
                Who Votes for You?
              </h1>
              <p className="mt-4 text-lg leading-relaxed text-story-ink-2">
                Liquid delegation lets you hand each kind of decision to someone you choose, and keep the rest. We
                simulated {protocol.cities} cities to ask one question: can people hand most of their civic decisions
                to delegates they choose, and still be represented better than by an elected representative?
              </p>
              <div className="mt-8 rounded-lg bg-story-surface p-5 ring-1 ring-story-rule">
                <p className="text-xs font-medium tracking-wide text-story-ink-2 uppercase">The short answer</p>
                <p className="mt-2 text-lg leading-relaxed text-story-ink">
                  Clearly yes in the middle of the turnout range. But the test we declared before the run is not met:
                  at both ends, liquid delegation cannot keep the work it asks of voters low.
                </p>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium tracking-wide text-story-ink-2 uppercase">
                    The pre-registered verdict
                  </span>
                  <ClaimLabel claim="frozen" />
                </div>
                <p className="mt-1 font-semibold text-story-ink">
                  &ldquo;{measures.verdict.text.charAt(0).toUpperCase() + measures.verdict.text.slice(1)}.&rdquo;
                </p>
              </div>
              <nav aria-label="The story's parts" className="mt-8 text-sm text-story-ink-2">
                <ol className="space-y-1">
                  {PARTS.map((part, index) => (
                    <li key={part.id}>
                      <a href={`#${part.id}`} className="hover:text-story-ink">
                        <span className="tabular-nums text-story-muted">{index + 1}.</span> {part.label}
                      </a>
                    </li>
                  ))}
                </ol>
                <p className="mt-4 [&_a]:underline [&_a]:underline-offset-4">
                  <a href="#app">Skip to the app</a> · <Link href={STUDY_HREF}>Read the full study</Link>
                </p>
              </nav>
            </header>

            {/* Parts 1 and 2 are read at Swiss turnout; the dial arrives in part 3 */}
            <TurnoutProvider
              levels={grid}
              swiss={swiss}
              fixed={`Shown at Swiss turnout, ${swiss}. You set the turnout from part 3.`}
            >
              {/* Part 1. The idea */}
              <LiquidHeading id="idea" kicker="Part 1 · The idea" claim="frozen">
                Three ways to be represented
              </LiquidHeading>
              <LiquidText>
                <p>There are three ways a city can turn what its residents want into ballots.</p>
                <ul>
                  <li>
                    <strong>Direct voting.</strong> Everyone votes on every question themself. A ballot you cast is
                    always yours, but most people skip most questions.
                  </li>
                  <li>
                    <strong>A district representative.</strong> Your district elects one person, who votes on every
                    question for everyone in it.
                  </li>
                  <li>
                    <strong>Liquid delegation.</strong> You hand each topic to someone you choose, anyone in the city,
                    and keep any topic you want. Your delegate can pass your vote on to their own delegate.
                  </li>
                </ul>
                <p>
                  A representative costs you in two ways. <em>Dilution</em>: you share them with your whole district,
                  whose views differ from yours, and they were elected by all of it. <em>Bundling</em>: one person
                  stands for you on every issue, and you will not agree with anyone on everything. Liquid delegation
                  removes both, because you choose the person, topic by topic.
                </p>
                <p>
                  Two numbers measure the trade. <strong>Fidelity</strong> is the share of your questions on which the
                  ballot counted for you matches what you would have chosen. <strong>Overhead</strong> is the share
                  you decide yourself: the work an arrangement asks of you. Voting on everything yourself scores one
                  on both. The question is how much fidelity an arrangement keeps for how little overhead.
                </p>
                <p>
                  To measure them we built synthetic cities. Each has {design.residents} residents in{" "}
                  {design.districts} districts, with views drawn from a model fitted to the CES 2024 survey of American
                  voters, and {design.topics} topics, each with a public record of {design.history_per_topic} past
                  votes to choose delegates from. Each resident votes at their own rate. The study ran{" "}
                  {protocol.cities} such cities.
                </p>
                <p>
                  Until part 3, everything is shown at Swiss turnout, where the average resident votes on{" "}
                  {pct(at.direct.fidelity)} of questions. Voting yourself is never wrong but usually absent:{" "}
                  {pct(at.direct.none_share)} of their questions carry no ballot for them. A representative leaves only{" "}
                  {pct(at.representative.none_share)} empty, but votes against the resident on{" "}
                  {pct(at.representative.contrary_share)}: about a third of the time. Liquid delegation&apos;s ballots
                  match the resident on {pct(at.liquid.fidelity)} of questions; {pct(at.liquid.contrary_share)} are
                  against them and {pct(at.liquid.none_share)} are empty.
                </p>
              </LiquidText>
              <LiquidFigure>
                <ThreeWaysFigure />
              </LiquidFigure>
              <LiquidText>
                <p>
                  Each dot is one resident of one real city of the {protocol.cities}, on one question; the bars average
                  all {design.topics * design.evaluation_per_topic} questions they are scored on, over all{" "}
                  {protocol.cities} cities.
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

              {/* Part 2. How it works */}
              <LiquidHeading id="how" kicker="Part 2 · How it works" claim="illustration">
                From the record to the ballot
              </LiquidHeading>
              <LiquidText>
                <p>
                  Liquid delegation runs on a few simple rules: hand over a topic, let votes travel on, and let loops
                  come back. The hard part is choosing whom to trust. The steps below run on one of the{" "}
                  {protocol.cities} cities, and every resident, count and setting in them is the frozen code&apos;s
                  own.
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
                  {m.short_record.total_record} ballot{m.short_record.total_record === 1 ? "" : "s"} in the whole
                  record. Their best candidate&apos;s lower bound, {dec(shortBest.lower)}, falls just short of the
                  acceptance level, so they keep the topic.
                </p>
                <p>
                  {m.empty_records.count} residents have cast no ballot at all. With nothing to compare, they keep every
                  topic. Part 4 comes back to them: they are where liquid delegation breaks.
                </p>
              </Step>
              <Step title="A ballot arrives" figure={<RoutingFigure />}>
                <p>
                  When a ballot arrives, each question is filed under its topic. It goes to the resident&apos;s delegate
                  for that topic, or stays with them. {resident(m.showcase.voter)} keeps {kept.join(" and ")} and hands
                  the other {design.topics - kept.length} topics on. That makes them unusual: at this turnout{" "}
                  {everything} of the city&apos;s {design.residents} residents hand over all {design.topics} topics.
                </p>
              </Step>
              <Step title="Votes travel on" figure={<ChainFigure mode="chain" />}>
                <p>
                  A delegate applies their own delegations to the votes they receive, so a vote can pass through several
                  people. In this city one resident&apos;s vote on {chainTopic} passes through {m.chain.path.length}.
                </p>
              </Step>
              <Step title="Loops come back" figure={<ChainFigure mode="loop" />}>
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
              <Step title="How good a delegate must be" figure={<CalibrationFigure />}>
                <p>
                  One setting remains: the acceptance level. Each city takes the strictest level at which overhead on
                  the past questions stays at or under {pct(m.cap, 0)}. Here that is {dec(m.acceptance)}. The rule uses
                  no later question, so the scores are not tuned to the answers.
                </p>
                <p>That {pct(m.cap, 0)} limit is the one the study&apos;s verdict tests.</p>
              </Step>
              <StudyLinks links={[{ anchor: "how", label: "How it works" }]} />
            </TurnoutProvider>

            {/* Part 3. Does it work? */}
            <LiquidHeading id="result" kicker="Part 3 · Does it work?" claim="frozen">
              Far ahead in the middle, not established at the ends
            </LiquidHeading>
            <LiquidText>
              <p>
                Everything so far was at Swiss turnout. Turnout is the one setting that changes the answer, so from here
                on you set it: the dial under each figure moves every figure below.
              </p>
              <p>
                Liquid delegation overtakes the district representative near turnout {dec(threshold.crossing, 2)}; the
                95% range for where it crosses runs from {threshold.confidence[0]} to {threshold.confidence[1]}. From
                there the lead grows. At Swiss turnout liquid is {pointsLabel(100 * result(swiss).h1.estimate)} points
                ahead, and at every level from {worthwhile[0]} to {worthwhile[worthwhile.length - 1]} the lead clears{" "}
                {100 * rules.delta} points, the smallest lead the study set out to count as worthwhile.
              </p>
              <p>
                The test had one more condition: at every level where liquid leads, at least{" "}
                {pct(rules.feasible_share, 0)} of cities must keep its overhead at or under {pct(rules.cap, 0)}.{" "}
                {failing
                  .map((l, i) => `${i === 0 ? "Only " : ""}${quoted(result(l).cap_share)}${i === 0 ? " do" : ""} at ${l}`)
                  .join(" and ")}
                . So the verdict, fixed in advance, is <em>{measures.verdict.text}</em>. Part 4 explains why both ends
                fail.
              </p>
            </LiquidText>
            <LiquidFigure>
              <ResultFigure />
            </LiquidFigure>
            <LiquidText>
              <p>
                Where does the lead come from? The study declared a chain of arrangements from the representative to
                liquid delegation, each run on the same cities, so the lead splits into steps. At Swiss turnout, having
                one chosen delegate for everything adds {pointsLabel(100 * ladder.city_wide_proxy_combined.estimate)} of
                the {pointsLabel(100 * ladder.h1.estimate)} points. Handing each topic to its own delegate, the feature
                liquid democracy is known for, adds {pointsLabel(100 * ladder.specialisation.estimate)}. That first
                step bundles several changes, and the study cannot say which of them causes the gain.
              </p>
            </LiquidText>
            <LiquidText className="mt-8">
              <div className="rounded-lg bg-story-surface p-5 ring-1 ring-story-rule">
                <p className="text-xs font-medium tracking-wide text-story-ink-2 uppercase">How we know</p>
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
                  <li>Every number on this page is read from the published results.</li>
                </ul>
              </div>
            </LiquidText>
            <StudyLinks
              links={[
                { anchor: "result", label: "The result" },
                { anchor: "ladder", label: "Where the lead comes from" },
                { anchor: "attendance", label: "Delegates who don't show up" },
                { anchor: "sweeps", label: "What the lead depends on" },
                { anchor: "methods", label: "Methods and sources" },
              ]}
            />

            {/* Part 4. Where it breaks */}
            <LiquidHeading id="breaks" kicker="Part 4 · Where it breaks" claim="frozen">
              What stands in the way of a real deployment
            </LiquidHeading>
            <LiquidText>
              <p>
                Neither end of the turnout range fails because votes go astray. They fail for opposite reasons, and a
                few further costs hide behind the headline. Each one below names the proposal in part 5 that targets
                it, or says that none does.
              </p>
              <Beat>Low turnout: people with no record</Beat>
              <p>
                A resident with no votes in the record has nothing to choose a delegate by. They keep their own vote,
                and they rarely use it. At {lowest}, liquid&apos;s overhead is {pct(measured(lowest).liquid.overhead)},
                and {pct(measured(lowest).liquid.empty_record_share ?? 0)} of residents have an empty record: the
                overhead is these residents.
              </p>
              <p>
                They are barely represented. Their fidelity under liquid is between{" "}
                {Math.min(...emptyFidelity).toFixed(3)} and {Math.max(...emptyFidelity).toFixed(3)} at every level,
                against about {dec(measured(swiss).representative.empty_record_fidelity ?? 0, 2)} under the
                representative. One chosen delegate for everything has the same floor (
                {pct(measured(threshold.bracket[1]).proxy.overhead)} overhead at {threshold.bracket[1]}), so the cause is
                choosing by record, not topics.
              </p>
              <Targets>the representative as a default delegate, and a personal agent.</Targets>
              <Beat>High turnout: loops, and people who would vote</Beat>
              <p>
                When nearly everyone delegates, delegations close into loops, and everyone on a loop decides for
                themself. At {highest}, {pct(measured(highest).liquid.loop_share ?? 0)} of voter-question pairs sit on
                a loop, and liquid&apos;s overhead is {pct(measured(highest).liquid.overhead)}. This is specific to
                topic delegation: with one delegate for everything the loop share is{" "}
                {pct(measured(highest).proxy.loop_share ?? 0)}.
              </p>
              <p>
                The city-wide limit also pushes people who would vote into delegating. Direct voting, with full
                overhead, passes liquid between {beforePass} ({dec(measured(beforePass).direct.fidelity)} against{" "}
                {dec(measured(beforePass).liquid.fidelity)}) and {afterPass} (
                {dec(measured(afterPass).direct.fidelity)} against {dec(measured(afterPass).liquid.fidelity)}). One
                overhead number cannot tell a burden people carry from one they drop.
              </p>
              <Targets>a backup delegate for loops, and a ceiling set by each voter.</Targets>
            </LiquidText>
            <LiquidFigure>
              <EdgesFigure />
            </LiquidFigure>
            <LiquidFigure>
              <KeepCityFigure />
            </LiquidFigure>

            <LiquidText>
              <Beat>Costs the headline hides</Beat>
              <p>
                <strong>Concentration.</strong> A district representative decides{" "}
                {pct(measured(swiss).representative.mean_largest_share ?? 0, 0)} of every question. Under liquid at
                Swiss turnout, the largest single delegate decides {pct(measured(swiss).liquid.mean_largest_share ?? 0)}{" "}
                of a question&apos;s votes on average, and {pct(measured(swiss).liquid.max_largest_share ?? 0)} on a
                city&apos;s worst question; at {lowest}, {pct(measured(lowest).liquid.mean_largest_share ?? 0)}.
              </p>
              <p>
                <strong>Poor representation looks different.</strong> Under liquid,{" "}
                {pct(measured(swiss).liquid.share_below_half ?? 0)} of voters are represented on fewer than half their
                questions, against {pct(measured(swiss).representative.share_below_half ?? 0)} under the
                representative. Liquid&apos;s failures are absences; the representative&apos;s are ballots against
                them.
              </p>
              <p>
                <strong>The cold start.</strong> The {pct(rules.cap, 0)} is a steady state. The record has to be built
                first, while everyone decides every question: counting that period, liquid&apos;s overhead is{" "}
                {pct(measured(swiss).liquid.lifecycle_overhead ?? 0, 0)} at Swiss turnout.
              </p>
              <Targets>
                a personal agent, whose record would come from one interview, for the cold start. Nothing here
                prevents concentration, and the agent would carry the same risk in a new form.
              </Targets>
            </LiquidText>
            <LiquidFigure>
              <CostsFigure />
            </LiquidFigure>
            <LiquidText>
              <p>
                <strong>Routing.</strong> The study files every question under its true topic. A real system has to
                read each question and decide which of a voter&apos;s categories it falls under, and a decision model
                can be wrong either way: a false delegation sends a vote to someone it was not meant for and costs
                fidelity; a false keep leaves a vote with its owner and costs overhead.
              </p>
            </LiquidText>
            <LiquidFigure>
              <RouterFigure />
            </LiquidFigure>
            <LiquidText>
              <p>
                <strong>Not a bottleneck: attendance.</strong> Whoever holds someone&apos;s vote at Swiss turnout
                casts it {pct(measured(swiss).liquid.resolver_attendance ?? 0, 0)} of the time.
              </p>

              <Beat>What delegation cannot change</Beat>
              <p>
                <strong>It borrows engagement; it does not create it.</strong> Liquid delegation moves votes from
                people who rarely vote to people who often do. In an electorate where nearly everyone votes sometimes,
                the lead at Swiss turnout falls to {pointsLabel(100 * sweepLead(evenKey))} points and the crossing
                moves to about {dec(sweeps.points[evenKey].crossing ?? 0, 2)}. With a record of only{" "}
                {shortestHistory.label} questions per topic, too few cities stay within the {pct(rules.cap, 0)} limit at
                any level.
              </p>
              <Targets>nothing. None of the proposals changes this.</Targets>
              <p>
                <strong>Better for individuals, worse for outcomes.</strong> Fidelity scores each voter. Whether an
                arrangement picks the winner the whole city would pick if everyone voted is a different question. At
                Swiss turnout direct voting matches it on {pct(measured(swiss).direct.outcome_agreement ?? 0)} of
                questions, liquid on {pct(measured(swiss).liquid.outcome_agreement ?? 0)} and the representative on{" "}
                {pct(measured(swiss).representative.outcome_agreement ?? 0)}: the arrangement that represents
                individuals worst matches outcomes best.
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
            </LiquidText>
            <LiquidFigure>
              <OutcomesFigure />
            </LiquidFigure>
            <StudyLinks
              links={[
                { anchor: "edges", label: "The two edges" },
                { anchor: "costs", label: "Costs the headline does not show" },
                { anchor: "sweeps", label: "What the lead depends on" },
                { anchor: "outcomes", label: "Individuals and outcomes" },
              ]}
            />

            {/* Part 5. What we'd build */}
            <LiquidHeading id="build" kicker="Part 5 · What we'd build" claim="proposal">
              Each bottleneck points at something buildable
            </LiquidHeading>
            <LiquidText>
              <p>
                None of these is tested here. Each names the bottleneck it targets and the bar it would have to clear.
              </p>
              <Beat>The representative as a default delegate</Beat>
              <p>
                For people with no record. Whoever has no delegate for a topic would be represented by their
                district&apos;s representative rather than not at all. The bar: nobody with an empty record falls below
                being represented.
              </p>
              <Beat>A backup delegate for loops</Beat>
              <p>
                For loops at high turnout. Each topic gets a second choice, used when a delegation loops back. Ranked
                backup delegates are an existing idea in the literature; the study shows where they would matter: at{" "}
                {highest}, loops are liquid&apos;s whole overhead.
              </p>
              <Beat>A ceiling set by each voter</Beat>
              <p>
                For people who would vote. Today one limit is set for the whole city, and it pushes people who would
                vote into handing their questions over. A ceiling set by each voter would let them keep the questions
                they would answer.
              </p>
              <p>
                <span className="mr-1.5 inline-block align-middle">
                  <ClaimLabel claim="exploratory" />
                </span>
                The evidence for it comes from an analysis made after the freeze. Handing over one more topic at a time
                traces liquid&apos;s whole curve, from voting yourself to handing over everything. Up to {lastRise},
                every topic handed over raises fidelity. From {firstFall} it does not: at {highest}, every topic handed
                over lowers it, from {dec(highCurve[0].fidelity)} to {dec(highCurve[highCurve.length - 1].fidelity)}.
                Keeping a question buys fidelity only where a voter would vote on it often enough to beat their
                delegate.
              </p>
            </LiquidText>
            <LiquidFigure>
              <HandoverFigure />
            </LiquidFigure>
            <LiquidText>
              <Beat className="pt-0">A personal agent</Beat>
              <p>
                For people with no record, and for the cold start. A model of the voter casts the ballots they would
                leave empty. The people who need it most have no record to learn from, so its input would be the
                preference interview of demo 2: the cost moves from every ballot to one onboarding conversation.
              </p>
              <ul>
                <li>
                  The bars at Swiss turnout: to beat a representative as the default, its ballots must match the voter
                  more than {pct(agentBars.representative)} of the time they are cast; to beat a chosen delegate, more
                  than {pct(agentBars.delegate)}.
                </li>
                <li>No accuracy is claimed: demo 2 has no measured ballot accuracy yet.</li>
                <li>
                  One model serving everyone shares its errors across every ballot it casts: the concentration problem
                  in a new form.
                </li>
              </ul>
              <p>
                <strong>What none of them fixes:</strong> liquid delegation still borrows engagement rather than
                creating it, and its outcomes still drift further from full turnout than direct voting&apos;s.
              </p>
              <p>
                The follow-up is one pre-declared study of fallback rules for the questions voters keep: keep them, a
                representative default, or an agent at an assumed accuracy. It will be linked here once it has results.
              </p>
            </LiquidText>
            <StudyLinks
              links={[
                { anchor: "exploratory", label: "What overhead is worth" },
                { anchor: "proposals", label: "What could be built" },
              ]}
            />
          </TurnoutProvider>
        </StoryDataProvider>
      </div>

      {/* Part 5's payoff: the account app */}
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
            people, their delegations and the votes are made up; the routing is real. The proposals above are not built
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
        <LiquidText>
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
