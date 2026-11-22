# Demo 5: the liquid-democracy walkthrough

Status: planned 2026-11-19, after the frozen benchmark was published (PR #110).
Decisions made with Ben the same day are recorded below. Slice A (the
exploratory handover benchmark) is published (PR #112). Slice B (the data
pipeline, the illustrative city, §0–4 and the app at the page's foot) is
published (PR #113), slice C (§5–8) too (PR #115) and slice D (§9–11) (PR
#116). Slice E (§12–15) is published (PR #117), so the walkthrough's
content is complete. "Built in slice B" to "E" below record the choices
made while building them.

**2026-11-20: the story outline.**
- `/liquid` becomes a five-part story built on that content, and the
  sections as built move to `/liquid/study`, the full study. Slice F built
  this from a first draft (PR #118).
- Ben revised the outline the same day:
  - the idea and the basic mechanism come first, as if everyone votes;
  - each problem is followed by its fix;
  - the verdict is held back until the turnout section.
- The five parts are now the idea, how it works, where the machinery breaks
  (with a fix for each), where it still struggles (with our answer to each),
  and the app.
- Two exploratory runs feed it: an everyone-votes reference point, and the
  fallback study.
- Styling waits until the core is built.

See "The story" and "Slices".

This is build step 7 of
[`demo-5-liquid-democracy.md`](demo-5-liquid-democracy.md). It replaces the
2026-11-14 outline in that doc's "Presentation" section.

## Why a walkthrough

The claim is about a population, so one account cannot show it. The
walkthrough reports the study as a long page that tells its story as the
reader scrolls, with a design of its own (see "Form"). It answers one
question:

> Can people hand most of their civic decisions to delegates they choose,
> and still be represented better than by an elected representative?

The answer the frozen results give: yes, clearly, in the middle of the
turnout range. The pre-registered test does not establish it, because at both
ends of the range liquid delegation cannot keep its overhead low. The two
ends fail for opposite reasons, and each points to something that could be
built.

## The story: `/liquid` (outline, revised 2026-11-20)

Ben revised the first draft the same day, after slice F had built it. The
first draft is in Git history (PR #118); "What changed" lists the
differences. The sections built in slices B to E stay, as built, at
`/liquid/study`, and the story takes its highlights from them.

Numbers here are for orientation. The page computes every number from the
generated data, as it does now.

### What the reader should take away

Set by Ben, 2026-11-20:
1. **What liquid democracy is,** and how it compares with representative
   democracy, including the key trade-offs.
2. **The mechanisms at work** in a liquid system, shown with animations and
   diagrams where they help.
3. **The limits and bottlenecks** that stand in the way of a successful
   deployment.
4. **Our proposed solutions** to some of them.

The impression to leave: a careful implementation of known theory, and ideas
of our own that improve on its limits.

### What changed from the first draft

- **The idea first, as if everyone votes.** Parts 1 and 2 show the system
  with every resident voting on every question. Turnout arrives in part 3,
  as the first thing that breaks it. At Swiss turnout a reader sees their
  own ballot match them less than half the time, which distracts from the
  idea.
- **Each problem is followed by its fix.** There is no separate proposals
  part, so the reader has the problem in mind when its solution arrives.
- **The verdict is held back.** There is no short answer at the top. The
  frozen verdict lands in part 4's turnout section.
- **Part 1 builds the case step by step:** direct voting, then a
  representative, then a proxy, then liquid delegation. The first draft
  named three arrangements at once.
- **Concentration is not a bottleneck.** Votes gathering around the people
  many others agree with on a topic is the mechanism working, and part 2
  shows it that way.
  - Part 4 notes that it grows as turnout falls: on average the largest
    decider holds 43.5% of a question's votes at 0.1, 28.5% at 0.45 and
    14.7% at 0.9. A representative holds 20%.
  - One sentence names the risk that stays open: capture, because someone
    holding many votes is a cheap target for lobbying.
  - The copy says "agree with", never "experts". Residents choose by
    agreement, and the model has no expertise in it.
- **The cold start is about history.** Choosing by record needs an initial
  history of votes, gathered somehow, before anyone can choose.

### Two pages

- **`/liquid`, the story.** Five parts, highlights only, the mechanism
  animations and the app.
- **`/liquid/study`, the full study,** as slice F left it: §0–15 as built,
  with every figure, interval, data table and the methods.
  - It keeps its section anchors, so the story can link to them.
  - It reuses the same components; nothing is rebuilt.
  - It links to the published benchmarks on GitHub.
- **Links between them.** Each part of the story ends with links to the
  matching sections of the study ("The full analysis"). The study opens with
  a line pointing back to the story.
- **The rigour stays visible on the story page, briefly.** A short "How we
  know" note goes with the verdict in part 4: the test was declared before
  the run, it ran on 200 synthetic cities from frozen commit `a50ebcc`, and
  the verdict is quoted word for word.
- **No expandable "deep dive" drawers.** The depth lives in the study.

### Labels: known theory and what is new

The claim labels stay: frozen, exploratory, proposal, illustration and
design. Proposed: a second small tag on mechanisms and proposals, either
*from the literature* or *new here*, with sources in the study's methods.
- A *from the literature* tag needs its source checked before it ships.
- A *new here* tag needs a literature check that the idea is not already
  published.
- Provisional mapping, from the design doc's references:
  - **From the literature:**
    - transitive, per-topic delegation (Christoff and Grossi; Kahng,
      Mackenzie and Procaccia);
    - everyone on a loop deciding for themselves (after Christoff and
      Grossi's default opinion);
    - backup delegates, as ranked delegations (Brill et al.; Colley, Grandi
      and Novaro);
    - vote concentration in a few "super-voters" (Kling et al. on
      LiquidFeedback; Gölz et al.).
  - **New here, pending that check:**
    - one population scored on fidelity and overhead under every
      arrangement, with a pre-declared test and a decomposition;
    - the two-edge diagnosis;
    - choosing delegates from the public record by a Beta-binomial lower
      bound with a calibrated acceptance level;
    - the decision-model router for free-text categories, with its measured
      error;
    - the representative as default, the per-voter ceiling, and the
      personal agent with its bars.
  - **To source or to claim:** dilution and bundling as the two costs of
    representation.

### The opening

- **The title stays** "Who Votes for You?".
- **The question, in one line:** can people hand most of their civic
  decisions to delegates they choose, and still be represented better than
  by an elected representative?
- **No answer yet** (Ben, 2026-11-20). The opening says the page shows how
  liquid delegation works, where it breaks and what we would build. It says
  the answer comes from a test declared before 200 synthetic cities were
  run, and that part 4 gives it.
- **The five parts, and two shortcuts:** to the full study and to the app.

### Part 1. The idea [exploratory reference]

**Message:** voting on everything yourself is the most faithful arrangement
and the most work. A representative costs almost no work, but you share them
with your district and they stand for you on everything. Liquid delegation
aims between the two: far less work than voting yourself, and more faithful
than a representative.

Every number in parts 1 and 2 comes from the everyone-votes reference run
(R1, under "Research the outline needs"), which is not yet computed. An
asterisk names what it assumes: everyone votes, and residents choose
delegates by agreement with their past votes. Parts 3 and 4 unpack both.

1. **A vote, end to end** (the opening animation). An arrangement is a rule
   for whose ballot counts for whom.
2. **Direct voting.** Everyone decides everything, so fidelity and overhead
   are both 100%. The work is the problem.
3. **A district representative.** One person decides everything for a
   district, at an overhead of about 1%. Representation costs fidelity
   twice:
   - dilution: you share the representative with your whole district;
   - bundling: one person stands for you on every issue.
4. **A proxy you choose.** Your own person, for everything. This removes
   dilution.
5. **Liquid delegation.** Your own person for each topic. This removes
   bundling too.
6. **The trade-off, on two measures:**
   - fidelity: how often the ballot counted for you matches yours;
   - overhead: how many questions you decide yourself.

   The four arrangements, and what each step adds.
7. **The city, in one paragraph:**
   - 500 made-up residents in five districts, with beliefs fitted to CES
     survey data;
   - eight topics, with a public record of past votes;
   - one of 200 such cities.

   The details stay in study §1.

Study only: the plane of five arrangements (§4). The frozen ladder at Swiss
turnout returns in part 4.

### Part 2. How it works: the basic version [illustration]

**Message:** liquid delegation is a few simple rules. This is the version
most proposals share (Ben, 2026-11-20), still with everyone voting.

1. **Topics are fixed in advance,** and each question arrives tagged with
   one.
2. **For each topic you name a delegate, or keep it.**
   - In the basic version you pick someone you trust.
   - The city's residents cannot trust anyone, so they pick by record: the
     person whose past votes on that topic agree with theirs most, given
     enough record to tell.
   - One sentence here; part 4 shows how it works.
3. **A ballot arrives.** A question in a delegated topic goes to your
   delegate, and the rest come to you. Once you delegate a topic, your own
   ballot on it does not count, even if you cast one.
4. **Votes travel on.** Your delegate's own delegations apply to the votes
   they hold, so a vote can pass through several people before someone
   decides it.
5. **Who ends up deciding.** Each decider's ballot counts for everyone whose
   vote reached them. Votes gather around the people many others agree with
   on a topic, which is the mechanism working (see "What changed").

Some systems let your own vote replace your delegate's. The study does not
model it, and one line says so.

**The app's first appearance.** The beats are drawn with the app's own
elements where one exists:
- a delegation card for beat 2;
- the routing receipt for beat 3;
- the vote page's chain for beat 4.

The app itself waits for part 5.

The study files every question under its topic without error. Filing real
questions is part 4's first problem.

### Part 3. Where the machinery breaks, and the fix for each [frozen, with proposals]

**Message:** real people miss votes. That one change opens gaps in the
rules, and a rule can close each one.

- **The dial arrives:** "now let people miss votes". The reader sets mean
  citizen turnout from 0.1 to 0.9, with Swiss turnout marked, and every
  figure from here follows it.
- **The resident from part 1 again,** now following the dial: their own
  ballots go missing, and so do some of their delegates'.
- **Each break has four pieces:**
  - what goes wrong, shown;
  - how often, frozen;
  - the fix, with its label;
  - the evidence for the fix, or a note that there is none yet.

**3a. A delegate who does not vote.** Every vote they hold goes uncast.
- At Swiss turnout 1.4% of delegated votes are lost, and 5.4% at 0.1.
  Delegates who hold votes cast them 97% of the time at 0.45.
- The fix [proposal]: a backup delegate (from the literature, as ranked
  delegation), then the representative as the last default.
- Evidence: the fallback study (R2).

**3b. Nobody to delegate to: the empty record.** A resident who never votes
has no record, so no candidate can clear the bar. They keep every topic and
rarely vote.
- At 0.1, 22.8% of residents have an empty record.
  - Their fidelity is 0.001 to 0.003, against about 0.60 under the
    representative.
  - They account for nearly all of liquid's 23.6% overhead at that level.
- The same happens under the personal proxy, so the cause is choosing by
  record, not delegating by topic.
- The fix [proposal]: the representative as default delegate.
- Evidence: R2.

**3c. Loops.** When nearly everyone hands a topic over, chains have nowhere
to end but a loop. In the example city 96% of handed-over votes end at one
(3,590 of 3,740).
- The loop rule (from the literature, and in the frozen study): everyone on
  a loop decides for themselves, so no vote is lost.
- Its cost is work handed back. At 0.9, 11.5% of all voter-question pairs
  sit on a loop, which is all of liquid's overhead there.
- A backup delegate outside the loop would take that work over, but at high
  turnout it costs fidelity:
  - a delegated vote matches 0.75 to 0.76 of the time;
  - a resident at 0.9 turnout who votes for themselves matches about 0.9 of
    the time.

  So this fix depends on turnout, and part 4's per-voter ceiling takes it
  up.

Study only: the light record, the kept-city figure, and the attendance
frontier.

### Part 4. Where it still struggles, and our answer to each [frozen, exploratory, proposal]

**Message:** three limits that no rule settles: filing questions under
topics, building the history people choose by, and getting enough people to
vote. Each comes with the answer we would build and the bar it must clear.

**4a. Strict categories: the decision-model router.**
- Real questions are not tagged in advance, and one can touch several
  topics. Filing them is a judgment:
  - a false delegation costs fidelity;
  - a false keep costs work.
- Our answer [new here, pending the check]: a decision model files
  free-text questions, and keeps a question with the voter when unsure.
- Evidence [frozen, `delegation_router_v1`]: at the operating threshold of
  0.7, coverage is 53.7%, with 1.4% false delegations and 6.8% false keeps.
  A higher threshold trades coverage for caution.

**4b. The initial history: choosing from the record, and what it costs.**
- How the city chooses, in full [design]:
  - each candidate's past votes are lined up against the resident's, and
    the agreements counted;
  - a lower bound counts a short shared record for less;
  - each city calibrates an acceptance level, so overhead on past questions
    stays at or under 10%.
- **The short record:** a resident with one ballot in the whole record falls
  just short of the bar and keeps everything.
- **The cold start** [frozen]: before anyone can choose by record, everyone
  decides everything.
  - Counting that history, liquid's overhead at Swiss turnout is 74%
    instead of about 10%. The figure depends on how long the city runs after
    its history.
  - With a short history (10 past questions per topic), the cap fails at
    every level.
- **Our answers** [proposal]:
  - The representative as default lets a city start as representative
    democracy while records build. A resident who never votes still never
    builds one.
  - The personal agent (the demo 2 link): its record would come from one
    interview instead of a history of votes.
    - Its bars at 0.45: its ballots must match 63.2% of the time to beat a
      representative default, and 74.7% to beat a chosen delegate.
    - No accuracy is claimed.
    - One model for everyone shares its errors across every ballot it
      casts.

**4c. Turnout: how much is enough** [frozen]. This is the study's own
question, and its verdict lands here.
- **The result, following the dial:**
  - liquid overtakes the representative near 0.19, with a 95% range of
    (0.1, 0.3];
  - it leads by +10.2 points at Swiss turnout;
  - it leads by at least 2 points at every level from 0.3 to 0.8.
- **The verdict, word for word:** *overhead condition not met where liquid
  is ahead*.
  - The test needs 95% of cities under the 10% cap at every level where
    liquid leads.
  - Only 7.5% are under it at 0.2, and 4% at 0.9.
- **The two edges, tied back:**
  - the low edge is part 3's empty record;
  - the high edge is the city-wide cap pushing people who would vote into
    delegating. Direct voting passes liquid between 0.7 and 0.8.
- **Where the lead comes from:** most of it arrives with one chosen proxy
  (+7.3 points of the ladder at 0.45). Topics add about 2.
- **Concentration** grows as turnout falls (see "What changed").
- **"How we know"** (see "Two pages").
- **Our answer for the high edge** [proposal, with exploratory evidence]: a
  per-voter ceiling instead of a city-wide cap. The handover curve,
  following the dial:
  - fidelity rises with every topic handed over up to 0.7;
  - at 0.8 it peaks after two topics;
  - at 0.9 it falls with every topic.
- **What delegation cannot change** [frozen, with one interpretation]:
  - **It borrows engagement; it does not create it.** With an even
    electorate the lead at 0.45 falls to +4.4 points, and the crossing moves
    to about 0.35.
  - **Better for individuals, not for outcomes.**
    - Agreement with full-turnout outcomes at 0.45 is 97.4% under direct
      voting, 85.3% under liquid and 82.2% under the representative.
    - The interpretation, labelled untested: random abstention is a fair
      sample, while delegation copies one person's deviations onto everyone
      who follows them.
    - The caveat: in this model, turnout does not depend on opinion.
  - No proposal creates engagement, and the page says so.

Study only: the cap-only curve, the confidence-range sidenote, the full
ladder, attendance (Figure 2), the sweeps, the lower tail, lifecycle
overhead across the dial, the wrong-ballot table, and outcomes for every
arrangement.

### Part 5. What we'd build: the app [illustration, proposals labelled]

**Message:** the fixes together make a system someone could build. Here it
is to try.

- **The design, assembled.** One diagram stacks the fixes from parts 3 and 4
  on part 2's basic version, each with its label and its evidence.
- **The app** [illustration] is a plausible implementation of that design.
  See "Slice H".
  - It is a separate city of 240 residents, with free-text categories and
    the real decision model. It is not evidence.
  - On the page: the hub, one vote and your delegates. The full-screen app
    keeps the rest: Incoming Votes, Profile, Activity, City Results and
    About.
  - The hub's anchor stays `#app`.
- **Preset scenarios,** each a seeded starting state that shows one problem
  and its fix:
  - "you've never voted": the representative steps in;
  - "your delegate stops voting": the backup delegate, then the
    representative;
  - "your chain loops back to you": the loop rule, and the backup delegate;
  - "you'd rather keep more": the ceiling.

  Free play and reset stay.

### The close

- What the study leaves out (§14), as a short list.
- Links to the full study, the benchmarks and the design doc.

### Animations and diagrams (slice G)

**Decided by Ben, 2026-11-20:**
- Each one plays once when it scrolls into view, with a replay button.
  Reduced motion shows the end state, and nothing locks scrolling.
- The example city carries through wherever it fits.
- Mechanisms are drawn with the app's elements where one exists.
- Numbers come from the generated data. An animation that shows a result
  carries that result's label.

**The list,** numbered as first proposed, with Ben's descriptions
(2026-11-20). Items 8, 9 and 13 became one scene.

| # | Animation or diagram | Part | Ben's description | Data |
|---|---|---|---|---|
| 1 | A vote, end to end | 1 | An animated graph with residents as nodes and directed edges. A ballot question goes in, the graph sorts the votes to the options, and a tally with its winner comes out. | example city, everyone votes (R1) |
| 2 | The structures: you alone; your district and its representative; a proxy; a delegate per topic | 1 | As proposed, with the proxy added as its own step. | design |
| 3 | Dilution and bundling | 1 | As proposed. | design |
| 4 | The trade-off: the four arrangements on fidelity and overhead | 1 | No turnout yet. The idea: liquid lowers overhead against direct voting and raises fidelity against a representative. It shows the data, with an asterisk saying its assumptions are unpacked later. It replaces the three-ways figure at Swiss turnout. | R1 |
| 5 | One resident's ballots, question by question | 1, then 3 | Everyone votes at first. The turnout effect waits for part 3. | example city, R1, then the dial |
| 8, 9, 13 | Part 2 as one scene, in three stages, one per beat | 2 | **A ballot arrives:** a ballot measure, with scribbled lines where the question would be and a yes and a no box, shrinks into a glowing orb. The orb goes to the resident, who has graph edges to their delegates. Many orbs float in and are sorted, each into the edge for its topic, by colour: a yellow orb to the yellow delegate, red to red. **Votes travel on:** a slight zoom shows one delegate passing that colour on to another delegate. **Who ends up deciding:** zoom out to a fuller graph, with orbs flowing around the network, no longer coloured. | the typical resident's delegates, one onward chain and the city's delegation graph, with everyone voting (new data) |
| 11 | A delegate who does not vote, and the fixes | 3a | The delegate drops the orb and it cracks. Then arrows let the reader swipe through fixes that catch it: **you** catch it yourself, and your overhead bar, drawn like a health bar, bumps up; **an elected representative**, whose job is still to vote for everyone, catches it; **a personal agent**, a model of you, votes on your behalf. | `mechanism.lost`; R2 for the representative |
| 17 | Nobody to delegate to | 3b | As proposed (residents with no record grey out), then the same swipe-through fixes as 11. | `empty_records`, `liquid_reason`; R2 |
| 10, 18 | Loops: chains ending at a loop, the loop rule, and loops multiplying as turnout rises | 3c | As proposed. | `mechanism.loop`, `loops_per_topic`, `liquid_reason`, R1 |
| 21 | Routing errors | 4a | Start from the app's routing tracer. | `results.router` |
| 6, 7, 12 | Choosing from the record, the short record, and the acceptance level | 4b | As proposed. | `mechanism.showcase`, `short_record`, `calibration` |
| 20 | The cold start, as a timeline | 4b | As proposed. | `lifecycle_overhead` |
| 27 | The personal agent: an interview, a model, filled ballots against the bars | 4b | As proposed. | `agent_bars` |
| 14 | The result curve, drawing with the dial | 4c | As proposed. | `results.levels` |
| 15 | The ladder | 4c | As proposed. | `decomposition` |
| 16 | "How we know", as a timeline | 4c | No comment yet: optional, built last if at all. | the protocol |
| 26 | The per-voter ceiling on the handover curve | 4c | As proposed. | `exploratory.handover` |
| 22 | Borrowed engagement | 4c | As proposed. | the sweeps |
| 23 | Individuals and outcomes | 4c | As proposed. | `outcome_agreement`, the city's winners |
| 24, 25 | The design, assembled | 5 | As proposed. | design |
| 19 | Concentration | — | Folded into the third stage of 8, 9 and 13, plus one line in 4c. | |

**G's design** (draft, 2026-11-20):
- **One visual vocabulary,** from Ben's descriptions:
  - a vote is a glowing orb;
  - residents are nodes, and delegations are directed edges;
  - each topic has its own colour: eight topics, the validated categorical
    palette in its fixed order, checked with the palette validator in both
    themes;
  - a ballot is a card with scribbled question lines and a yes and a no box;
  - overhead is a bar drawn like a health bar.
- **One stage.** A shared network component (nodes, edges, orbs moving along
  edges) serves item 1, part 2's scene, part 3's breaks and part 5's
  assembled design, so the city carries through. It is SVG driven by
  `requestAnimationFrame`. The site has no animation library, and the
  apportionment essay's figures are hand-rolled the same way, with
  `useReducedMotion`.
- **Playing.** Each animation plays once when scrolled into view, with a
  replay button. Reduced motion shows the end state. The swipe-through fixes
  (11, 17) are arrow buttons, reachable by keyboard, each option with its
  own still end state.
- **Data.** Part 2's scene needs the typical resident's eight delegates, one
  onward chain and the city's delegation graph with everyone voting: a small
  addition to `city.json`'s everyone block, built by the example-city
  script and labelled exploratory.
- **Labels.**
  - Part 2's scene is an illustration.
  - In 11 and 17, "you catch it" is direct voting; the representative is
    R2's arrangement; the personal agent is a proposal with no claimed
    accuracy.
  - The health bar's bump is drawn, not quoted as a number, unless a
    computed value exists.
- **Sub-slices,** each its own PR:
  - **G1 (built):** the stage, the vocabulary and part 2's scene (8, 9,
    13). It replaces part 2's three placeholders.
  - **G2 (built):** part 1's diagrams (1, 2, 3) on the same stage.
  - **G3 (built):** part 3's breaks (11, 17, 10 and 18) with the
    swipe-through fixes, using R2's results.
  - **G4 (built):** part 4 (21, 6, 7 and 12, 20, 27, 14, 15, 26, 22, 23).
  - **G5 (built):** part 5's assembled design (24, 25); 16 not built.
- **Open:**
  - ~~The backup delegate~~: added as a fourth fix (Ben, 2026-11-20).
  - Item 16 has no description.

### Research the outline needs

Each new analysis is declared before it runs and says what role it plays,
under the one-hypothesis rule. Both are exploratory: neither changes the
frozen verdict, and the page says so.

**R1. Everyone votes: a reference point** [exploratory; descriptive, no
hypothesis].
- **What:** every arrangement, with the ladder's steps, on the 200 primary
  cities, with every resident and every office holder voting on every
  question.
- **Why:** parts 1 and 2 show the system before turnout, and the frozen grid
  stops at 0.9.
- **How, without touching `delegation/comparison/`:**
  - turnout has its own random stream, so setting the population's legacy
    uniform bounds to [1, 1] keeps each city's residents and questions;
  - office holders and delegates vote at rate 1 through a `TurnoutPolicy`;
  - confirmed on one city: every arrangement accepts the setting, each
    city's acceptance level calibrates as it does at the recorded levels,
    and the residents and questions are the frozen city's.
- **Declared** 2026-11-20 in
  [`demo-5-liquid-democracy.md`](demo-5-liquid-democracy.md), "Exploratory
  analyses after the freeze", item 3. The runner is
  `eval/delegation_everyone_votes.py`.
- **Seen in that one city (position 1):** liquid's overhead is above the
  10% cap, all of it on loops, because with everyone voting nearly everyone
  hands every topic over.
- **Run and published 2026-11-20** (`eval/benchmarks/delegation_everyone_votes_v1/`,
  from commit `770f413`). The run confirms the one city:
  - liquid 81.0% fidelity at 18.3% overhead; the proxy 79.0% at 10.6%; the
    representative 63.3% at 1%;
  - no city's liquid stays under the cap (the proxy does in 114 of 200), and
    all of liquid's overhead is loops;
  - the ladder: +17.8 points over the representative, 15.8 of them before
    topics, and topics add 2.0;
  - the largest decider holds 10.3% of a question's votes on average,
    below a representative's 20%.
- **What it means for the copy:**
  - part 1 says "far less work than voting yourself" (about a fifth) and
    does not promise the cap;
  - part 3c can say the loops grow as turnout rises, from 0.8% of
    voter-question pairs at 0.1 to 18.3% with everyone voting;
  - "What changed"'s concentration note gains its everyone-votes point.
- **Output:**
  - a new exploratory benchmark, with summaries committed and city records
    kept local;
  - the example city at the same setting, for parts 1 and 2.
- **What it is not:** a test. Direct voting's fidelity is 100% by
  construction. The run shows the trade-off's shape before turnout.

**R2. The fallback study** [exploratory; one hypothesis, declared with Ben
before it runs].
- **Declared 2026-11-20** in
  [`demo-5-liquid-democracy.md`](demo-5-liquid-democracy.md), item 4, after
  Ben approved the candidate hypothesis below. Settled there:
  - the default applies to (a) every topic a resident has no delegate for,
    and (b) every vote still uncast at close;
  - delegations and the calibrated acceptance level stay the frozen
    liquid's;
  - the backup delegate moves out of R2 to a later declaration, because the
    hypothesis does not involve it.

  The runner is `eval/delegation_fallback.py`. The notes below are the
  draft as it stood before the declaration.
- **Run and published 2026-11-20** (`eval/benchmarks/delegation_fallback_v1/`,
  from commit `c5a2971`). **Supported:** liquid with the default leads the
  representative by 5.7, 8.8 and 11.0 points at 0.1, 0.2 and 0.3, with every
  city under the cap. At 0.1 it adds 16.3 points of fidelity, cuts overhead
  from 23.6% to 1.8% and lifts empty-record residents from 0.1% to 60.3%;
  part of the gain is ballots where there were none, so contrary ballots
  rise from 23.3% to 32.9%. At 0.9 it changes almost nothing. For the story:
  part 3's fixes for the empty record and the uncast vote now have evidence,
  and the high edge still belongs to the ceiling.
- It replaces the earlier draft, whose arms were keep, a representative
  default and an agent at an assumed accuracy. The agent leaves, because
  there is no measured accuracy to give it.
- **It serves** part 3's fixes: the representative as default (3a and 3b)
  and the backup delegate (3a and 3c).
- **A candidate hypothesis, to settle:** under the frozen test's own rules,
  liquid with the representative as default meets the overhead condition at
  every low level (0.1 to 0.3) where it leads.
  - It reuses the declared rules, so it adds no new threshold.
  - It partly favours itself: the default moves empty-record residents' kept
    questions to the representative, so overhead falls by about their share.
    The open part is light records and uncast votes.
- **Reported, not tested:**
  - the three shares (match, contrary, no ballot) under each fix, at every
    level;
  - the backup delegate's effect on overhead and fidelity;
  - the fidelity of residents with empty records.
- **Out of scope:** the per-voter ceiling (the handover curve covers it),
  and the agent.
- **Code:** the fallback rules are written once, in the app's package
  (`delegation/graph.py` and its neighbours), off by default, so the frozen
  results reproduce unchanged; a test checks this. The study and the app
  (slice H) both use them.
- **Rules to settle first:**
  - when the default applies: to a vote still uncast at close, to a
    resident with no record, or both;
  - whether the backup delegate comes before the representative;
  - whether the backup delegate covers loops at all.

## Decisions

### Stance: report, then explain, then explore

*Revised 2026-11-20 (see "The story"):* the story's order is the idea, the
basic mechanism, the breaks with their fixes, the limits with our answers,
and then the app. The verdict is held back from the opening (Ben) and quoted
word for word in part 4's turnout section. The full study keeps the order
below.

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

Proposed 2026-11-20: a second tag, *from the literature* or *new here*, on
mechanisms and proposals (see "Labels: known theory and what is new").

### Form: a long page that tells the study's story (revised 2026-11-19)

The walkthrough tells the study top to bottom: report, then explain, then
explore. It is **not modelled on the apportionment essay**; it shares only
being a long page that unfolds as the reader scrolls. Ben decided this after
slice B was first built in the essay's style, to break from that pattern
early.

- **Content first.** The page's own design and its animation are worked out
  once every section's content exists (after slice E).
- **Until then the page is plain and static.** Sections of text with their
  figures in reading order: no pinned scroll steps, no decorative motion.
- **What will move, once designed** (unchanged from the first plan): how
  delegates are chosen from the record; how a ballot's questions are routed;
  how votes travel on and loops send them back; the city changing with the
  arrangement or the turnout; the result curves drawing as the dial moves.
  However it is done, it stays reversible, has a reduced-motion path, and
  never locks scrolling.

*Revised 2026-11-20 (draft):* the content now spans two pages, the story at
`/liquid` and the full study at `/liquid/study` (see "The story").
- **The core comes first, styling last.** The mechanism animations and
  diagrams are core content, because they explain how the system works. They
  are built in slice G, in the current plain look.
- **Styling waits.** Colour, type and any motion beyond the mechanisms come
  after slices F to H. Ben decided there are no style mock-ups before then.
- **How the animations play** (Ben): once each, when scrolled into view,
  with a replay button. See "Animations and diagrams".

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

*Revised 2026-11-20 (draft):*
- **The routes:** the story takes `/liquid`, and the full study
  `/liquid/study`. The app's screens keep their routes.
- **The app appears twice:**
  - first as its elements, in part 2's mechanism diagrams;
  - then in full as part 5, after the breaks and limits, with the proposals
    built in.
- **The hub's anchor stays `#app`,** now in part 5.

### Reader interaction: the turnout dial

One control runs through the page: the reader sets mean citizen turnout.
- **It snaps to the recorded levels,** 0.1 to 0.9, with 0.45 marked as Swiss
  turnout.
- **Every turnout-dependent figure and animation follows it.**
- **Nothing is interpolated** except where the study's own reading does (the
  crossing near 0.19).

*Revised 2026-11-20:*
- **On the story page** the dial arrives in part 3, with "now let people
  miss votes".
- **Parts 1 and 2 read as if everyone votes,** from the R1 reference run.
  Their figures show that setting's note instead of a dial. Slice F's
  `fixed` note held them at Swiss turnout; that stays only until R1 exists.
- **The dial keeps the frozen levels.** Everyone-votes is not added to it,
  so the dial never mixes exploratory and frozen levels.
- **The study page** keeps the dial throughout.

### Visual motif: one city of 500 dots

Each resident is a dot in one of five districts. For the chosen arrangement
and turnout, a dot shows two things: whose ballot counted for that resident,
and whether it matched them, contradicted them, or was missing. This makes
the three shares behind fidelity visible one person at a time.

The city is a real primary city (position 1), precomputed at build time from
the frozen code (see "Data").

*2026-11-20:* on the story page the same city carries through wherever it
fits (Ben), from part 1's opening animation to the app's doorstep. It gains
an everyone-votes setting from R1.

### Static-first

Except for the app section, data comes from build-time artifacts, never a
live Python call. The design doc's earlier "small live re-run" becomes the
precomputed city.

### Look (revised 2026-11-19)

- **Not the essays' editorial look:** no serif body, warm surfaces or pinned
  figures. Until the design pass the page uses the site's neutral surfaces
  and type (`.story.liquid-story` in `app/globals.css` points the story
  tokens at them).
- **What is about data, not style, stays:**
  - the validated chart palette (`lib/story/palette.ts`);
  - a data table with every figure, and chart text in ink tokens, never a
    series colour;
  - the benchmark's encodings, so the page and
    `eval/benchmarks/delegation_frontier_v1/README.md` read the same way:
    liquid in the first series colour, comparisons in the second, failing
    gate levels in the critical colour, each sweep's baseline as a dark line
    and its settings as an ordinal ramp.
- **The styling pass comes after the core** (slices F to H; decided
  2026-11-20). Until then both pages keep this neutral look.

## The walkthrough (becomes the full study, `/liquid/study`)

These are the sections built in slices B to E. Under the 2026-11-20 draft
they move, as built, to `/liquid/study`. "The story" above draws its
highlights from them. §16, the app, moves to the story's part 5.

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

One mechanism per step, on the illustrative city (animated once the page
is designed):

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

**Copy numbers come from generated data**, never typed into the page. A
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
| ~~F~~ | ~~Build step 8 in the app (§16), then weaving it into the story~~ (replaced 2026-11-20 by F to H below) | |

Slices after the 2026-11-20 draft (see "The story"):

| Slice | Contents | `/liquid` after merge |
|---|---|---|
| F (built) | The split, from the first draft. The current page moves, as built, to `/liquid/study`. `/liquid` is rebuilt as five parts, plain and static, from existing figures with new copy, linked both ways. The app's hub moves to the end of part 5. | the story (first draft), with the full study beside it |
| R1 | The everyone-votes reference run (see "Research the outline needs") on the 200 primary cities, and the example city at the same setting. Its summaries join `public/data/liquid-story/`, labelled exploratory. No UI. | unchanged |
| F2 (built) | The revised outline. `/liquid` is rebuilt in the new five parts, plain and static, from existing figures, R1's numbers and new copy. The verdict moves to part 4, and each break sits beside its fix. The study page is unchanged. | the revised story |
| G | The animations and diagrams in "Animations and diagrams", once Ben has described them, drawn with the app's elements and driven by `city.json` and R1. | + the mechanisms in motion |
| R2 | The fallback study: declared with Ben, then run. The fallback rules go into the app's package, off by default. | part 3's fixes gain their evidence |
| H | The app: build step 8, re-scoped around the proposals, with the preset scenarios. Possibly two PRs. | + the proposed system to try |
| — | The styling pass: colour, type and any motion beyond the mechanisms, after F to H | the designed page |

*Revised 2026-11-20.* The order:
- R1 comes before F2, because parts 1 and 2 need its numbers.
- G follows F2, so the animations land in the final structure.
- R2 can run beside F2 and G once its hypothesis is declared.
- H needs R2's rules settled; its results can follow, labelled untested
  until then.

### Slice H: the app's changes

**Kept from build step 8:**
- the scenario regenerated with delegation chosen from vote history, so the
  app and the study describe the same world;
- delegate recommendations ranked by vote history, with their interval;
- the representation scorecard: the account's fidelity and overhead under
  its district representative, under a personal proxy and under its own
  delegations, on the closed questions.

**New:**
- **The proposals in the app's resolution path:**
  - the representative as default delegate;
  - a backup delegate, for a delegate who does not vote and possibly for
    loops;
  - a per-voter ceiling.

  Their exact rules are settled with Ben before the slice starts (see
  "Still open"). They go into the app's code (`delegation/election.py`,
  `routing.py`, `graph.py`), never into the frozen comparison code
  (`delegation/comparison/`). R2 uses the same rules, so the app and the
  study test one implementation.
- **The preset scenarios** from part 5, each a seeded starting state.
- **The version shown on the page:** the hub, one vote and your delegates.

**Labels:** every proposal in the app carries the proposal label. The app as
a whole stays an illustration.

## Built in slice B (2026-11-19)

- **The illustrative city is primary city 1**, recomputed at every level with
  `compare` (`scripts/build_liquid_example_city.py`). Its totals and
  acceptance levels equal the recorded city's at every level.
- **The motif shows one question.** A dot is one ballot, so the city shows
  one featured question at every level: the evaluation question whose match,
  contrary and no-ballot shares, under direct voting, the representative and
  liquid at Swiss turnout, lie closest to the city's own (immigration,
  `e0096`). Filled is the resident's own ballot, a ring someone else's; blue
  matches, red is against, grey is no ballot.
- **The mechanism uses real residents chosen by fixed rules,** written in the
  script. At Swiss turnout 445 of 500 residents hand over every topic, so the
  showcase (one who keeps a topic, to show both routes) is atypical and the
  page says so. A resident with one ballot in the whole record falls short
  of the acceptance level (0.580 against 0.586) and keeps everything.
- **Chains end in loops.** Because nearly everyone delegates, 96% of
  handed-over votes in this city end with someone on a loop. The page shows
  the longest chain (nine people, ending on a mutual pair) and that share.
- **§2 uses a typical resident:** one who hands over every topic, with
  turnout closest to the city's mean.
- **Built plain** (see "Form" and "Look"): the first build used the
  apportionment essay's pinned scroll steps and editorial styling, and was
  reworked the same day. The cold open shows the city under whichever
  arrangement the reader picks; "How it works" is seven steps, each with its
  own static figure.
- **The app's hub loads in the browser** through a read-only server action,
  so `/liquid` stays static; its screens keep a dynamic layout in the
  `app/liquid/(app)/` route group.

## Built in slice C (2026-11-19)

Plain and static, like slice B (see "Form" and "Look").
- **Data.** `scripts/build_liquid_story.py` adds `results.json`: per level,
  liquid minus the representative with its simultaneous band, the cap-only
  curve and band, liquid's and the proxy's share of cities under the cap (the
  proxy's from `primary_report.json.gz`), the per-level readings, the
  declared ladder and the attendance frontier. `measures.json` gains the
  record, loop, kept-fidelity and attendance measures §6 and §8 quote.
- **The city records why each resident decides.** `liquid_reason` per level:
  delegated, on a loop, an empty record, or no candidate good enough. It is
  §6's city: at 0.1, 107 residents decide only because they have no record;
  at 0.9, 44 because their delegation loops back.
- **Figures.** §5 mirrors the benchmark's Figure 1 (the cap-only curve drawn
  under the all-city one, with bars only where few cities qualify) and §8
  its Figure 2. §6 is four small panels and the city. §7's ladder follows the
  dial; a test checks its steps add up to the lead at every level.
- **One chart for every "across the dial" figure**
  (`components/liquid/story/dial-chart.tsx`), marking the dial's own level.

## Built in slice D (2026-11-19)

Plain and static, like slices B and C.
- **Data.** `results.json` gains the sweeps (every point's curve, cap shares
  and threshold, grouped in the benchmark's own panels, whose layout is
  imported from `eval/plot_delegation_frontier.py`) and the router's measured
  errors (`eval/benchmarks/delegation_router_v1/summary.json`, a new pinned
  input). `measures.json` gains concentration, poor representation, lifecycle
  overhead and outcome agreement. The sweep points keep `levels.csv` order:
  collecting them through a set made the build depend on the hash seed.
- **The city records each question's winner** per arrangement and level, so
  §11 shows its Ostrogorski-style cases: at Swiss turnout the council of five
  loses the issue majority on 24 of 160 questions (liquid 25, direct 10; one
  city, and across all 200 liquid does better than the representative).
- **The router is a static chart for now** (false delegations and false keeps
  by threshold, the operating threshold marked); the animation comes with the
  design.
- **Dark mode's own blue steps** for the page (`.dark .story.liquid-story`):
  the shared ramp's darkest steps vanished on a dark page. The sweeps use the
  middle steps so no setting reads as the baseline's ink line.

## Built in slice E (2026-11-20)

Plain and static, like slices B to D. The walkthrough's content is complete.
- **Data.** `exploratory.json` (labelled exploratory) holds liquid's handover
  curve and the wrong-ballot scores from
  `eval/benchmarks/delegation_handover_v1/`, whose summaries are now pinned
  inputs, and the personal agent's bars, labelled proposal arithmetic.
- **The agent's bars use one formula for both comparisons:** how often a
  ballot matches its voter when one is cast. A representative's: fidelity
  divided by the share of its ballots cast (63.2% at Swiss turnout). A chosen
  delegate's: fidelity on delegated pairs divided by the share of those cast
  (74.7%; the plan's "about 74%" was approximate).
- **"Beats the calibrated point on both measures"** requires a fidelity gain
  beyond the curve's intervals (0.4 points), which gives the README's 0.3 to
  0.5; a strict comparison would also have counted 0.2 and 0.6.
- **The wrong-ballot table is static and always visible,** as tentatively
  decided; a slider stays possible.
- **Methods and sources** carry no claim label; the heading's label is
  optional.

## Built in slice G5 (2026-11-20)

Part 5's assembled design (`components/liquid/story/design-scene.tsx`),
replacing its placeholder and the list of fixes.
- **One vote through the whole system:** a rail of seven stages (a question
  arrives, the router files it, your ceiling, your delegate and theirs, if
  no ballot comes back, if you have no record yet, the tally); an orb moves
  down it and each stage lights up as the vote reaches it.
- **Each stage** carries its claim label, one line of evidence from the
  generated data (the router's measured errors, the handover curve, the loop
  rule, R2's result, the agent's bar) and a link to the break it answers.
- **Item 16** ("How we know" as a timeline) had no description and is not
  built; the verdict box in part 4 keeps its "How we know" list.
- **Slice G is complete.** `Pending` is gone from the page.

## Built in slice G4 (2026-11-20)

Part 4's animations (`components/liquid/story/limits-scene.tsx`, and
`Reveal` in the shared stage). Branched on G3, whose PR was still open.
- **Item 21, routing:** a ballot question meets a voter's written categories;
  the decision model's recorded scores fill in, the 0.7 threshold drops
  through, and the result is read out. Three tabs, from the router
  benchmark's 544 cases by a fixed rule: sent right ("Senior property tax
  freeze", 0.98), kept by mistake ("Spending cap tied to tax revenue": the
  right category at 0.57), sent wrong ("Property tax deferral for older
  homeowners": housing at 0.75). The story build re-routes all 544 cases
  from the recorded judgments and refuses to build unless the published
  error counts come out.
- **Item 20, the cold start:** a timeline fills 400 questions at 100%, then
  160 at 9.8%, with the running average landing on 74.2%.
- **Item 27, the personal agent:** an interview, a model, ballots filled with
  question marks, then the bars it must beat on a scale with its accuracy
  hatched as unknown; the bars follow the dial.
- **Item 26, the ceiling:** a point walks the handover curve at the dial's
  turnout and marks its peak (all eight topics up to 0.7, two at 0.8, none
  at 0.9); it replaces the handover figure in the story.
- **Item 22, engagement borrowed:** the city sorted by how often residents
  vote; each handed-over vote flies to whoever decides it, and the deciders
  are ringed, growing with what they hold. The caption gives the two
  turnout averages (76.9% against 99.6% at 0.8).
- **Items 6, 7, 12, 14, 15 and 23:** the candidates, short-record,
  calibration, result, ladder and outcomes figures draw in from the left
  when scrolled into view (`Reveal` clips every SVG inside to the share
  shown), with replay. The ladder figure joins the story.
- **The shared player** now clamps elapsed time at zero: a frame's timestamp
  can precede the start, which crashed the ceiling scene's indexing.

## Built in slice G3 (2026-11-20)

Part 3's breaks on the shared stage (`components/liquid/story/breaks-scene.tsx`),
with R2's evidence. Ben added the backup delegate as a fix (resolving the open
question).
- **Swipe-through fixes.** Arrows and tabs step through the problem, you
  catch it, a backup delegate, the representative and a personal agent; each
  replays the scene and carries its label and evidence.
- **Item 11, a delegate who does not vote:** resident 33's vote passes through
  203 to 137, who does not vote; it falls and cracks. Each fix catches it
  and shows what that catcher would really have cast on that question: 33
  would not have voted, their backup (441) did not either, and their
  representative (3) would have voted against them. The notes give the
  averages: R2 cuts votes with no ballot at Swiss turnout from 6.6% to 0.3%;
  overhead's health bar shows the rise if everyone caught their own (9.8%
  to 11.1%, from frozen shares).
