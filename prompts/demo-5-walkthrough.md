# Demo 5: the liquid-democracy walkthrough

Status: planned 2026-11-19, after the frozen benchmark was published (PR #110).
Decisions made with Ben the same day are recorded below. Nothing is built.

This is build step 7 of
[`demo-5-liquid-democracy.md`](demo-5-liquid-democracy.md). It replaces the
2026-11-14 outline in that doc's "Presentation" section.

## Why a walkthrough

The claim is about a population, so one account cannot show it. The
walkthrough reports the study as a scrolling essay, in the manner of the
apportionment essay and the districting walkthrough. It answers one
question:

> Can people hand most of their civic decisions to delegates they choose,
> and still be represented better than by an elected representative?

The answer the frozen results give: yes, clearly, in the middle of the
turnout range. The pre-registered test does not establish it, because at both
ends of the range liquid delegation cannot keep its overhead low. The two
ends fail for opposite reasons, and each points to something that could be
built.

## Decisions

### Stance: report, then explain, then explore

The page leads with the pre-registered verdict, *overhead condition not met
where liquid is ahead*, word for word, and does not soften it. Explanation
follows; ideas come last.

### Every claim carries one of three labels

- *Frozen result:* from `eval/benchmarks/delegation_frontier_v1/`, read under
  the rules fixed before the run.
- *Exploratory:* computed after the freeze, from the same cities or the
  published summaries. It never changes a verdict, and it says so where it
  appears.
- *Proposal:* a design idea the study did not test.

The label is visible on the page, as a small tag beside the section or
figure, not only in the methods.

Animations of how the system works are illustrations: they make no claim.
An animation that shows a result takes its numbers from the frozen data and
carries that result's label.

### Form: a scrolling essay, animated throughout (settled 2026-11-19)

Animations carry the mechanism and some of the results:
- how delegates are chosen from the record;
- how a ballot's questions are routed;
- how votes travel on, and how loops send them back;
- the city motif changing as the reader changes arrangement or turnout;
- the result curves drawing as the dial moves.

They follow the apportionment essay's conventions:
- scroll-linked and reversible;
- a skip control and a reduced-motion path that shows the end state;
- nothing locks scrolling;
- built from the story kit (`Scrolly`, `scrolly-reveal`, `slide-swap`, the
  canvas dot field).

### Route and the app (settled 2026-11-19)

- **The walkthrough takes `/liquid`.**
- **The account app sits at the bottom of the page for now** (§16). It will
  be woven into the walkthrough later, where it fits the story.
- **The app is a separate scenario.** Its city of 240 residents uses free-text
  categories routed by the decision model, not the study's cities. The
  section says so.
- **The app stays dynamic.** It needs the Python service at request time and
  keeps its existing fallback when the service is down.
- **The rest of the page is static.** The app section is the only part that
  is not.
- **Implementation:**
  - the app shell moves out of `app/liquid/layout.tsx` into a route group for
    the app's screens (`/liquid/votes`, `/liquid/people`, and so on);
  - its hub renders in the page's bottom section;
  - the app's "Hub" link points to that section.

### Reader interaction: the turnout dial

One control runs through the page, as the state picker does in the
apportionment essay. The reader sets mean citizen turnout.
- **It snaps to the recorded levels,** 0.1 to 0.9, with 0.45 marked as Swiss
  turnout.
- **Every turnout-dependent figure and animation follows it.**
- **Nothing is interpolated** except where the study's own reading does (the
  crossing near 0.19).

### Visual motif: one city of 500 dots

Each resident is a dot in one of five districts. For the chosen arrangement
and turnout, a dot shows two things: whose ballot counted for that resident,
and whether it matched them, contradicted them, or was missing. This makes
the three shares behind fidelity visible one person at a time.

The city is a real primary city (position 1), precomputed at build time from
the frozen code (see "Data").

### Static-first

Except for the app section, data comes from build-time artifacts, never a
live Python call. The design doc's earlier "small live re-run" becomes the
precomputed city.

### Look

- **The story kit:** `components/story/`, `<StoryRoot>`, its tokens and the
  validated palette in `lib/story/palette.ts`.
- **Every figure ships a data table,** and chart text uses ink tokens, never a
  series colour.
- **Figures reuse the benchmark's encodings,** so the page and
  `eval/benchmarks/delegation_frontier_v1/README.md` read the same way:
  - liquid in the first series colour, comparisons in the second;
  - failing gate levels in the critical colour;
  - each sweep's baseline as a dark line, its settings as an ordinal ramp.

## The walkthrough

