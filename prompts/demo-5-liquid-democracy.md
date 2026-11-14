# Demo 5: Liquid Democracy — Design Doc

Living design document for the liquid democracy demo. Edit when decisions change.

Status: vision revised 2026-11-14 (see "The claim" and "The comparison"
below); not yet built. The machinery from the first design (2026-11-09 to
2026-11-13) stays: category routing, election processing, the loop rule, the
router evaluation in `eval/benchmarks/delegation_router_v1/`, the four
`/api/delegation` routes and the account app at `/liquid`. What changes is
what the demo is for and how it argues it: a comparison of direct voting,
elected representation and liquid democracy on a simulated population,
presented as a research walkthrough, with the account app kept as a
companion that shows what using it would look like.

## The claim

Direct democracy is the reference. A voter is more likely than anyone else
to choose the outcome they prefer, so their own sincere vote on a question is
the best representation of them there is. Its cost is overhead: nobody can be
informed on every question or has the time to answer each one thoughtfully.

Elected representation is the practical answer to that overhead, and it
costs fidelity in two separate ways:

1. **Dilution.** The representative is shared with everyone in the district,
   whose preferences differ from yours, and is elected by them.
2. **Bundling.** One person stands for you on every issue. You will not agree
   with any single candidate on everything, so you compromise on some issues
   to win others.

Liquid democracy removes both while keeping overhead low: you pick the person
yourself (no dilution), per category (no bundling), and keep any question you
want. The demo shows this on two axes, **overhead** (how many decisions you
make yourself) and **fidelity** (how often the ballot counted for you matches
the one you would have cast). Direct voting is one corner, representation a
point at low overhead, and liquid democracy a curve between them. The
question the demo answers is how close that curve gets to direct voting's
fidelity at representation's overhead, and what it depends on.

Liquid democracy is not claimed to beat direct voting, and is not modelled as
a fix for poorly informed votes: in this model a voter's own vote is correct
for them by definition.

## The comparison

### Arrangements

Each arrangement decides whose ballot counts for a voter on a question.

| Arrangement | Whose ballot counts for you | Dilution | Bundling |
|---|---|---|---|
| **Direct** | Yours, on every question | — | — |
| **District representative** | Your district's representative, elected by plurality, on every question | yes | yes |
| **Personal proxy** | One person you chose by your overall agreement, on every question | no | yes |
| **Liquid** | Per category, a person you chose by your agreement on that category; yours on everything you keep | no | no |

The personal proxy is not a real proposal. It is the step between the other
two that separates the cost of dilution from the cost of bundling: the gap
from representative to proxy is dilution, the gap from proxy to liquid is
bundling.

Abstention is the same everywhere: a voter whose counted ballot is empty
(their resolver did not vote) gets no match.

### Measures

- **Fidelity** (per voter, per question): 1 if the ballot counted for the
  voter equals their sincere choice, else 0. Averaged over voters and
  questions. Direct voting scores 1 for everyone who votes. Unweighted: every
  question counts the same, because a per-voter salience weight would be
  hard to model credibly (decided 2026-11-14).
- **Overhead** (per voter): the share of questions the voter decides
  themself. Direct is 1, representative and proxy 0, liquid in between. The
  number of delegations a voter maintains is reported beside it, so liquid's
  upkeep is not hidden.
- **Outcome agreement** (per question): whether the arrangement's winner is
  the direct-voting winner. Representatives decide a city question as a
  council majority. This is where Ostrogorski-style cases appear: a council
  elected on bundled platforms that loses the issue-by-issue majority.
- Fidelity is always measured on questions that come *after* the history the
  delegates were chosen from (see below), never on the same questions.

### The headline figure

Overhead on the horizontal axis, fidelity on the vertical: direct, the
district representative, the personal proxy, and the liquid curve traced by
letting voters hand over zero, one, two, ... of their categories (best-scoring
first). Every other figure is a sensitivity or a breakdown of this one.

### Choosing delegates from vote history

Nobody knows another person's preferences. What they can see, because votes
are public in this world, is how that person voted. A voter chooses a
delegate for a category by comparing that person's past votes on the
category's questions with their own (proposed 2026-11-14):

1. **History.** The questions in the category from earlier ballot papers.
   Which questions belong to a category comes from the router, the same rule
   that routes new questions.
2. **Agreement.** For each candidate, over the questions on which the voter
   voted themself: count a match when the candidate voted the same way
   themself. A question the candidate did not vote on, or delegated onward,
   counts as a miss, because a delegation would not have represented the
   voter there either. Questions the voter skipped are left out.
3. **Uncertainty.** Agreement is a Beta-binomial posterior with a uniform
   prior. Candidates are ranked by the lower end of an 80% credible interval,
   not by the raw rate, so 18 of 20 beats 2 of 2.
4. **Choice.** The voter delegates the category to the top-ranked candidate
   only if that lower bound clears an acceptance level; otherwise they keep
   the category. The acceptance level is a run parameter.

The personal proxy uses the same procedure over all questions instead of one
category. Representatives are chosen differently, by platform, because that
is how elections work: candidates state positions and voters pick the
closest.

Points that follow:

- **Nobody is assumed to know anyone's positions.** The only constraint on how
  well a voter chooses is how much history there is, which is observable and
  can be swept.
- **Agreement above chance.** On a question most of the city agrees on,
  everyone matches everyone. Raw agreement therefore flatters every
  candidate equally; it still ranks them correctly but overstates how good
  the best one is. Reported, and an agreement-above-base-rate score is an
  open question.
