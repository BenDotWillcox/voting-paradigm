# Demo 5: the liquid-democracy walkthrough

Status: planned 2026-11-19, after the frozen benchmark was published (PR #110).
Decisions made with Ben the same day are recorded below. Slice A (the
exploratory handover benchmark) is published (PR #112). Slice B (the data
pipeline, the illustrative city, §0–4 and the app at the page's foot) is
published (PR #113), slice C (§5–8) too (PR #115) and slice D (§9–11) (PR
#116). Slice E (§12–15) is published (PR #117), so the walkthrough's
content is complete. "Built in slice B" to "E" below record the choices
made while building them.

**2026-11-20: the story outline (draft).**
- `/liquid` becomes a five-part story built on that content: the idea, how
  it works, the result, where it breaks, and what we'd build.
- The sections as built move to `/liquid/study`, the full study.
- The app comes last, with the proposals built in.
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

## The story: `/liquid` (draft outline, 2026-11-20)

A draft for Ben to mark up. It sets the reading order of `/liquid`. The
sections built in slices B to E ("The walkthrough" below) move, as they are,
to `/liquid/study`, the full study. The story takes its highlights from
them.

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

### Two pages

- **`/liquid`, the story.** It has five parts and shows highlights only. It
  uses well under half of the study's figures, plus the new mechanism
  animations and the app.
- **`/liquid/study`, the full study.** This is the current walkthrough,
  §0–15 as built, with every figure, interval, data table and the methods.
  - It keeps its section anchors, so the story can link to them.
  - It reuses the same components; nothing is rebuilt.
  - It links to the published benchmarks on GitHub for anyone who wants the
    CSVs.
  - `/liquid/city` is the app's City Results, so the study takes
    `/liquid/study`.
- **Links between them.** Each part of the story ends with links to the
  matching sections of the study ("The full analysis"). The study opens with
  a line pointing back to the story.
- **The rigour stays visible on the story page, briefly.** A short "How we
  know" note in part 3 says that the test was declared before the run, that
  it ran on 200 synthetic cities from frozen commit `a50ebcc`, and that the
  verdict is quoted word for word. Failing a pre-declared test and saying so
  plainly is part of what the page shows.
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
- **The answer, in one line, unsoftened:**
  - clearly yes in the middle of the turnout range;
  - but the pre-declared test is not met, because at both ends liquid
    delegation cannot keep its overhead low.

  Part 3 gives the verdict in full.
- **Shortcuts** to the full study and to the app, for readers who want to
  jump.

### Part 1. The idea: three ways to be represented

**Message:** voting yourself is never wrong but usually absent. A
representative is almost always there, but against you a third of the time.
Liquid delegation hands each topic to someone you chose, and you keep any
question you want.

- **Three arrangements, one sentence each:** direct voting, a district
  representative, and liquid delegation.
- **Why representation costs fidelity:**
  - dilution: you share the representative with your whole district;
  - bundling: one person stands for you on every issue.

  Liquid delegation removes both: you choose the person (no dilution), topic
  by topic (no bundling). This is the design doc's "The claim".
- **The trade-off, named with the two measures:**
  - fidelity: how often the ballot counted for you matches yours;
  - overhead: how many questions you decide yourself.
- **The city, in one paragraph:**
  - 500 made-up residents in five districts, with beliefs fitted to CES
    survey data;
  - eight topics, with a public record of past votes;
  - one of 200 such cities.

  The details stay in study §1.
- **Fixed at Swiss turnout.** Parts 1 and 2 are set at 0.45. The dial
  arrives in part 3, where turnout starts to change the answer.

Figures:
- **New: a structure diagram** [illustration]. You and your own ballot; you,
  your district and its representative; you and a delegate for each topic.
- **The three ways** (§0's strips and the city of dots), at 0.45:

  | | Matches | Contrary | No ballot |
  |---|---|---|---|
  | Direct | 45.0% | 0% | 55.0% |
  | Representative | 60.6% | 35.3% | 4.0% |
  | Liquid | 70.9% | 22.6% | 6.6% |

Study only: the plane of five arrangements (§4), and full turnout and the
personal proxy as arrangements. The proxy comes back briefly, in the ladder
line of part 3 and in part 4's low edge.

### Part 2. How it works [illustration]

**Message:** liquid delegation is a few simple rules: hand over a topic,
votes travel on, and loops come back. Choosing delegates well is the hard
part.

One mechanism per beat. Each beat gets an animation or diagram, driven by
the frozen city's recorded data (`city.json`'s `mechanism` block):
1. **Choosing a delegate from the record.** For the showcase resident:
   - each candidate's past votes line up against the resident's, and the
     agreements are counted;
   - the lower bound ranks the candidates, so a short shared record counts
     for less;
   - the resident hands the topic over only if the best bound clears the
     acceptance level.

   Built from `CandidatesFigure`.
2. **A ballot arrives and is routed.** Each question is filed under its
   topic. It goes to that topic's delegate, or stays with the voter. Built
   from `RoutingFigure`, with the typical resident.
3. **Votes travel on.** A delegate's own delegations apply to the votes
   they hold, so a vote can pass through several people. Built from
   `ChainFigure`, with the recorded chain.
4. **Loops come back.** Everyone on a loop decides for themselves. The
   recorded loop cycle.
5. **A delegate who does not vote** leaves every vote they hold empty. One
   line here; part 4 says how rarely it happens.
6. **The acceptance level.** Each city's level is the highest at which
   overhead on the past questions stays at or under 10%. This is the cap
   that part 3's verdict tests. Built from `CalibrationFigure`.
7. **Who ends up deciding.** The city at 0.45, showing whose ballot counts
   for each resident.

**The app's first appearance.** The beats are drawn with the app's own
elements:
- a delegation card for beat 1;
- the routing receipt for beat 2;
- the vote page's chain for beats 3 and 4.

The reader meets the app's vocabulary before using it, and the app itself
waits for part 5. This is a structure decision; the look comes later.

The study routes exactly. The app files free-text questions with a decision
model, mentioned here and measured in part 4.

### Part 3. Does it work?

**Message:** in the middle of the turnout range, liquid delegation
represents people clearly better than an elected representative, while
each voter decides only about one question in ten. At the ends it is not
established.

- **The dial arrives.** Everything so far was at Swiss turnout, and turnout
  is what changes the answer. The reader sets it, from 0.1 to 0.9.
- **Figure 1, following the dial:**
  - liquid overtakes the representative near 0.19, with a 95% range of
    (0.1, 0.3];
  - it leads by +10.2 points at 0.45;
  - it leads by at least 2 points at every level from 0.3 to 0.8.
- **The verdict, word for word:** *overhead condition not met where liquid
  is ahead*.
  - The test needs 95% of cities under the 10% cap at every level where
    liquid leads.
  - Only 7.5% are under it at 0.2, and 4% at 0.9.
- **Where the lead comes from, in one line.** Most of it arrives with
  having one chosen proxy at all (+7.3 of the ladder at 0.45). Topic
  delegation, the signature feature, adds about 2 points.
- **The "How we know" note** (see "Two pages").

Optional: the three ways again, now following the dial.

Study only: the cap-only curve, the confidence-range sidenote, the full
ladder, attendance (Figure 2) and the sweeps.

### Part 4. Where it breaks

**Message:** the bottlenecks are not in the rules for passing votes on.
They lie in who has a record to choose by, in loops, in a few people
holding many votes, and in the time it takes to build a record.

Each bottleneck says what goes wrong, gives its number and says why it
matters for a real deployment. Each names the part 5 proposal that targets
it, or says that none does.

**4a. The two edges** [frozen]. This is the main beat, with figures.
- **Low turnout: the empty record.**
  - A resident who never votes has nothing to choose a delegate by. They
    keep their vote and rarely use it.
  - At 0.1, 22.8% of residents have an empty record, and liquid's overhead
    is 23.6%.
  - Under liquid their fidelity is 0.001 to 0.003, against about 0.60
    under the representative.
  - The same thing happens under the personal proxy, so the cause is
    choosing by record, not topics.
  - Targeted by: the representative as default, and the personal agent.
- **High turnout: loops and over-delegation.**
  - At 0.9, 11.5% of voter-question pairs sit on a loop, and that is
    liquid's whole overhead.
  - This is specific to topic delegation: the single proxy's loop share is
    7.0%.
  - The city-wide cap pushes people who would vote into delegating. Direct
    voting passes liquid between 0.7 and 0.8.
  - Targeted by: the backup delegate, and the per-voter ceiling.
- **The beat's point:** one overhead number cannot tell a burden people
  carry from one they drop.
- **Figures:** `EdgesFigure` (empty- and light-record fidelity, and the loop
  share) and `KeepCityFigure`.

**4b. Costs the headline hides** [frozen]. Compact, one small figure or line
each.
- **Concentration.**
  - A district representative decides 20% of every question.
  - Under liquid, the largest single delegate decides 28.5% at 0.45, and
    43.7% on a city's worst question.
  - It is 43.5% at 0.1.
  - Targeted by: none directly. The personal agent carries the same risk in
    a new form.
- **The cold start.**
  - The 10% is the steady state.
  - Building the record means everyone decides every question first:
    lifecycle overhead is 74% at 0.45.
  - Targeted by: the personal agent, whose record would come from one
    interview instead of years of votes.
- **Routing.**
  - A real system has to file each question under a category.
  - The decision model's measured error, from `RouterFigure`: a false
    delegation costs fidelity, and a false keep costs overhead.
  - Targeted by: the app's threshold, which trades coverage for caution.
- **Not a bottleneck: attendance.** Delegates who hold votes cast them 97%
  of the time at 0.45. One line.

**4c. What delegation cannot change** [frozen, with one interpretation].
- **It borrows engagement; it does not create it.**
  - With an even electorate, the lead at 0.45 falls to +4.4 points and the
    crossing moves to about 0.35.
  - With a short record (10 past questions per topic), the cap fails at
    every level.
  - No proposal targets this, and the page says so.
- **Better for individuals, worse for outcomes.**
  - Agreement with full-turnout outcomes at 0.45: direct voting 97.4%,
    liquid 85.3%, the representative 82.2%.
  - The interpretation, labelled as untested: random abstention is a fair
    sample, while delegation copies one person's deviations onto everyone
    who follows them.
  - The caveat: in this model turnout does not depend on opinion.

Study only: the lower tail, the other sweep families, lifecycle overhead
across the dial, the wrong-ballot table and outcomes for every arrangement.

### Part 5. What we'd build [proposal]

**Message:** each bottleneck points at something buildable. Here is the
design, the bar each piece must clear, and an app to try it in.

**The four proposals**, each set against the bottleneck it targets. All are
untested.
1. **The representative as default delegate** → the empty record. Its bar:
   no one with an empty record falls below being represented.
2. **A backup delegate for loops** → loops. The page says it is a known idea
   (ranked delegations) applied to the high edge.
3. **A per-voter ceiling instead of a city-wide cap** → over-delegation at
   the high end. Its evidence is the handover curve [exploratory], following
   the dial:
   - fidelity rises with every topic handed over up to 0.7;
   - at 0.8 it peaks after two topics, and at 0.9 it falls with every
     topic;
   - the turn comes where a delegated pair's fidelity (0.75 to 0.76) drops
     below turnout.
4. **A personal agent** (the demo 2 link) → the empty record and the cold
   start.
   - Its bars at 0.45: 63.2% to beat a representative default, and 74.7% to
     beat a chosen delegate.
   - No accuracy is claimed.
   - One model for everyone shares its errors across every ballot it casts.

**What none of them fixes:** borrowed engagement, and outcomes that drift
from full turnout.

**The follow-up study:** the declared fallback-rules study. It is linked
here only once it has results.

**The app** [illustration]. It is the part's payoff: a plausible
implementation of the proposed system. See "Slice H" for its changes.
- It is introduced as a separate city of 240 residents, with free-text
  categories and the real decision model. It is not evidence.
- **On the page:** the hub, one vote and your delegates. The full-screen app
  keeps the rest: Incoming Votes, Profile, Activity, City Results and About.
- **Preset scenarios,** each a seeded starting state that shows one
  bottleneck and its fix:
  - "you've never voted": no recommendations, so the default
    representative steps in;
  - "your chain loops back to you": the backup delegate catches it;
  - "your delegate stops voting": the fallback takes over;
  - "you'd rather keep more": the ceiling.

  Free play and reset stay.

### The close

- What the study leaves out (§14), as a short list.
- Links to the full study, the benchmarks and the design doc.

## Decisions

### Stance: report, then explain, then explore

*Revised 2026-11-20 (draft, see "The story"):* the story's order is the
idea, the mechanism, the result, the limits and then the proposals. The
verdict is still quoted word for word, in the opening's one-line answer and
in part 3. The full study keeps the order below.

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
  - then in full as part 5's payoff, after the bottlenecks, with the
    proposals built in.
- **The hub's anchor stays `#app`,** now in part 5.

### Reader interaction: the turnout dial

One control runs through the page: the reader sets mean citizen turnout.
- **It snaps to the recorded levels,** 0.1 to 0.9, with 0.45 marked as Swiss
  turnout.
- **Every turnout-dependent figure and animation follows it.**
- **Nothing is interpolated** except where the study's own reading does (the
  crossing near 0.19).

*Draft 2026-11-20:*
- **On the story page** the dial arrives in part 3. Parts 1 and 2 are fixed
  at Swiss turnout, so the reader first learns the system at one turnout,
  then sees turnout change the answer.
- **The study page** keeps the dial throughout.

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
| F (built) | The split. The current page moves, as built, to `/liquid/study`. `/liquid` is rebuilt as the five parts, plain and static, from existing figures with new copy, linked both ways. The app's hub moves to the end of part 5. | the story, with the full study beside it |
| G | The mechanism animations and diagrams: part 1's structure diagram and part 2's beats, drawn with the app's elements and driven by `city.json`. Each has a reduced-motion path and none locks scrolling. | + the mechanisms in motion |
| H | The app: build step 8, re-scoped around the proposals. Possibly two PRs. | + the proposed system to try |
| — | The styling pass: colour, type and any motion beyond the mechanisms, after F to H | the designed page |

G and H do not depend on each other.

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
  - a backup delegate for loops;
  - a per-voter ceiling.

  Their exact rules are settled with Ben before the slice starts (see
  "Still open"). They go into the app's code (`delegation/election.py`,
  `routing.py`, `graph.py`), never into the frozen comparison code
  (`delegation/comparison/`).
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

- **Ben's markup of "The story"** (the draft of 2026-11-20).
- **The opening:** state the answer and the verdict up front, as drafted, or
  let part 3 reveal them.
- **The known-or-new tag:** whether to adopt it, and how the literature check
  behind each *new here* is done.
- **The fallback-rules study:**
  - run it before slice H, so part 5 has results;
  - or ship part 5 labelled untested and add the results later.
- **The personal agent in the app:** text only, as drafted, or a labelled
  stand-in at an accuracy the reader sets.
- **The app's rules for the proposals** (before slice H):
  - when the representative default applies, for example to a vote still
    uncast at close;
  - whether the backup delegate also covers a delegate who does not vote,
    or only loops;
  - what the per-voter ceiling is. One candidate rule: hand over a topic
    only when the delegate's expected match beats the voter's own chance of
    voting. That is the turn the handover curve shows.
- **The wrong-ballot table:** whether it becomes a slider. It is now on the
  study page only.
- ~~Where the app is woven into the story~~ Drafted 2026-11-20: as its
  elements in part 2, then in full in part 5.
