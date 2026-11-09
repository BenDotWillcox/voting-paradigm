# Demo 5: Liquid Democracy — Design Doc

Living design document for the liquid democracy demo. Edit when decisions change.

Status: design agreed 2026-11-09; categories revised the same day to be
voter-defined. Build step 1 (the core, in `delegation/`) is implemented;
steps 2 to 4 are not.

## What we're building

A voter can hand a *category* of civic decisions to a specific person in the
network. When a ballot arrives, each question on it is read, matched against
the categories that voter has delegated, and either sent to the matching
delegate or kept by the voter. Delegation is transitive: a delegate applies
their own delegations to what they receive.

Three technical pieces carry the demo. Each has one decided answer:

| Piece | Decision |
|---|---|
| **Category routing** | Voters write their own categories, at any granularity. A Jev-style decision model (hosted Jev, pinned to `jev-1.14.0`) gives one yes/no probability per (question, category). The voter's highest-scoring category wins if it clears a threshold; otherwise the voter keeps the decision. |
| **Election processing** | The unit of work is one (voter, question) pair. Votes originate at eligible residents; the person who resolves a vote can be anyone in the network. Tallies are produced by copying each resolver's ballot back to the voters they answer for, so `voting/` is used unchanged. |
| **Circular delegation** | Two layers. Creating a delegation that would close a loop in the identical category is rejected, and one that loops on a reference question raises a warning. At resolution, if a question's chain still loops, everyone on the loop keeps that decision. Every vote therefore ends at exactly one resolver. |

The story being told: *topic-level delegation needs someone to decide what
topic a decision belongs to. That used to require a clerk or a fixed tag on
every measure. A small, fast decision model can do it per question, per voter,
with a probability attached and a visible threshold, and the rest of the
system can be made exact around it.*