- **Choosing the best of many is optimistic.** The top candidate's history
  overstates their future agreement (winner's curse). This is why fidelity is
  measured only on later questions.
- **Building a history costs overhead.** A voter has history only on
  questions they voted on. The simulation starts with a direct-voting period;
  its overhead is reported separately as setup.
- **Concentration and lost votes emerge.** Candidates who agree with many
  people and vote reliably attract delegations; ones who skip votes score
  lower because skipped votes count as misses.
- **It is also an app feature.** The same ranking is a delegate
  recommendation in the account app, with its interval shown.

### Population model

The simulation extends `delegation/simulate.py`. Every choice here is an
assumption chosen to make the comparison legible, and the main ones are
swept rather than fixed.

- **Issue dimensions.** Each person has a position on D issue dimensions
  (default 6). Positions follow a one-factor model: a shared left-right
  factor plus an independent part per dimension. The factor loading sets
  how correlated a person's positions are across issues. It is the most
  important parameter: with fully correlated positions one representative
  captures everyone and bundling costs nothing; with cross-cutting positions
  bundling is expensive. It is swept.
- **Districts.** Each district has a lean on each dimension, so residents of
  a district are more alike than the city as a whole. The district count is
  swept (one at-large seat, the current three, more) because smaller
  districts dilute less.
- **Questions.** Each question sits on one dimension with a cutpoint and a
  direction; a person's sincere vote is the side they fall on, with a little
  seeded noise on close calls. Single choice first; ranked and approval
  measures come from the same utilities as today.
- **Categories.** In the main runs a category is a dimension, and routing is
  exact (each question's dimension is known). This isolates the comparison
  from router error. Narrower categories (parts of a dimension) are a later
  variant, which is where liquid should pull further ahead of a proxy.
- **History.** Synthetic questions, many per dimension per year, so per-
  category histories are long enough to rank candidates. The 68 authored
  measures are too few for this and are used for the routing condition
  below.
- **Turnout.** Each person casts their own ballot with a seeded chance, as
  today. In the direct arrangement a non-voter's fidelity is 0 for that
  question, so direct voting is not idealised.
- **Representatives.** Each district has a few candidates drawn from its
  residents; their platform is their true position. Voters choose the
  closest platform (unweighted distance across dimensions) and plurality
  decides. The representative votes their sincere position on every
  question, so representation is not handicapped by bad faith.

### Routing condition

Per-category delegation is only low-overhead because questions are filed
into categories automatically; otherwise every voter would have to file every
question and the overhead would come back. The router therefore belongs on
the two axes:

- **False delegation** sends a question to the wrong delegate: a fidelity
  cost.
- **False keep** leaves a question with a voter who wanted it handled: an
  overhead cost.

The main runs use exact routing. A second condition applies the router
evaluation's measured error rates to the synthetic questions, and the 68
authored measures are run through the real recorded judgments as a small
check. The gap between exact and measured routing is what the router costs.

### Sensitivity

Reported as curves, not single numbers:

- correlation of positions across issues (the factor loading);
- history length before delegates are chosen;
- number of districts;
- the acceptance level for delegating a category;
- turnout, including delegates' turnout;
- exact versus measured routing.

### What it leaves out

Representatives deliberate, set agendas and broker compromises across issues;
none of that is modelled. Bundling also lets a voter trade issues they care
little about for ones they care about, which an unweighted issue-by-issue
comparison does not credit. Strategic voting, campaigning and changing
preferences are out. The walkthrough says so beside the headline figure.

## The machinery

The comparison runs on the machinery from the first design, unchanged unless
noted. A voter can hand a *category* of civic decisions to a specific person
in the network. When a ballot arrives, each question on it is read, matched
against the categories that voter has delegated, and either sent to the
matching delegate or kept by the voter. Delegation is transitive: a delegate
applies their own delegations to what they receive.

Three technical pieces carry it. Each has one decided answer:

| Piece | Decision |
|---|---|
| **Category routing** | Voters write their own categories, at any granularity. A Jev-style decision model (hosted Jev, pinned to `jev-1.14.0`) gives one yes/no probability per (question, category). Categories below a threshold drop out, a narrower category overrules the broader one it sits inside, and the highest score among the rest wins; if nothing clears the threshold the voter keeps the decision. |
| **Election processing** | The unit of work is one (voter, question) pair. Votes originate at eligible residents; the person who resolves a vote can be anyone in the network. Tallies are produced by copying each resolver's ballot back to the voters they answer for, so `voting/` is used unchanged. |
| **Circular delegation** | Two layers. Creating a delegation that would close a loop in the identical category is rejected, and one that loops on a reference question raises a warning. At resolution, if a question's chain still loops, everyone on the loop keeps that decision. Every vote therefore ends at exactly one resolver. |

The routing story is a supporting point under the revised vision, not the
headline: *topic-level delegation needs someone to decide what topic a
decision belongs to. That used to require a clerk or a fixed tag on every
measure. A small, fast decision model can do it per question, per voter, with
a probability attached and a visible threshold, and the rest of the system
can be made exact around it.* It is what keeps liquid democracy's overhead
low (see "Routing condition").

## Vocabulary

- **Arrangement** — a rule for whose ballot counts for a voter on a
  question: direct, district representative, personal proxy or liquid.
- **Fidelity** — whether the ballot counted for a voter equals their sincere
  choice, averaged over voters and questions.
- **Overhead** — the share of questions a voter decides themself.
- **Agreement** — how often a candidate's own past votes on a category's
  questions matched the voter's, with a credible interval.
- **Person** — a member of the network. Has a set of residences (jurisdiction
  ids). May be a voter, a delegate, or both.
- **Category** — a short piece of text, written by a voter, describing the
  decisions they want to hand over. It can be as broad as "all things taxes"
  or as narrow as "the well-being of tree frogs in the Amazon". There is no
  shared taxonomy and no fixed level. Two voters have the same category only
  when the text is identical after normalising case and whitespace.
- **Delegation** — `(delegator, category, delegate)`. At most one delegate per
  delegator per category. No self-delegation. The delegate must be a person in
  the network.
- **Ballot paper** — a jurisdiction plus an ordered list of questions. Each
  question is a ballot measure (title, summary, options). It is `BallotPaper`
  in code, to keep it apart from `voting.types.Ballot`, which is one voter's
  cast vote on one question.
- **Direct vote** — a person's own ballot on one question. It always overrides
  that person's delegations for that question.
- **Judgment** — the decision model's probability that a question is primarily
  about a category.
- **Resolver** — the person whose ballot is used for a given voter on a given
  question. The literature calls this person the guru.

## Piece 1: Category routing

### What the model does and what code does

The decision model makes small judgments. Code makes the routing decision.

For each ballot question, one request goes to Jev with the question as the
state and one yes/no (Noul) question per distinct category in use across the
network. The category's own text goes into the instruction:

```json
{
  "model": "jev-1.14.0",
  "state": {
    "title": "...",
    "summary": "...",
    "options": ["Yes", "No"]
  },
  "questions": {
    "cat_3f9a1c": {
      "type": "noul",
      "instructions": "Is this ballot question primarily about the following topic? Topic: the well-being of tree frogs in the Amazon"
    },
    "cat_b27e40": {
      "type": "noul",
      "instructions": "Is this ballot question primarily about the following topic? Topic: all things taxes"
    }
  }
}
```

The response carries one probability per category. Question names are hashes
of the category text; per TypeSafe's docs the model never sees them. The shape
above follows TypeSafe's docs as read on 2026-11-09; the instruction wording
is fixed in build step 2 after the router evaluation.

The per-voter rule is plain code:

```
route(person, question):
    if person cast a direct vote on question:      keep (direct vote)
    C = categories this person has delegated
    if C is empty:                                 keep
    if any judgment for C is missing:              keep (router unavailable)
    C = the categories in C whose probability >= threshold
    if C is empty:                                 keep (none of the available)
    drop from C any category that has a narrower category inside it still in C
    c* = the category left in C with the highest probability
         (exact ties broken by the order of the person's category list)
    send to delegate(person, c*)
```

Every category the voter has is scored. The threshold is a floor: if nothing
clears it, the decision returns to the voter. Among the categories that clear
it, specific overrules general, and then the highest score wins. The output
contract is the one originally proposed: the voter's own categories, or none
of the available.

### Voter-defined categories

- **Any text, any granularity.** A voter can hold a narrow category and a
  broad one at the same time, with different delegates.
- **Each category is one more yes/no question.** TypeSafe states that answers
  are independent, so one voter's categories cannot change the scores of
  another's.
- **Judgments are shared by text.** A judgment is stored per question and
  category text, and every voter who uses that exact text gets the same score.
- **Bounded length.** A category is one sentence of at most 200 characters,
  so it stays a description and not a set of instructions.
- **Voter-written text reaches the model.** TypeSafe lists adversarial content
  as a failure mode. A voter who writes misleading category text changes only
  their own routing.
- **New text needs a live call.** A category the viewer types is judged live,
  which needs the API key at runtime. Without it the viewer picks from the
  curated pool.

### Nested and overlapping categories

A narrower category overrules the broader one it sits inside, when both clear
the threshold. Decided 2026-11-10, after the router evaluation. The first
decision (2026-11-09) was no special handling, with a test attached; this
section keeps that history.

- **Overlapping categories.** A carbon tax is about both "taxes" and "the
  environment". Either delegate is a reasonable outcome for the voter, and
  the higher score wins.
- **Why nested categories needed a rule.** A yes/no score measures whether the
  statement is true, not which category fits best. If "tree frogs in the
  Amazon" sits inside "the environment", the broad statement is true whenever
  the narrow one is, so nothing makes the narrow category score higher even
  though the voter created it as a carve-out.
- **Measured on 2026-11-10.** In the router evaluation, 28 cases put a
  question squarely inside a narrow category while the voter also held the
  broad category above it. The narrow category got the vote in 17, the broad
  one in 10, and one was an exact tie. Neither prediction held: the broad
  category does not win systematically, and the scores do not reliably prefer
  the narrow one. In 18 of the 28 the two scores are within 0.04 of each
  other, in either direction. Five go to the broad category by 0.13 or more,
  including both tree-frog questions.
- **The rule (`delegation/routing.py`).** A category that clears the threshold
  gives way when a narrower category inside it also clears. The narrow
  category must clear the threshold itself; if it does not, the broad one
  still gets the question. The receipt lists the categories that gave way.
- **Where nesting comes from (`delegation/nesting.py`).** Voters declare
  nothing. For two categories A and B that one voter holds, Jev is asked
  whether every decision about A is also a decision about B, in both
  directions. A pair is nested only when the answer is yes one way and no the
  other; yes both ways means two wordings of one thing. These judgments are
  recorded and replayed like question judgments, and nesting cannot loop.
  When a judgment is missing the pair is not nested and the higher score
  wins.
- **Effect on the evaluation's cases.** With the nesting declared in the
  fixture, the narrow category gets 26 of the 28 nested cases, up from 17.
  The other two score below the threshold and fall back to the broad one.
  The error counts on the 544 voter cases do not change.
- **Detection, measured 2026-11-10.** All 870 ordered pairs of the 30 pool
  categories were asked. Jev detected 11 of the 14 nested pairs labelled in
  the fixture and none of the other 856. The eleven score 0.73 to 0.91; no
  unlabelled pair scores above 0.48. The misses are the fire department
  inside "policing and public safety" (0.29, an arguable label), police
  oversight inside the same (0.63) and street trees inside the environment
  (0.64).
- **Effect with detected nesting.** The narrow category gets 24 of the 28
  nested cases, against 26 with the labelled nesting and 17 with none, and
  the error counts on the 544 voter cases are again unchanged.
- **Nesting threshold.** 0.7, set before the data was seen. Any value from
  0.49 to 0.63 would detect 13 of the 14 with no extra pairs. It has not
  been lowered, because 14 labelled pairs is a small sample to tune on.
- **Not taken.** Asking one follow-up choice question among the categories
  that clear the threshold. It needs a request per voter and question, and
  the choice form leans toward the first option listed.

### Why yes/no per category and not one choice question

A single choice question listing the voter's categories plus "none" was the
first design. It is kept as a comparison arm, not the default, for these
reasons:

- **No built-in "none".** Neither Jev nor OpenAI's Decisions API has one.
  TypeSafe's docs say an added "none of the above" option "may not work well"
  and suggest a companion yes/no question.
- **Order bias.** TypeSafe's docs say that in a choice question Jev leans
  toward the option that comes first, so the order of a voter's categories
  would matter.
- **Dependence on the option set.** Choice probabilities sum to one across the
  supplied options, so adding a delegate for an unrelated category shifts the
  others. With yes/no judgments, TypeSafe states every answer is independent
  and questions can be added or removed without changing the others.
- **Cost and consistency.** Judgments are per question and distinct category
  text, not per voter. The state is billed once per request and each extra
  question is cheap. Every voter who uses the same category text sees the
  same score, so receipts are auditable.

### Threshold

Start at 0.7, TypeSafe's suggested starting point for "yes", then set it from
the labelled decisions. Sending a decision to a delegate the voter would not
have chosen is the expensive error; keeping a decision that could have been
delegated only costs the voter a vote they can cast themself. The threshold is
a run parameter and is shown on every receipt.

The evaluation supports keeping 0.7. Of 292 cases sent to a delegate, 4 went
to a category the question was not about (1.4%), and 21 of 309 cases with an
acceptable category were kept (6.8%). At 0.75 those are 3 and 23; at 0.85
they are 0 and 60. With 68 questions the threshold should not be tuned more
finely than that.

### Failing closed

If Jev returns an error, no API key is configured, or a judgment is missing
and not recorded, the decision stays with the voter and the receipt says the
router did not run. The router never guesses.

### Known limits of the model

- **Not repeatable to the last digit.** TypeSafe's cookbook shows the same
  question moving by up to 0.015 between runs. There is no seed parameter. See
  Reproducibility.
- **Names over definitions.** arXiv 2609.26758 found that typed decision
  models follow an option's name over the definition bound to it (Jev flipped
  32.5% of yes/no answers when names were rebound). A category here is a
  single piece of text with no separate name and definition, which avoids the
  mismatch. The risk applies mainly to the single-choice comparison arm.
- **Long state hurts.** TypeSafe lists falling accuracy as the state grows.
  The state is the title, summary and options, not full legal text.

### Router evaluation

Run once against Jev, with every response recorded so the results replay
without a key:

- **Category pool:** a few dozen category texts at mixed granularity, written
  the way voters would write them. It includes broad and narrow categories,
  nested pairs and overlapping pairs.
- **Labelled set:** short ballot questions, each labelled with the pool
  categories it is acceptably about. For a nested pair, the label also says
  whether the question sits squarely inside the narrow category. For each
  question, sample voter category sets from the pool; when no acceptable
  category is in the set, the correct answer is "keep".
- **Errors:** false delegation (sent to a category that is not acceptable),
  false keep (an acceptable category was available but the voter kept it).
- **Reported:** false-delegation rate against coverage across thresholds; the
  same curve for the single-choice arm; how often the narrow category of a
  nested pair wins on questions squarely inside it; repeat-call spread on a
  subset.
- **Not used:** anything under `eval/restricted_bank/`.

Results (2026-11-10, `jev-1.14.0`; full tables and limits in
`eval/benchmarks/delegation_router_v1/README.md`):

- **Routing errors at 0.7:** 4 false delegations in 292 delegated cases and
  21 false keeps in 309 delegable ones. All four false delegations went to
  one of two broadly worded categories, "the city budget and spending" and
  "housing and land use". Questions that belong to no category never scored
  above 0.08.
- **Nested categories:** under highest score alone the narrow category won
  17 of 28. With the narrower-category rule it gets 26 using the labelled
  nesting and 24 using the nesting Jev detected; see above.
- **Single-choice arm:** it never missed an acceptable category but made 14
  false delegations to the yes/no form's 4. At matched coverage the two are
  close (11 against 14), so the yes/no form's advantage is the threshold, not
  a large accuracy gap.
- **Repeat spread:** 242 of 360 judgments were identical across four calls.
  The largest spread was 0.06, four times TypeSafe's published figure, and
  one judgment crossed the threshold between calls.
- **Labels:** one author wrote and labelled the pool and questions, and some
  unlabelled high scores are defensible, so the error rates reflect the
  labels as well as the model.

## Piece 2: Election processing

A ballot is processed per question:

1. **Issue.** Persons whose residences include the ballot's jurisdiction are
   eligible. Each eligible person originates exactly one vote per question.
2. **Judge.** Fetch the judgments for that question for every distinct
   category in use across the network.
3. **Route.** Apply the routing rule to whoever currently holds the vote. At
   each hop the *holder's* own delegations apply.
4. **Resolve.** Follow hops until someone keeps the vote (see Piece 3).
5. **Cast.** Each resolver casts one ballot per question. It applies to every
   vote they hold on it.
6. **Tally.** For each eligible voter, copy their resolver's ballot under the
   voter's own id and hand the list to the chosen `voting/` method.
7. **Report.** Receipts, inboxes, concentration, and the same tally under
   direct voting.

Points that follow from this:

- **Eligibility decides where votes originate, not who resolves them.** A
  person outside the jurisdiction has no vote of their own on that ballot but
  answers for whatever was handed to them.
- **A ballot fans out.** One voter's 15 questions can end with 15 different
  resolvers.
- **`voting/` needs no changes.** It has no weight support today
  (`VoteCounts` is `dict[str, int]`). Copying a resolver's ballot is
  equivalent to weighting it for any anonymous method and works for ranked,
  score and quadratic ballots as well as single choice.
- **Seeded tiebreak.** Each question is tallied with
  `random_tiebreak(seed)` and the seed is recorded on the run, as the voting
  package conventions ask of simulations. A fresh tiebreak is built for each
  question, because a tiebreak object carries its own random stream.
- **Abstention.** If a resolver casts nothing, every vote they hold on that
  question is an abstention, which `voting/` already counts.

### What a run returns

- **Receipt (per voter):** for each question, the scores for their categories,
  the threshold, sent or kept and why, the chain, the resolver, and the choice
  cast.
- **Inbox (per resolver):** the questions they answer, for how many voters,
  and from which jurisdiction.
- **Per question:** the tally under each requested method, the direct-voting
  tally for comparison, the share of votes delegated, the largest share held
  by one resolver, the Gini coefficient of resolver weights, chain lengths,
  and the loops found.

## Piece 3: Circular delegation

### Why prevention alone is not enough

Routing is per voter and categories are voter-written, so whether two
delegations are both active depends on the question. Suppose A delegates
"housing and land use" to B, and B delegates "transportation and
infrastructure" to A. Neither delegation closes a loop when
it is created. A transit-oriented zoning measure scores 0.80 for housing and
0.85 for transportation. A's only category is housing, so A's vote goes to B.
B's only category is transportation, so it comes straight back. The loop
exists for this measure only.

### Layer 1: checks when a delegation is created

Two checks run when a delegation `(u, c, v)` is created.

**Rejected** if `u == v`, or if following delegations of the identical
category `c` from `v` reaches `u`:

```
would_close_loop(u, c, v):
    seen = {u}
    cur = v
    while cur is not None:
        if cur in seen: return True
        seen.add(cur)
        cur = delegate(cur, c)        # None when cur has no delegate for c
    return False
```

Each person has at most one delegate per category, so this is a single walk.
It covers the direct case: voter 1 delegates a category to voter 2, and voter
2 then tries to delegate the same category to voter 1.

**Warned** otherwise, when the loop depends on the question. Because
categories are voter-written, two differently worded categories can both
match the same question, and that cannot be known from the text alone. The
new delegation is resolved against a set of reference questions (the curated
ballots), and any that would come back to `u` are shown. The delegation is
still allowed; Layer 2 decides what happens on a real question.

### Layer 2: rule when a question is resolved

For one question, each person has at most one next hop, so the structure is a
set of chains that either end or loop.

```
for each eligible voter p whose resolver is unknown:
    walk p -> next(p) -> ... recording the path
    stop at the first person r that
      (a) has no next hop         -> r resolves the whole path
      (b) is already resolved     -> resolver[r] resolves the whole path
      (c) is already on the path  -> loop: every person from r's first
                                     appearance to the end of the path
                                     resolves for themself; everyone
                                     earlier on the path resolves to r
```

**Everyone on a loop keeps the decision.** This is the same outcome as "none
of the available". Voters upstream of the loop still reach the loop member
their chain leads to, and that member now votes directly. The receipt says the
chain came back, so the decision stayed.

### Alternatives considered

| Rule | Where it comes from | Why not |
|---|---|---|
| Votes on a loop are lost | LiquidFeedback (a loop with no direct voter yields no vote); Brill et al. treat such voters as isolated | Silently drops upstream delegators |
| Void one delegation in the loop | MinSum-style rules from the ranked-delegation literature, with "self" as the backup | Needs a tiebreak that hands one member the whole loop's weight |
| Chosen: everyone on the loop keeps it | Closest to Christoff and Grossi's default-opinion idea, with the voter's own ballot as the default | — |

The chosen rule treats all loop members identically and needs no tiebreak or
timestamp.

### Invariants to test

There is no property-testing library in `requirements.txt`, so these run over
300 seeded random networks with plain pytest, in
`delegation/tests/test_invariants.py`:

1. Every eligible voter has exactly one resolver.
2. A resolver resolves for themself and either has no next hop, voted
   directly, or is on a loop.
3. Per question, the weights held by resolvers sum to the number of eligible
   voters.
4. No chain is longer than the number of persons.
5. Results do not depend on the order voters are processed or on relabelling.
6. Every member of a loop is their own resolver.
7. Giving a person a direct vote makes them their own resolver and changes
   nobody who is not upstream of them.
8. With no delegations, the tally equals the direct-voting tally.
9. A network built only through the creation checks has no loop on any
   question where every hop uses the identical category.

## Architecture

```
delegation/
  types.py       Person, Category, Delegation, Network, Question,
                 BallotPaper, Judgments                              [built]
  routing.py     the per-voter routing rule (pure)                   [built]
  graph.py       creation checks and per-question resolution (pure)  [built]
  election.py    issue -> route -> resolve -> cast -> tally via voting/  [built]
  metrics.py     delegated share, largest share, Gini, chain lengths [built]
  tests/         unit tests and the nine invariants                  [built]
  judgments.py   JudgmentSource protocol, recorded-judgment store,
                 gathering with failing closed                       [built]
  jev.py         Jev adapter over plain HTTP (httpx); the one module
                 that uses the network, not imported by the package  [built]
  nesting.py     which categories sit inside which: asking, recording,
                 deriving                                            [built]
  simulate.py    seeded synthetic network, its dated changes, homes,
                 turnout and sincere ballots                         [built]
  ballots.py     ballot types (single choice, ranked, approval) and
                 the voting/ method that counts each                 [built]
  scenario.py    loads the curated scenario                          [built]
  data/measures_v3.json  hand-written: the city, every measure with
                 its wording, fiscal note and arguments, the support
                 numbers, the viewer's account and its past          [built]
  data/recorded_v3/      judgments for measures reworded since the
                 evaluation                                          [built]
  data/scenario_v3.json  built from the two above plus the pool,
                 the nesting and the evaluation's judgments          [built]
api/
  routers/delegation.py     HTTP only                                [built]
  schemas/delegation.py     Pydantic request and response models     [built]
  services/delegation.py    orchestration                            [built]
scripts/
  build_delegation_scenario.py  builds scenario_v3.json; `plan` and
                 `build` use no network, `collect --live` asks Jev
                 about reworded measures                             [built]
eval/
  delegation_router.py              router evaluation (pure)        [built]
  run_delegation_router_eval.py     plan, smoke, collect, report    [built]
  fixtures/delegation_router_v1.json  30 categories, 68 questions   [built]
  benchmarks/delegation_router_v1/  recorded answers and summary    [built]
app/liquid/                 the account: delegations, votes, profiles [built]
components/liquid/          its client components and shared state    [built]
```

- `delegation/` imports `voting/` and nothing else from the other demos.
- The pure core takes judgments as input. Tests use a scripted
  `JudgmentSource`; nothing in the core needs a network.
- The API is stateless. v1 keeps the viewer's delegations and votes in the
  browser's local storage and adds no tables.

### Endpoints

The server rebuilds the network and ballot papers from the scenario file and
a seed, so a request carries only what the viewer changed: their delegations,
in list order, and any votes they cast themself.

- `GET /api/delegation/scenario` — the seeded network, the ballot papers with
  their closing offsets, and the delegations the viewer's account starts with.
- `GET /api/delegation/people/{person_id}` — one person's profile: counts,
  what they hand over and are handed, and every closed question issued to
  them or decided by them, with how it went.
- `POST /api/delegation/delegations/validate` — the creation checks on one
  proposed delegation: a rejection with the chain, or the open questions
  on which it would come back to the viewer.
- `POST /api/delegation/judgments` — a category's judgments for every open
  question, and its nesting against the viewer's other categories. Recorded
  answers first; the rest are asked of Jev only when live judgments are
  switched on, and otherwise reported as missing.
- `POST /api/delegation/resolve` — a ballot paper, the viewer's delegations
  and votes, threshold and tiebreak seed in; per question, the delegated and
  direct tallies, concentration measures, the viewer's receipt and the votes
  the viewer answers for. Reads recorded judgments only. A closed paper is
  returned as it was resolved, with the viewer's starting account, whatever
  the request carries.

Behaviours worth knowing:

- **Live judgments are opt-in twice.** The server asks Jev about a
  viewer-written category only when it has `TYPESAFE_API_KEY` and
  `DELEGATION_LIVE_JUDGMENTS` is switched on. A key alone does nothing. New
  answers are recorded under the git-ignored `.cache/delegation/`.
- **The first wording of a category stays.** A category's identity ignores
  case and whitespace, but a judgment records the exact wording asked. The
  service reuses the pool's wording, or the wording a written category was
  first judged under, so every spelling shares the same judgments.
- **The viewer's vote is their direct vote.** A vote the viewer casts on a
  question overrides their delegations for it and is the ballot used for
  anyone they answer for. Until they vote, the votes they hold count as
  abstentions.
- **History is fixed.** Closed papers are resolved once, with the account
  the viewer started with, and profiles are read from them. Editing a
  delegation changes open votes only.
- **New categories are rationed.** The server counts the new categories it
  has asked Jev about each day (UTC) and stops at
  `DELEGATION_LIVE_DAILY_CATEGORIES`, 200 by default. A written category is
  judged against the open questions only.

## Account scenario (the companion app's city)

This is the city the account app runs on, built before the 2026-11-14
revision. The comparison's population model (see "Population model") is
separate and larger. Once that model exists, this scenario's delegation
behaviours are replaced by choice from vote history, so the app and the
walkthrough describe the same world; until then the app's delegations are
preference-blind and its "result changed" counts are not evidence of
anything.

Built in `delegation/simulate.py`; the scenario's settings are in
`delegation/scenario.py`.

- One city of three districts with 80 residents each, 20 people who live
  outside it and can still be delegates, and the viewer: 261 people, all
  seeded.
- Each person has a position on three issue dimensions with a lean per
  district and a pull toward measures sited near their home. Each question
  has a direction and a cutpoint, and a little seeded noise decides close
  calls. A person's sincere ballot is the side they fall on. This supplies
  resolver ballots and the direct-voting baseline. It is a toy spatial model
  and makes no claim about real voters.
- A delegating person hands over three to seven pool categories, with broad
  categories three times as likely as narrow ones.
- Three delegation behaviours: keep every decision (30% of the population as
  drawn), trust one of eight well-known people for the category (42%), trust
  someone in your own district (28%). The delegate is drawn at random from
  those, without regard to agreement. Every delegation goes through the
  creation check.
- Measured 2026-11-14 on the 47 closed questions: 17% of votes were decided
  by someone else, the heaviest resolver held 20% of one question, counted
  turnout rose from 56.3% to 60.9%, and 252 of 1,569 delegated votes (16%)
  ended with a resolver who did not vote.
- Everyone has a made-up name and a unique username.
- The viewer is a District 1 resident. The simulated network holds no
  delegations of theirs; the scenario gives their account eight to start
  with, four broad and four narrow. Nine residents across the three districts
  each hand the viewer one authored category, in categories the viewer does
  not hand on, so the viewer answers for others, including on ballot papers
  issued to districts they do not live in.
- Twelve ballot papers use each of the evaluation's 68 questions once. Each
  has a day offset from today: eight have closed, over about eleven months,
  and four are open, closing in 3, 6, 9 and 16 days. City papers go to 241
  voters and district papers to 80 or 81.
- The viewer's past: a sincere choice from an authored position on every
  closed question, except two they let lapse and two they voted on themself
  despite a delegation. Of 40 closed questions issued to them, 16 were
  decided by a delegate.
- These shares come from the assumed behaviours above, not from data.

## Presentation (revised 2026-11-14)

The claim is about a population, and one account cannot show a frontier for
a population. The demo therefore becomes two parts:

1. **The walkthrough** (`/liquid`), written like a short research paper over
   the simulated population, in the manner of the districting walkthrough and
   the apportionment essay:
   1. Setup: the city, the issue dimensions, how sincere votes arise.
   2. The three arrangements on the two axes, and the headline figure.
   3. The ladder: representative, proxy, liquid, separating dilution from
      bundling.
   4. How delegates are chosen from vote history, with the uncertainty
      interval, and what history length buys.
   5. Sensitivity: correlation across issues, districts, acceptance level,
      turnout.
   6. Outcomes against direct voting, including Ostrogorski-style cases.
   7. Who decides what a question is about: the router, its evaluation, and
      what its errors cost on each axis.
   8. Failure modes: concentration, votes lost to resolvers who do not vote,
      loops.
   9. What is left out.
2. **The control center** (the account app, moving to `/liquid/account`):
   what using liquid democracy would look like for one person. Its scope is
   frozen apart from three changes: delegate recommendations ranked by vote
   history with their interval, a representation scorecard for the account
   (its fidelity and overhead under its district representative, a personal
   proxy and its delegations, on the closed questions), and moving City
   Results and the city map into the walkthrough.

The route change is a proposal; the walkthrough could instead live at
`/liquid/study` with the app staying at `/liquid`.

## Account app UI

The demo is an account app in the simulated city. The first version was a
single page (2026-11-10); it was rebuilt as an account with separate screens
(2026-11-11) and then given an app frame and its own look. Since then it has
gained City Results, an Activity log, a routing tracer, a backtest on edit,
grouping of category wordings and a city map, which CLAUDE.md describes; the
list below is the core.

**Frame.** The demo header stays above. Everything under it is the app: a
top bar with people search, a notifications bell and the signed-in account
(top right), and a side menu with Hub, Incoming Votes, Profile, About this
demo and Reset demo. The look is a dark control surface, scoped by
`.liquid-app`: near-black with violet and blue, glass panels, mono readout
labels, a dot-grid canvas for the graph.

1. **Hub** (`/liquid`). Four readouts (waiting on you, with your delegates,
   votes reaching you, delegations in and out) and a node graph read left to
   right: who hands the viewer a category, the viewer, who the viewer hands
   categories to. An outgoing node opens a side sheet for that delegation:
   change the delegate or the category, each with a confirmation step,
   remove it, or view the delegate's profile. An incoming node opens that
   person and the open votes of theirs that currently reach the viewer. An
   extra node, and a button, add a delegate: search by name or `@username`,
   then write the category. A refused loop shows its chain; an allowed one
   lists the open questions that would come back.
2. **Incoming Votes** (`/liquid/votes`). Open votes, soonest to close first,
   in two boxes. "Needs you" holds the viewer's own votes that fit no
   category and other people's votes that reached them; a vote not cast when
   the ballot closes is an abstention. "With your delegates" holds the votes
   routed out, which the viewer can still vote on themself.
3. **A vote** (`/liquid/votes/[questionId]`). The question in full, who it was
   issued to, the viewer's receipt (scores, threshold, chain, resolver,
   ballot), the votes that reached them, and for a closed vote the delegated
   result beside the direct one with concentration.