- **Item 17, nobody to delegate to:** the city at the dial's turnout;
  residents with no record grey out, then take each fix's ballots: their own
  (almost none), none from a backup (it needs a record too), the
  representative's (at 0.1: 71 match, 36 against, from R2's rule), or
  unknown for the agent.
- **Items 10 and 18, loops:** the recorded chain runs into its two-person
  loop, circles it twice and stops under the loop rule; a meter below shows
  the loop share at every turnout and with everyone voting, following the
  dial.
- **Copy:** part 3's fix notes, part 4's edges and part 5's list now cite R2
  (supported at 0.1 to 0.3); the backup delegate and the agent stay
  untested.
- **Data:** `city.json` (version 5) adds the lost vote's path, the voter's
  backup and each fix's would-be ballot; `exploratory.json` gains a
  `fallback` block from `eval/benchmarks/delegation_fallback_v1`.
- **Dropped from the story** (still in the study): the kept-city figure and
  the static chain figures, which the new scenes replace.

## Built in slice G2 (2026-11-20)

Part 1's figures on the shared stage (`components/liquid/story/structures-scene.tsx`),
drawn from the illustrative city with everyone voting.
- **Item 1, a vote from question to winner** (canvas with an SVG overlay):
  a ballot reaches all 500 residents in a sweep, each ballot flies to the
  option it chooses in the diverging palette's two poles, the tallies count
  up and the winner is ringed (340 yes, 160 no on the featured question).