Every number below is from the published summaries unless marked. Section
labels are in brackets.

### 0. Cold open: three ways to be represented [frozen]

This is an average resident of a city at Swiss turnout (0.45), across the
160 questions they are later scored on:

| Arrangement | Ballot matches them | Contrary ballot | No ballot |
|---|---|---|---|
| Direct voting | 45.0% | 0% | 55.0% |
| District representative | 60.6% | 35.3% | 4.0% |
| Liquid delegation | 70.9% | 22.6% | 6.6% |

The beat: voting yourself is never wrong but usually absent. The
representative is almost always present but against you a third of the
time. Liquid delegation hands each topic to someone you chose.

The figure is three stacked strips, then the city motif filling in for each
arrangement.

### 1. The city [frozen: design facts]

A city is one run of the whole experiment:
- **500 residents** in five districts of 100. Their beliefs are drawn from a
  model fitted to the CES 2024 Common Content.
- **Eight topics.** Each has 50 past questions and 20 later ones.
  - The past votes form the public record people choose delegates from.
  - Every arrangement is scored on the later questions.
- **Turnout.** Each resident's own rate follows the dial. The spread across
  residents is calibrated to Geneva's register. Office holders, the
  representative included, vote at 0.96 (Voteview).

The benchmark has 200 such cities, identical except for their seed. Each is
run at every turnout level with the same residents.

### 2. Two measures [frozen]

- **Fidelity:** the share of a voter's questions on which the counted ballot
  matches their sincere choice. It is the match share in §0's table.
- **Overhead:** the share of questions a voter decides themself.

One note is planted here and paid off in §12: fidelity scores a contrary
ballot the same as no ballot.

### 3. How it works [illustration]

Animated, one mechanism per step, on the illustrative city:

- **Choosing a delegate from the record.** For one resident and one topic:
  - each candidate's past votes line up against the resident's, and the
    agreements are counted;
  - the Beta-binomial lower bound ranks the candidates, so a short shared
    record counts for less;
  - the resident hands the topic over only if the best candidate's bound
    clears the city's acceptance level; otherwise they keep it;
  - a resident with an empty record has nothing to count, so they keep
    everything. This sets up §6.
- **A ballot arrives.** Each question is filed under its topic. It goes to
  the voter's delegate for that topic, or stays with the voter.
  - The study routes exactly.
  - What a real router does is shown in §10, and the animation can build on
    the app's routing tracer.
- **Votes travel on.** A delegate applies their own delegations to the votes
  they receive, so a vote can pass through several people.
  - A loop of mutual delegation sends votes back to their owners, who then
    decide for themselves. This sets up §6's high edge.
  - A resolver who does not vote leaves every vote they hold empty.
- **The calibration.** Each city's acceptance level is the highest at which
  overhead on the past questions stays at or under 10%.

### 4. Five arrangements on one plane [frozen]

The framing figure: overhead against fidelity, at the dial's turnout. The
values at 0.45:

| Arrangement | Overhead | Fidelity |
|---|---|---|
| Full turnout (reference) | 1 | 1 |
| Direct voting | 1 | 0.450 |
| District representative | 0.010 | 0.606 |
| Personal proxy | 0.097 | 0.689 |
| Liquid delegation | 0.098 | 0.709 |

Moving the dial moves the points. The plane holds only the calibrated
arrangements; liquid's own curve on it is §12's exploratory figure.

### 5. The result: Figure 1 [frozen]

- **The crossing.** Liquid overtakes the representative near turnout 0.19.
  The 95% range for the crossing is (0.1, 0.3].
- **The lead.** Liquid leads by +10.2 points at Swiss turnout, and by at
  least δ = 2 points at every level from 0.3 to 0.8.
- **The verdict.** The test requires at least 95% of cities to keep liquid's
  overhead at or under 10% at every level where it leads. Only 7.5% do at 0.2
  and 4% at 0.9, so the verdict is *overhead condition not met where liquid
  is ahead*.

The figure is the benchmark's Figure 1:
- the all-city curve and its band;
- the cap-only curve where it differs;
- the share of cities under the cap, below.

The curve draws as the dial moves. A sidenote explains the confidence range:
it ends at 0.3 because the 15 cities under the cap at 0.2 have a band that
still dips below zero.

### 6. Two edges that fail for opposite reasons [frozen]

**Low turnout: overhead nobody uses.** A resident with no votes in the
history has nothing to choose a delegate by. They keep their own vote, and
they rarely use it.
- **The overhead is these residents.** At 0.1 liquid's overhead is 23.6%,
  and 22.8% of residents have an empty record.