4. **Profile** (`/liquid/people/[username]`). Name, username and district,
   then three tabs, each openable full screen: stats (delegation rate, who
   delegates to them, votes decided for others), their node graph in both
   directions, and their voting history, newest first, tagged voted,
   delegated or did not vote.
5. **Notifications.** Votes that close within a week and still wait on the
   viewer, and the last few votes a delegate decided for them.
6. **About** (`/liquid/about`). Method and limits.

Not built: a free-text question judged live, a browsable people page, and
an account name other than "You / @you".

## Build sequence

1. **Core.** `delegation/` types, routing rule, creation checks, resolution,
   vote-copy tally, metrics, invariants. Judgments come from fixtures. No
   network calls. *Done.*
2. **Jev judgments.** Adapter, pinned model, recorded-judgment store, failing
   closed, category pool, labelled set, router evaluation including the
   nested-pair test. *Done.* The
   adapter calls the HTTP API directly with `httpx`, which the repo already
   depends on, so there is no SDK to install and no alias or hidden retry
   behaviour. The key is read from `TYPESAFE_API_KEY` in the environment or
   `.env.local`. The collections sent 690 requests in all and were billed
   365,220 input tokens, about $0.015 at list price. The `plan` command's
   rough estimate was about a third low for the question judgments and
   close for the containment ones. Paid commands refuse to
   run without `--live`, and each paid run needs explicit approval.