- **Items 2 and 3 as one figure per beat.** Under direct voting, the
  representative, the proxy and liquid, resident 227's eight topic orbs go
  to whoever decides them and stay gathered there:
  - direct: beside the resident;
  - the representative: all eight round one node (bundling), with the
    district's other residents' votes drawn in beside them (dilution);
  - the proxy: all eight round the one person 227 chose (481);
  - liquid: each beside its own delegate, a delegate holding two topics as
    one segmented node.

  Under each, fidelity and overhead bars (overhead drawn like a health bar)
  from R1's averages over 200 cities, labelled exploratory.
- **Part 1 no longer shows the three-ways figure;** the structures carry the
  arrangements and the plane the trade-off. The three-ways figure stays in
  part 3 with the dial.
- **Data:** `city.json` (version 4) adds, with everyone voting, every
  resident's vote on the featured question and resident 227's representative
  (209), proxy (481) and the proxy's decider (176). Tests check the votes'
  winner and that the representative lives in 227's district.
- **Development loader:** `loadLiquidStory` re-reads the artifacts on every
  request in development, so a rebuilt `city.json` shows without restarting
  the server; production still caches.

## Built in slice G1 (2026-11-20)

The shared stage and part 2's scene, replacing its three placeholders.
- **The stage** (`components/liquid/story/stage.tsx`): `useScenePlayer` runs
  a scene once when it first scrolls into view and holds its end state; the
  replay button runs it again; reduced motion shows the end state and never
  animates. The vocabulary: `Orb` (a glowing vote), `Ballot` (scribbled
  lines with a yes and a no box), `Person`, `Edge`. Each topic takes its
  series slot's colour; the eight passed the palette validator in both
  themes, with a contrast warning in light mode that every scene meets with
  text labels and a data table.