- **They are barely represented.** Empty-record residents' fidelity under
  liquid is 0.001 to 0.003 at every level, against about 0.60 under the
  representative.
- **Light-record residents lose too.** These residents cast under 10% of the
  history questions themselves, empty records included: 26% of the city at
  0.45. They do slightly worse under liquid than under the representative at
  every level up to 0.5 (0.588 against 0.606 at 0.45).
- **It isn't caused by topics.** The personal proxy has the same floor (12.2%
  overhead at 0.2), so the cause is choosing by record.

**High turnout: overhead people do use.** Voters on a loop of mutual
delegations decide for themselves.
- **Loops are the overhead.** At 0.9, 11.5% of voter-question pairs sit on a
  loop, and liquid's overhead is 11.5%. The questions liquid's voters keep
  match them 99% of the time.
- **It is specific to topic delegation.** The single proxy's loop share is
  7.0%, and it meets the cap in 98.5% of cities.
- **The cap pushes people who would vote into delegating.** Direct voting,
  with full overhead, passes liquid between 0.7 (0.700 against 0.766) and 0.8
  (0.800 against 0.779).

The section's point: one overhead number cannot tell a burden people carry
from one they drop.

Figures:
- empty-record and light-record fidelity against the representative, across
  the dial;
- the loop share across the dial;
- the city motif showing who keeps what.

### 7. Where the lead comes from: the ladder [frozen]

The declared chain from the representative to liquid, at 0.45:

| Step | Points |
|---|---|
| Sharing: own one of the three local candidates | +0.6 |
| Choice by non-voters | +1.1 |
| City-wide proxy (499 candidates, onward delegation, acceptance, own-rate attendance) | +7.3 |
| Topic specialisation: eight topic delegates instead of one proxy | +2.0 |
| Platform against record (subtracted) | −0.7 |

- **The signature feature adds least.** Topic specialisation is real but
  never shown worth Δ: +1.97 [+1.82, +2.12] at 0.45, size unresolved.
- **The proxy step bundles several changes,** and no matched arm separates
  them. So the copy says most of the lead "arrives with" the single proxy,
  not "is caused by" it.

### 8. Delegates who don't show up: Figure 2 [frozen]

- **Attendance is not the bottleneck.** Chosen delegates vote 97% of the time
  when they hold someone's vote at 0.45 (92% at 0.1).
- **A floor helps a little.** Attendance of 1 adds 2.9 points at 0.1, about 1
  at 0.45, and less above.
- **It can't rescue the low end.** At 0.1 liquid still trails by 7.7 points
  even if every delegate always votes.

The figure is the benchmark's two-panel Figure 2.

### 9. What the lead depends on: the sweeps [frozen]

The figure is the sweeps chart, one panel per family. Highlights in copy:
- **History length.** The lead grows with the public record. With 10
  questions per topic, the cap fails at every level.
- **Turnout spread.** Liquid borrows engagement; it does not create it.
  - An even electorate cuts the lead at 0.45 to +4.4 and moves the crossing
    to about 0.35.
  - It is also the only point where the gate holds everywhere.
- **Within-topic coherence.** The only family that shifts the whole curve.
  Consistent views (×0.5) give +13.6 at 0.45, the highest lead in the sweeps.
- **Districts.** No effect.
- **Agenda drift.** Fidelity is unchanged, but the cap breaks.
- **Belief generator.** The one-factor model costs liquid about 5 points.

A sidenote explains why 12 of 19 sweep threshold ranges are unbounded: at 48
cities, sparse cap-meeting levels meet the frozen band's rule.

### 10. Costs the headline does not show [frozen]

- **Concentration.** A district representative decides 20% of every
  question.
  - Under liquid at 0.45, the largest single delegate decides 28.5% of a
    question's votes, and 43.7% on a city's worst question.
  - That share is 39.6% at 0.2 and 43.5% at 0.1.
- **Two kinds of poor representation.** Under liquid, 6.3% of voters are
  represented on fewer than half their questions; under the representative,
  17.5%.
  - Liquid's failures are absences: no ballot on 73% of their questions.
  - The representative's are contradictions: a contrary ballot on 54%.
- **Cold start.** The 10% is steady state. Counting the history period, when
  everyone decides every question to build the records, liquid's lifecycle
  overhead is 74% at 0.45, and 74% to 78% across the dial. (The design doc's
  pre-run estimate was 71% to 74%; these are the measured values.)