3. **Network and API.** Synthetic network, curated ballots with recorded
   judgments, the four endpoints. *Done.* No network calls were made: the
   scenario file is built from answers already recorded in step 2.
4. **UI.** *Done*, first as a single page and then rebuilt as an account
   (see UI above). The scenario gained names, a timeline of papers and the
   viewer's starting account; the API gained profiles and a daily limit on
   newly judged categories. The history is generated from the spatial model
   and still to be authored.

Steps for the revised vision (2026-11-14), each its own PR:

5. **Population and arrangements.** In `delegation/`, pure and seeded: the
   one-factor population over D dimensions with district leans, synthetic
   questions per dimension, turnout, district elections by plurality, the
   personal proxy and liquid delegation chosen from vote history with the
   Beta-binomial lower bound, a chronological split between history and
   evaluation, and fidelity, overhead and outcome agreement. Tests include:
   direct voting scores 1 for every voter who votes; with perfectly
   correlated positions and one district, representative and proxy
   fidelity converge; more history never lowers the expected rank quality
   on a fixed population.
6. **Benchmark.** `eval/benchmarks/delegation_frontier_v1/`: the headline
   frontier, the ladder, the sensitivity sweeps and the routing condition,
   rebuilt byte for byte from a runner, as the synthetic preference
   benchmark is.