- **Part 2's scene** (`components/liquid/story/delegation-scene.tsx`), drawn
  from the illustrative city with everyone voting:
  - **A ballot arrives:** the ballot shrinks into an orb in its topic's
    colour, which goes to resident 227 and then along the edge to their
    delegate; sixteen more orbs follow, sorted by colour. A delegate trusted
    with two topics is one node with a segment per topic, and its edges sit
    side by side. A legend names each topic's delegate.
  - **Votes travel on:** the camera starts close on the first hand-over and
    pulls back as the orb passes 374, 403 and 53 before 203 decides it.
  - **Who ends up deciding:** a canvas radial tree of the featured
    question. Deciders sit on the inner ring, everyone else outward by
    their hand-overs; uncoloured orbs flow inward and the deciders grow with
    the votes they hold, the largest (61 of 500) named at the centre.
- **Data:** `city.json` (version 3) gains, for the everyone-votes setting,
  the typical resident's delegate and decider per topic, their longest
  chain, and everyone's delegate in the featured question's topic. The
  builder checks the delegations give the comparison's resolvers; a test
  follows every delegation to its decider and recomputes the block.
- **The loop back-edge is not drawn** in part 2: loops are part 3's.

## Built in slice F2 (2026-11-20)

`/liquid` rebuilt to the revised outline, plain and static. The study page
is unchanged.
- **Parts 1 and 2 read as if everyone votes.** A nested `TurnoutProvider`
  with `everyone` and a `fixed` note holds them; its dials show the note.
  Figures read their data through `useSetting()`
  (`components/liquid/story/setting.tsx`), which returns R1's measures and
  the city's everyone-votes setting there, and the dial's level elsewhere.
  - The three-ways figure, the plane and the one-resident figure support
    it. With everyone voting the three-ways figure shows direct voting,
    the representative, the proxy and liquid, and the plane notes that
    direct voting and full turnout coincide.
  - The ballot tooltip takes a city setting instead of a level key.