- **Routing.** The study assumes every question reaches the right topic.
  - What the real router does is animated here, with its measured error from
    `eval/benchmarks/delegation_router_v1/`.
  - A false delegation costs fidelity; a false keep costs overhead.
  - H1 under routing error is a declared follow-up, not a result.

### 11. Individuals and outcomes [frozen, with one interpretation]

Agreement with full-turnout outcomes at 0.45:

| Arrangement | Agreement |
|---|---|
| Direct voting | 97.4% |
| Liquid delegation | 85.3% |
| Personal proxy | 84.2% |
| District representative | 82.2% |

- **The contrast.** Direct voting represents individuals worst but matches
  outcomes best.
- **The interpretation, untested and labelled as such.** Random abstention is
  a fair sample. Delegation copies one person's deviations onto everyone who
  follows them.
- **The biggest caveat.** In this model turnout is independent of opinion,
  and real abstention is not. That is the largest caveat on any outcome
  claim.
- **Ostrogorski-style cases** (from the 2026-11-14 outline) appear only if the
  illustrative city contains one. Otherwise they are dropped, not
  constructed.

### 12. What overhead is worth [exploratory]

Two analyses made after the freeze. Each is labelled on the page and in its
data, and neither touches the verdict.

**a. Liquid's handover curve.** This is the curve §4's plane is missing.
- **What it varies.** Each voter hands over topics one at a time, in the
  order of the top candidate's lower bound (open question 7's default), from
  none (direct voting) to all eight.
- **Where it is drawn.** At every recorded turnout level (settled
  2026-11-19), on the same 200 primary cities. The page's dial picks the
  level.
- **What it plots.** Each point is mean overhead against fidelity, with the
  three shares in its data table.
- **What the endpoints already show.**
  - At 0.45 the curve must slope down overall: direct voting scores 0.450
    against liquid's 0.709.
  - At 0.9 it slopes up, 0.900 against 0.790. So its direction flips between
    0.7 and 0.8.
- **The expected lesson.** Extra overhead buys fidelity only where people
  would use it. The page will show the curve as it comes out, not this
  expectation.
- **Where it lives.** Its own exploratory benchmark,
  `eval/benchmarks/delegation_handover_v1/`, in its own PR.
  - It is built by a new module that calls the frozen functions unchanged.
  - A dated exploratory note goes in the design doc.
- **What it showed (run 2026-11-19, slice A).** The expectation held. See
  the benchmark's README for the numbers.
  - Fidelity rises with every topic handed over up to 0.7. At 0.8 it peaks
    at depth 2. At 0.9 it falls with every topic.
  - The turn sits where a delegated pair's fidelity (0.75 to 0.76) drops
    below turnout.
  - The curve is close to a straight line, and the calibrated point lies on
    it, short of its end. At 0.3 to 0.5, handing over everything beats the
    calibrated point on both measures.

**b. How bad is a wrong ballot?** Each arrangement is scored as match − w ×
contrary.
- **w = 0 is frozen fidelity.**
- **w = 1** counts a contrary ballot as −1, which is how it acts on a binary
  majority.

Shown as a static table at w = 0 and w = 1. This is tentative (2026-11-19);
a slider stays possible once the section exists. Everything comes from the
published shares, so no new runs are needed.

At w = 1:
- the representative is about 0.25 at every turnout;
- liquid rises from 0.265 at 0.1 to 0.584 at 0.9, ahead of the
  representative at every level;
- direct voting equals turnout, so it ties liquid at 0.5 and leads from 0.6.

The beat: the choice of metric is a value judgment, and it changes which
arrangement looks best.

### 13. What could be built [proposals]

Each proposal names the failure it targets and the bar it must clear. None
is tested here.

- **The representative as default delegate.** It targets the low edge: no one
  with an empty record falls below representation.
- **A backup delegate for loops.** It targets the high edge.
- **The cap as each voter's own ceiling, not a city-wide target.** People who
  would vote keep their questions. It targets the high end, where delegation
  now costs fidelity.
- **A personal agent (the demo 2 link).** A model of the voter casts the
  ballots they would leave empty.
  - The people who need it have no record to train on. Its input is demo 2's
    interview, so the cost moves from every ballot to one onboarding
    conversation, and demo 2's question efficiency is the exchange rate.
  - It must be scored on all three shares. On a two-option question, a coin
    flip cast for an abstainer raises frozen fidelity.
  - The bars at 0.45: to beat a representative default, its ballots must
    match more than 63% of the time they are cast; to beat a chosen delegate,
    about 74%.
  - No accuracy is claimed: demo 2 has no measured ballot accuracy yet.
  - One model serving everyone shares its errors across every vote it casts,
    which is the super-delegate problem in a new form.