7. **Walkthrough.** The `/liquid` research page over the benchmark's
   recorded results, with a small live re-run where it is cheap.
8. **Control center.** Regenerate the account scenario with history-based
   delegation, add the recommendation and the scorecard, move the app.

## Reproducibility

- **Pinned model.** Always `jev-1.14.0`, never `jev-latest`. The versioned id
  returned in each response is recorded.
- **Recorded judgments.** Each (model id, state, question) is hashed and its
  first response stored, append-only. The question includes the category
  text. Judgments for the curated ballots against the curated category pool
  are committed in `delegation/data/scenario_v3.json`, so that part of the
  public demo replays without a key. A category the viewer writes is judged
  live, which needs the key and the `DELEGATION_LIVE_JUDGMENTS` switch.
- **Resolution reads only recorded judgments.** A run is deterministic given
  its inputs. The run key is (ballot hash, network hash, judgment snapshot
  hash, threshold, method, seed).
- **Documented exception.** Jev is the one non-deterministic input. A live
  judgment for a new question can differ slightly from a later one; once
  recorded it does not change.
- **Retirement.** TypeSafe retires pinned versions on 30 to 60 days' notice.
  Recorded judgments keep replaying. New ballots then need a new pin and a
  threshold re-check.
- **Seeds.** Network generation, sincere ballots and tiebreaks are seeded and
  the seeds are part of the run.