## Vocabulary

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
    c* = the category in C with the highest probability
         (exact ties broken by the order of the person's category list)
    if probability(question, c*) >= threshold:     send to delegate(person, c*)
    otherwise:                                     keep (none of the available)
```

Every category the voter has is scored and the highest score wins. The
threshold is only a floor: if the best category does not clear it, the
decision returns to the voter. The output contract is the one originally
proposed: the voter's own categories, or none of the available.

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

There is no special handling: the highest score wins. Decided 2026-11-09, with
a test attached.

- **Overlapping categories.** A carbon tax is about both "taxes" and "the
  environment". Either delegate is a reasonable outcome for the voter.
- **Nested categories are the open risk.** A yes/no score measures whether the
  statement is true, not which category fits best. If "tree frogs in the
  Amazon" sits inside "the environment", the broad statement is true whenever
  the narrow one is, so a well-calibrated model should score the broad
  category at least as high. The narrow category would then rarely win, even
  though the voter created it as a carve-out.
- **Unknown for Jev.** The "primarily about" wording may pull scores toward
  the best-fitting level, in which case nothing more is needed.
- **Test in build step 2.** Include nested pairs in the router evaluation and
  measure how often the narrow category wins on questions squarely inside it.
- **Only if the broad category wins systematically,** add one of two fixes.
  Both keep the judgment with Jev and ask nothing extra of the voter:
  - When a category is created, ask Jev whether it sits inside one of the
    voter's existing categories, and let the narrower one win when both pass.
  - When several categories pass the threshold, ask one follow-up choice
    question among just those.

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
  judgments.py   JudgmentSource protocol, recorded-judgment store    (step 2)
  jev.py         Jev adapter (typesafe-sdk imported lazily)          (step 2)
  data/          recorded judgments for curated ballots              (step 2)
  simulate.py    seeded synthetic network and sincere ballots        (step 3)
api/
  routers/delegation.py     HTTP only
  schemas/delegation.py     Pydantic request and response models
  services/delegation.py    orchestration
eval/
  delegation_router.py      labelled set and router evaluation
app/liquid/                 the demo page (route already exists)
```

- `delegation/` imports `voting/` and nothing else from the other demos.
- The pure core takes judgments as input. Tests use a scripted
  `JudgmentSource`; nothing in the core needs a network.
- The API is stateless. v1 keeps the viewer's delegations in browser session
  state and adds no tables.

### Endpoints

- `GET /api/delegation/scenario` — the seeded network and the curated ballots.
- `POST /api/delegation/delegations/validate` — the creation checks: a
  rejection, or the reference questions that would loop.
- `POST /api/delegation/judgments` — judgments for given questions and
  categories: recorded first, live Jev if a key is configured, otherwise an
  explicit unavailable result.
- `POST /api/delegation/resolve` — network, ballot, judgments, direct votes,
  threshold, method and seed in; receipts, inboxes, tallies and metrics out.

## Synthetic network (scope cut)

- One city with a few districts, a few hundred persons, some of whom live
  outside the city and can still be delegates. All seeded.
- Each person has a position per category. A question's options have
  positions too, and a person's sincere ballot is the nearest option. This
  supplies resolver ballots and the direct-voting baseline. It is a simple
  spatial model and makes no claim about real voters.
- Each person's categories are drawn from the curated pool at mixed
  granularity, so broad, narrow and nested categories all occur.
- Three delegation behaviours: none, trust a well-known person in the
  category, trust someone in your own district.
- The viewer plays one resident and edits their own delegations.

## UI plan (`/liquid`)

1. **Your delegations.** Pick a person, then pick a category from the pool or
   write your own. A rejected loop shows the chain that would have closed; a
   warning shows the reference questions that would come back to you.
2. **Run a ballot.** Choose a curated ballot for a district.
3. **Your receipt.** Per question: scores, threshold, sent or kept, chain,
   resolver, choice.
4. **Your inbox.** Questions you answer for others, including from districts
   you do not live in.
5. **Outcome.** Delegated tally next to the direct tally, with concentration.
6. **Try a question.** Free-text question judged live; disabled without a key.

## Build sequence

1. **Core.** `delegation/` types, routing rule, creation checks, resolution,
   vote-copy tally, metrics, invariants. Judgments come from fixtures. No
   network calls. *Done.*
2. **Jev judgments.** Adapter, pinned model, recorded-judgment store, failing
   closed, category pool, labelled set, router evaluation including the
   nested-pair test. Needs `TYPESAFE_API_KEY`. The
   first paid run needs explicit approval; expected spend is well under a
   dollar.
3. **Network and API.** Synthetic network, curated ballots with recorded
   judgments, the four endpoints.
4. **UI.** The `/liquid` page.

## Reproducibility

- **Pinned model.** Always `jev-1.14.0`, never `jev-latest`. The versioned id
  returned in each response is recorded.
- **Recorded judgments.** Each (model id, state, question) is hashed and its
  first response stored, append-only. The question includes the category
  text. Judgments for the curated ballots against the curated category pool
  are committed, so that part of the public demo replays without a key. A
  category the viewer writes is judged live and needs the key.
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
2. **Route name.** The placeholder and navigation use `/liquid`; CLAUDE.md
   says `/delegation`. Default: keep `/liquid` and correct CLAUDE.md.
3. **Jev access.** The launch post describes early access with a waitlist. The
   key has to be created by the repo owner.
4. **Nested categories.** Whether highest score lets a narrow category beat
   the broad one it sits inside. Settled by the build step 2 test; see Piece 1.

## Follow-ups outside this doc

When the first demo 5 change lands, CLAUDE.md's demo 5 section needs these
corrections: the route name, voter-written categories in place of the
`domain`/`program` taxonomy, vote copying in place of "weighted ballots with
minor adapter code", the cycle rule, the answered scoping questions, and a
reproducibility line for recorded Jev judgments.

## Deferred

- Database tables (`delegation_*`) and saved networks.
- A precedence rule for nested categories, only if the build step 2 test
  calls for it.
- Ranked backup delegates, split delegation, weight caps.
- OpenAI Decisions and open-weight models as further comparison arms.
- Delegate recommendations from demo 2's preference posterior.

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