- **The opening** asks the question and says part 4 gives the answer. The
  short-answer box is gone.
- **Part 1** builds the case: direct voting, the representative (dilution and
  bundling), the proxy, liquid. Then the three-ways figure, the two measures
  with the one-resident figure and the plane, and the asterisk on what parts
  1 and 2 assume.
- **Part 2** is the basic version in five beats. Its three animations are
  dashed "Animation in progress" boxes saying what each will show, for slice
  G. The Swiss-turnout mechanism figures were not reused there, because
  turnout is not yet on the page.
- **Part 3** opens with the dial, the three-ways figure and the resident from
  part 1 at Swiss turnout. Each break (a delegate who does not vote, nobody
  to delegate to, loops) is followed by its fix in a `Fix` note with its
  label and its evidence. The lost-vote and loop chain figures, the kept
  city and the edges figure moved here.
- **Part 4** has strict categories (the router), the initial history (the
  candidates, short-record and calibration figures moved here, then the
  cold start and the personal agent), and turnout: the result, the verdict
  in a box with "How we know", the two edges, the ladder line,
  concentration as a turnout effect with capture named, the per-voter
  ceiling with the handover curve, and what delegation cannot change.
- **Part 5** lists the assembled design, each piece with its label, then a
  placeholder for the diagram and the app.