## Privacy

Only question text and category text are sent to TypeSafe. Category text is
written by voters, so the UI says that it is sent to a third party. No person,
delegation or vote leaves the machine. TypeSafe states it does not train on
requests.

## Open questions

1. **Category pool and labelled set source.** Default: write a synthetic pool
   and question set first. A Ballotpedia ingest is more realistic but is its
   own project.
2. **Jev access.** The launch post describes early access with a waitlist. The
   key has to be created by the repo owner.
3. **Nesting threshold.** At 0.7 Jev's containment answers find 11 of the
   14 labelled nested pairs and no others. Lowering it to about 0.6 would
   find 13. Whether to lower it is undecided; see Piece 1.

Raised by the 2026-11-14 revision:

4. **Agreement above chance.** Rank candidates by raw agreement, or by
   agreement above what two random voters would share on those questions.
   Default: raw agreement with the lower bound, and report the inflation.
5. **Bootstrapping history.** Default: a direct-voting period before
   delegates are chosen, reported as setup overhead. Alternative: voters
   review a sample of past questions, which costs overhead in the same way.
6. **Re-choosing.** Choose once after the history period, or re-rank after
   each ballot paper. Re-ranking is more realistic and shows churn; choosing
   once is simpler to explain. Default: once, with re-ranking as a variant.