- **The follow-up study.** One pre-declared hypothesis on fallback rules for
  questions voters keep.
  - Its arms are keep, a representative default, and an agent at assumed
    accuracy, all scored on the three shares.
  - It is declared and run separately. The page links to it only once it has
    results.

### 14. What is left out [frozen: design]

- **What representatives do:** deliberation, agenda setting and brokering
  across issues.
- **Behaviour:** strategic voting, campaigns and changing preferences.
- **Unweighted questions:** bundling's trade of minor issues for major ones
  gets no credit.
- **Synthetic cities and exact routing.**
- **Finer categories than topics:** untested (H2).
- **Turnout independent of opinion.**

### 15. Methods and sources

- **The protocol:** frozen on 2026-11-19, merge commit `a50ebcc`.
- **The model:** the ODD (`prompts/demo-5-odd.md`), the CES 2024 fit, the
  Geneva register and Voteview.
- **Reproducing the benchmark:** `python -m eval.delegation_frontier
  verify`. The city records are kept locally, with their hashes committed.
- **Provenance** of the exploratory artifacts, and the three labels with what
  each may claim.

### 16. Try it: the account app [illustration]

The existing account app, at the bottom of the page for now: what using
liquid delegation could look like for one person.
- It is introduced as a separate, smaller scenario with free-text categories
  routed by the decision model.
- It is a design idea, not part of the study's claim.

Build step 8's changes are made here:
- regenerate the scenario with history-based delegation;
- add delegate recommendations and the representation scorecard.

## Figures and data

| § | Figure | Source | Label |
|---|---|---|---|
| 0 | Three stacked strips, then the city motif | `measures.csv`; illustrative city | frozen |
| 3 | Mechanism animations | illustrative city; frozen code | illustration |
| 4 | The plane, dial-linked | `measures.csv` | frozen |
| 5 | Figure 1, drawing with the dial | `levels.csv`, `thresholds.csv` | frozen |
| 6 | Empty- and light-record fidelity; loop share; city motif | `measures.csv`; illustrative city | frozen |
| 7 | The ladder | `decomposition.csv` | frozen |
| 8 | Figure 2 | `frontier.csv` | frozen |
| 9 | The sweeps | `levels.csv` | frozen |
| 10 | Concentration; lower tail; router animation | `measures.csv`; benchmark README; `delegation_router_v1` | frozen |
| 11 | Outcome agreement | `measures.csv` | frozen |
| 12a | Handover curve at every level | `delegation_handover_v1` | exploratory |
| 12b | Table at w = 0 and w = 1 | `measures.csv` | exploratory |
| 13 | Proposals, with bars from `measures.csv` | text | proposal |
| 16 | The account app | the Python service, live | illustration |

**`scripts/build_liquid_story.py`** reads only committed benchmark files. It
writes `public/data/liquid-story/` with a hash manifest of its inputs, and it
rebuilds byte for byte (a test checks this).

**`scripts/build_liquid_example_city.py`** recomputes primary city position 1
with the frozen code, at every recorded level. For each resident it keeps the
ballot and whether it matched, and the delegation steps the animations use.
- Where the local city records are present, it checks the city's aggregates
  against the recorded city.
- It always checks its own output hash.

**Copy numbers come from generated data**, as in the apportionment essay. A
test fails if a quoted number drifts from it.

## Slices

Each slice is its own PR.

| Slice | Contents | `/liquid` after merge |
|---|---|---|
| A | Exploratory handover benchmark at every level, and the w table; no UI | account app (unchanged) |
| B | Data pipeline, illustrative city, §0–4 with the mechanism animations, the app moved to the page's bottom | opening and how it works, app below |
| C | §5–8: the result, the two edges, the ladder, attendance | + the result |
| D | §9–11: sweeps, costs (with the router animation), outcomes | + robustness and costs |
| E | §12–15: exploratory, proposals, left out, methods | complete walkthrough |
| F | Build step 8 in the app (§16), then weaving it into the story | + the app's changes |

## Decisions settled 2026-11-19

1. **Route:** the walkthrough takes `/liquid`. The account app sits at the
   bottom of the page for now and is woven in later where it fits.
2. **Form:** a scrolling essay, with animations throughout, for the mechanism
   (routing, choosing from the record, votes travelling on and looping) and
   for some results.
3. **Handover curve:** every recorded level.
4. **Wrong-ballot weighting:** a static table at w = 0 and w = 1, tentatively.

## Still open

- Where the app is woven into the story, once the essay exists.
- Whether the wrong-ballot table becomes a slider.