- **Dropped from the story** (still in the study): the costs figure, because
  concentration is no longer framed as a cost.

## Built in slice F (2026-11-20)

The split, plain and static like slices B to E. Ben started it from the
draft outline without changes.
- **`/liquid/study`** is the walkthrough as built (`app/liquid/study/page.tsx`,
  moved with history).
  - It is retitled "The full study", with a line pointing back to the story.
  - Its methods link the three benchmarks on GitHub (the repository is
    public).
  - The app section is replaced by links to the story and to `/liquid#app`.
  - Its section ids are unchanged, because the story links to them.
- **`/liquid`** is the story (`app/liquid/page.tsx`), built from the same
  components with new copy:
  - the opening, with the short answer, the verdict word for word, the five
    parts and two shortcuts;
  - parts 1 to 5, each ending with `StudyLinks` to the study's sections;
  - the app at the end of part 5 (`#app`), saying the proposals are not in
    it yet;
  - the close, with a short "What is left out" and links to the study, the
    benchmark and the design doc.
- **Parts 1 and 2 at Swiss turnout.** A nested `TurnoutProvider` with a
  `fixed` note holds them at 0.45, and every dial inside shows the note
  instead. Moving a later dial leaves them unchanged.
- **Each bottleneck names its proposal.** An "In part 5" note says which
  proposal targets it, or that none does.