7. **Which categories a voter hands over first.** Default: in order of the
   top candidate's lower bound, which is what traces the liquid curve.
8. **Representative candidates.** How many per district and how they are
   drawn (at random from residents, or spread across the district's range).
9. **Precedence between overlapping categories.** Highest score is within
   the router's repeat noise for many pairs; the voter's own list order is
   the alternative. Matters only once categories are narrower than a
   dimension.
10. **Onward delegation.** A received vote moves on under the receiver's own
    categories, so it can end with someone the voter never chose. Report
    how often; a per-delegation "decide it yourself" option is the
    alternative.
11. **Votes lost to resolvers who do not vote.** History-based choice
    penalises unreliable delegates; whether a backup delegate is still
    needed is decided from the benchmark.

The route name is settled: the page stays at `/liquid`, which the placeholder
and the navigation already use.

## Follow-ups outside this doc

CLAUDE.md and AGENTS.md now carry the demo 5 summary and status. README.md
still lists liquid democracy as demo 4, planned, at `/delegation`, and has no
apportionment demo; it was not part of this update.

## Deferred

- Database tables (`delegation_*`) and saved networks.
- A precedence rule for nested categories, only if the build step 2 test
  calls for it.
- Ranked backup delegates, split delegation, weight caps.
- OpenAI Decisions and open-weight models as further comparison arms.
- Delegate recommendations from demo 2's preference posterior. The
  comparison does not wait for demo 2: it needs many simulated people with
  known preferences, which demo 2 does not provide. Demo 2 could later stand
  in for the signed-in account's own positions.
- Salience-weighted fidelity (decided against 2026-11-14 as hard to model
  credibly).
- Proportional or at-large representation as further baselines.
- Grounding the cross-issue correlation in survey data (ANES, CES).

## References

- Brill, Delemazure, George, Lackner, Schmidt-Kraepelin, *Liquid Democracy
  with Ranked Delegations* — https://arxiv.org/abs/2112.07509
- *Circular Delegations – Myth or Disaster?*, The Liquid Democracy Journal —
  https://liquid-democracy-journal.org/issue/3/The_Liquid_Democracy_Journal-Issue003-02-Circular_Delegations_-_Myth_or_Disaster.html
- Christoff and Grossi, *Binary Voting with Delegable Proxy* —
  https://arxiv.org/abs/1707.08741
- Colley, Grandi, Novaro, *Unravelling multi-agent ranked delegations* —
  https://arxiv.org/abs/2111.13145
- Kahng, Mackenzie, Procaccia, *Liquid Democracy: An Algorithmic Perspective*
  — https://jair.org/index.php/jair/article/view/12261
- Gölz, Kahng, Mackenzie, Procaccia, *The Fluid Mechanics of Liquid
  Democracy* — https://arxiv.org/abs/1808.01906
- Kling et al., *Voting Behaviour and Power in Online Democracy* —
  https://arxiv.org/abs/1503.07723
- TypeSafe, *Introducing System One Models & Jev* —
  https://typesafe.ai/blog/introducing-system-one-models-and-jev
- TypeSafe docs — https://docs.typesafe.ai
- OpenAI Decisions guide —
  https://developers.openai.com/api/docs/guides/decisions
- Sun, Xu, Shi, Yang, *Type-Safe Is Not Error-Free* —
  https://arxiv.org/abs/2609.26758