- **Part 3's "How we know" note:**
  - the freeze date and commit;
  - the cities and the sweeps;
  - the verdict, quoted with the condition that was not met.
- **Left for later:**
  - part 1's structure diagram and part 2's "who ends up deciding" beat
    (slice G);
  - the known-or-new tags, until the literature check is done. Meanwhile
    the copy itself calls the backup delegate an existing idea (ranked
    delegations).
- **Study only:**
  - the plane;
  - the ladder in full;
  - the attendance frontier (part 4 keeps one line on attendance);
  - the sweeps panels;
  - the wrong-ballot table;
  - the council's Ostrogorski-style cases;
  - the agent's "three shares" note.

## Decisions settled 2026-11-19

1. **Route:** the walkthrough takes `/liquid`. The account app sits at the
   bottom of the page for now and is woven in later where it fits.
2. **Form:** a scrolling essay, with animations throughout, for the mechanism
   (routing, choosing from the record, votes travelling on and looping) and
   for some results.
3. **Handover curve:** every recorded level.
4. **Wrong-ballot weighting:** a static table at w = 0 and w = 1, tentatively.

## Still open

- **Ben's descriptions** of the animations and diagrams still without one
  (the table in "Animations and diagrams").
- **R2's hypothesis and rules,** before it runs:
  - the hypothesis (a candidate is drafted);
  - when the representative default applies: to a vote still uncast at
    close, to a resident with no record, or both;
  - whether the backup delegate comes before the representative, and whether
    it covers loops at all.
- **The per-voter ceiling's rule.** One candidate: hand over a topic only
  when the delegate's expected match beats the voter's own chance of voting.
  That is the turn the handover curve shows.
- **A turnout answer for delegates** (suggested, not yet agreed): delegates
  who hold votes commit to attending like office holders. The frozen
  attendance frontier (Figure 2) shows what that would be worth, so part 4c
  could offer it as an answer.
- **The known-or-new tag:** whether to adopt it, and how the literature check
  behind each *new here* is done.
- **The personal agent in the app:** text only, as drafted, or a labelled
  stand-in at an accuracy the reader sets.
- **The wrong-ballot table:** whether it becomes a slider. It is on the study
  page only.

Settled 2026-11-20:
- ~~Ben's markup of "The story"~~: the revised outline.
- ~~The opening~~: the verdict is held back until part 4.
- ~~The fallback-rules study: before slice H, or ship labelled untested~~:
  it becomes R2, declared with Ben; H may ship before its results, labelled
  untested.
- ~~Where the app is woven into the story~~: as its elements in part 2, then
  in full in part 5.
- ~~Concentration's fix~~: none needed; it is the mechanism working.
