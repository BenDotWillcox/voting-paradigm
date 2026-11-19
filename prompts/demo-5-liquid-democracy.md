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

## Research protocol (decided 2026-11-16)

The study tests one hypothesis. Everything else is a reference point, an
explanation, a robustness sweep, a reported secondary outcome, or out of
scope. This section is fixed before the benchmark is run; a change to it is
dated and justified here, never made after looking at evaluation results.

### Hypothesis

> **H1 (restated as a threshold, amendment A6, 2026-11-18).** At
> comparably low civic overhead, there is a level of citizen turnout above
> which liquid delegation, with delegates chosen per category from public
> vote history, represents voters more faithfully than single-member
> district representation elected by plurality. The study estimates that
> level.

How much people would take part in an app-based liquid democracy is not
known. A yes/no verdict at an assumed turnout would stand or fall with that
assumption, so the study instead estimates where the answer changes. A
reader can then compare the threshold with the turnout they expect. Real
turnout enters only as a reference marker on the curve: the Swiss mean per
federal vote, about 0.45, from a direct democracy where voting is already
low-cost (postal voting is the norm, and adding internet voting did not
raise turnout; Germann and Serdült 2017).

- **What H1 can and cannot license.** The finding is a level, with its
  uncertainty, in the specified simulated population under the stated
  record assumptions: "liquid represents voters more faithfully once mean
  turnout reaches X". It is not a forecast that any real system would reach
  X. It does not by itself say why liquid wins above X: choosing one's own
  resolver, broader choice, topic specialisation and resolver attendance
  can each produce a win (with two disciplined blocs, one well-chosen
  personal proxy beats a shared representative by forty points and topic
  delegates add nothing). The decomposition below is declared so the
  result can be attributed.
- **The turnout dial.** One dial moves everyone's participation: each
  resident's own rate is logistic(location + 2.81·z). Here z ~ N(0, 1) is
  fixed per resident, and the location is set so that the mean rate is the
  dial's value. Turning it shifts everyone's log-odds of voting by the same
  amount, so the same residents stay ranked the same and each city keeps
  its residents, questions and turnout draws at every level.
  - Delegates vote at their own rate (no floor).
  - Office holders vote at *exactly* the measured office-holder rate of
    0.96, whatever their own rate, so the comparator is the same at every
    level. This means the representative, and the three candidates in the
    matched arms. (Revised 2026-11-19, third A6 review: a 0.96 floor would
    have let keen representatives vote more often at high turnout.)
  - The spread 2.81 is calibrated to one register statistic under this
    model (see amendment A6).
  - The dial's levels are 0.1, 0.2, 0.3, 0.4, 0.45 (the Swiss marker),
    0.5, 0.6, 0.7, 0.8 and 0.9 (`protocol.TURNOUT_GRID`).
  - `compare` runs under this condition by default (`DIAL_TURNOUT`).
- **Primary outcome.** For each city and level, liquid fidelity minus
  representative fidelity (each the mean over voters and evaluation
  questions). The independent unit is the city seed, and each city
  contributes a whole curve over the dial.
- **The threshold (revised 2026-11-19, third A6 review).** It is the
  lowest level from which liquid is *strictly* ahead at that level and
  every level above it (`protocol.read_curve`). A tie is not a lead: an
  all-zero curve is *no crossing*.
  - The runner passes *signed match counts*: liquid's matching ballots
    minus the representative's, over the same voter-question pairs.
  - It also passes the number of pairs per city (voters times evaluation
    questions; it changes in the district-count sweep).
  - Signs, and so ties, are decided exactly on the counts. Means,
    intervals and the band are in fidelity units, so 800 extra matches
    among 500 × 160 pairs reads as one point, not 800 (fourth A6 review).
- **Two curves, the later threshold.** The threshold is read on two
  curves, and the claimed threshold is the later of the two:
  - every city;
  - the cities meeting the overhead cap at each level.

  Cities over the cap therefore cannot carry it. In the reviewer's case,
  ten over-cap cities gaining ten points made the all-city curve cross
  while every compliant city lost, and that is now *no crossing*.
  - When both curves cross in the same bracket, the later of their two
    interpolations is reported.
  - A level where no city meets the cap is *unobserved* on the
    cap-meeting curve and cannot be claimed (revised 2026-11-19, fourth
    A6 review):
    - if the bracket's lower level is unobserved, no interpolation is
      reported, only the bracket and the first level where the lead is
      observed;
    - if the top level is unobserved, the verdict is *overhead condition
      not met at the top of the range*, not a crossing or a no-crossing.
- **Reported:**
  - the grid bracket, the first level where the lead is observed, and a
    linear interpolation inside the bracket, labelled a grid approximation;
  - a **nominal 95% confidence set** on the grid: the threshold lies
    above one grid level and at or below another, either end possibly
    beyond the range. Its coverage is approximate, not guaranteed in finite
    samples; see "The limit" below;
  - both curves' own readings;
  - the 95% t-interval of the difference at every level.
- **How the confidence set is built.** It comes from one *simultaneous*
  band over both curves and all levels (`protocol.threshold`):
  - the band uses a bootstrap critical value for the maximum studentized
    deviation, resampling 2,000 sets of whole cities with their cap flags,
    seeded;
  - its earliest end is the first level from which a curve inside the band
    could lead; its latest end is the first level from which every curve
    inside the band must lead.

  Whenever both true curves lie inside the band, the true threshold lies
  inside the set, plateaus included.
  - **Bootstrap-t, on counts.** Each resample is studentized by its *own*
    standard error, as the rule declares. Every mean is computed from
    signed-count totals and divided once, so an exact tie in counts stays
    exactly zero through the band. (Revised 2026-11-19, fifth A6 review.
    Studentizing by the original sample's spread, and summing fidelities
    that had already been divided, each produced sets that excluded a
    correct *no crossing*.)
  - **Sparse outcomes.** A resample whose mean moved while its own spread
    is zero counts as an infinite deviation, not zero, as does a level
    observed in the data but missing from the resample. Rare large
    outcomes therefore widen the band rather than vanish from it. Only a
    deterministic 0/0, mean unchanged and no spread, counts as zero.
    Whether the mean moved is decided exactly on count totals, so rounding
    cannot fake a move. (Seventh A6 review: a mean of exactly 4 summed to
    3.9999999999999996 and made unmoved resamples infinite.)
  - **Both curves are ratios of exact totals.** Each curve is a city
    total of signed counts divided once by a city count:
    - the all-city curve divides by every city;
    - the cap-meeting curve divides the compliant cities' total by their
      number.

    This is the same quantity at every sweep point as in the primary, so a
    compliant city never counts for more because its topic lost others to
    the cap. An exact tie stays exactly zero. (Revised 2026-11-19, seventh
    A6 review: reweighting topics after cap filtering had let 47 compliant
    cities that lost 90 matches in total show a lead.)
  - **Standard errors at the balanced sweep points.** The rotating-agenda
    sweep points fix six cities per heavy topic, so standard errors there
    use variance *within* each topic, in the sample and in every resample.
    Pooling the spread between topic means is wrong for a design that fixes
    them; it held coverage on the reviewer's example to at most 84% (sixth
    A6 review). The cap-meeting curve's error is the stratified ratio
    estimator's, from each city's residual: its cap flag times its count's
    distance from the ratio. A topic whose residuals are all identical has
    exactly zero variance, set explicitly rather than left to floating-point
    centring, which can return about 1e-17 and hide a moved mean from the
    exact check (eighth A6 review).
  - **A lone city.** A stratum, or the whole cap-meeting curve, with a
    single city at a level has an *undefined* spread, not a zero or an
    infinite one. A moved mean there counts as an infinite deviation, and
    an undefined spread in the data leaves the band unbounded at that
    level.
  - **The limit.** The set is a *nominal* 95% set with approximate
    coverage. The checks below were run on designed cases; they are not a
    guarantee:
    - A rare outcome that does not appear in the sample cannot be
      recovered by any resampling method. That holds whether or not the
      ordinary outcomes in the sample vary. In the reviewer's example a
      0.5% chance of a large loss is missed by a third of 200-city samples,
      which still vary in their ordinary counts.
    - `zero_spread_levels` flags only the degenerate case where every city
      at a level has the same count. Its absence is no reassurance about
      unseen tails.
    - The study reports the set as nominal and makes no finite-sample
      coverage claim.
  - **Coverage.** The set replaces the earlier percentile interval of the
    interpolated crossing:

    | Case | Old interval | Set (current code, 2026-11-19) |
    |---|---|---|
    | A plateau at zero | 122 of 250 runs | 149 of 150 |
    | A clean crossing | — | 150 of 150, usually a single grid step |
    | The same clean crossing with 4% of city-levels over the cap | — | 150 of 150 |
    | The reviewer's sparse example: a true mean of zero carried by a rare loss of 196 matches at probability 3/199 | about 80% | 280 of 300 |
    | The reviewer's balanced-sweep example: 48 cities, topics offset ±1,000, a loss of 60 with probability 1/15 at the top | at most 84% | 288 of 300 |

    The remaining misses are samples in which the rare loss never appears.
- **Statuses.** The status is one of:
  - *crosses*;
  - *liquid ahead throughout* (strictly ahead at every level);
  - *no crossing in the tested range*.

  A curve that changes between leading and not leading more than once
  *reverses*. Both curves' reversals are reported. *(curve reverses)* is
  appended to whatever the verdict is, *no crossing* included, if either
  curve reverses, including a cap-meeting curve that reverses while the
  all-city curve does not. Raising turnout only adds
  ballots but also changes records and so delegations, so a single
  crossing is likely but not guaranteed.
- **The overhead gate.** The 10% cap applies per city and level. The
  threshold claim requires the cap to hold, in at least 95% of cities, at
  every level from the bracket's upper end upward, where liquid is claimed
  ahead. If it fails there, the verdict is *overhead condition not met
  where liquid is ahead*: the curve is reported, but no threshold is
  claimed at comparably low overhead. Levels below the crossing may fail the
  cap; that is reported and changes nothing. With no crossing there is no
  claimed level, so the verdict stays *no crossing in the tested range*,
  and feasibility is reported beside it. The full rule is
  `protocol.threshold` and `protocol.threshold_verdict`.
- **Cities.** A fixed 200 primary cities, each run at every level, so
  nothing stops on the data. Stein's two-stage rule, declared on
  2026-11-18 for the earlier single-difference H1, is withdrawn with that
  H1. More cities buy precision about this generator; uncertainty about
  records and future agendas is carried by the sweeps.
- **Reading at one level of the dial.** At any level, and always at the
  Swiss marker, the difference is also labelled with the rules declared for
  the earlier H1 (revised 2026-11-17 and 2026-11-18, kept as secondary
  readings):
  - *Direction*, from the all-city 95% interval: *supported* when wholly
    above zero, *evidence against* when wholly below, otherwise
    *inconclusive about the sign*. It stands only when the interval over
    cities meeting the cap agrees; any disagreement, opposite signs
    included, is inconclusive. The latter is an ordinary t-interval over
    those cities, with approximate coverage.
  - *Size*, against δ = 0.02 (two fidelity points, about three more
    matching ballots per voter per 160 evaluation questions):
    - *gain of at least δ established* (lower end at least δ);
    - *gain below δ established* (upper end below δ);
    - *estimate at least δ, size unresolved* or *estimate below δ, size
      unresolved*, when the interval still contains δ.

    A size is claimed only when the all-city and cap-meeting labels agree.
  - Gate: neither reading applies unless at least 95% of cities meet the
    cap at that level (`protocol.h1_verdict`, `protocol.h1_size_verdict`).
- **Primary seeds (pinned 2026-11-18, third review).** The primary city at
  position i has seed 1,000,000,000 + i (`protocol.primary_city_seeds`),
  positions 1 to 200. Development used:
  - seeds 1 to 3 (inspected pilot cities);
  - seeds 4 and 5 (history diagnostics);
  - the configuration defaults 20261114 and 20261116;
  - small test-fixture seeds.

  None of these lies in the primary range, which a test checks. Anyone can
  replay the run from the sequence.
- **Comparably low overhead.** At every level of the dial, liquid's
  evaluation overhead is at most 10% of questions decided by the voter
  themself. The proxy is held to the same
  bound so the two are compared at matched overhead. Overhead is counted
  the same way everywhere: a person decides a question when they resolve
  their own vote or anyone else's vote depends on their ballot, an elected
  resident included (the representative's overhead is then about 1% with
  districts of 100). In liquid, the proxy and every arm but one, anyone
  holding others' votes also resolves their own, so this is the share of
  questions voters keep; the exception is a candidate in the
  election-voters arm who decides for followers while their own vote goes
  to the winner (revised 2026-11-18, third review).
- **Fixing the configuration without evaluation data** (`compare`, the
  protocol's entry point, through `acceptance_for_overhead`; rewritten
  2026-11-17 after the review found a bug). The acceptance level is the
  highest at which overhead on the *history* questions is at most 10%. All
  distinct levels at which any delegation changes are checked (a voter
  delegates a topic exactly when their best candidate's lower bound reaches
  the level, so changes happen only at those bounds); there is no early
  exit or bisection, because overhead need not fall steadily as the level
  falls: a stricter level can break a mutual pair that the loop rule would
  otherwise leave both deciding for themselves. The resolver used is an
  exact per-topic resolution checked against `graph.resolve_question` at
  the level of each voter's final resolver.
- **Infeasible cities.** A city where no acceptance level reaches 10% at a
  dial level is included there at its lowest-overhead acceptance, flagged,
  and counted in the report. Cities are never dropped from the curve; how
  many miss the cap at each level feeds the overhead gate and the
  cap-meeting curve above. At low turnout this is expected:
  - a resident with **no recorded ballot at all** keeps every question,
    because every candidate would tie on the prior alone (revised
    2026-11-19; before, the seeded tie-break could hand them a delegate by
    lottery);
  - at the primary history length, about 23% of residents have no record
    at dial 0.1, and 2.1% at the Swiss marker (35% and 4.9% with attendance
    clustered by ballot days of three).
- **The cap on a changing agenda.** With the same topic mix in history and
  evaluation and exact routing, evaluation overhead equals history overhead
  by construction, so the 10% check alone tests nothing. An uneven
  evaluation agenda (`BeliefCityConfig.evaluation_topic_weights`) is
  therefore a declared sweep, and realised evaluation overhead is reported
  for every run.
- **Primary population.** One belief model, fitted to measured data (see
  "Population model"): `delegation/data/beliefs_ces2024_v2.json`, drawn by
  `delegation/comparison/beliefs.py`, with turnout on the dial. It is a
  measurement choice, not a hypothesis; the one-factor model in
  `population.py` is the structural robustness sweep.
- **Fixed for the primary run, declared before it:** binary questions;
  three candidates per district and sincere voting; exact routing;
  delegates chosen once from a history of declared length; turnout on the
  dial, with delegates at their own rate and the representative at the
  office-holder rate (amendment A6, which moves A1's floors to the
  frontier); 200 primary cities;
  ties between equally ranked candidates broken by a seeded random key per
  voter and candidate (`choice.tie_key`), never by row order (revised
  2026-11-18: rows are grouped by district, so breaking ties by index sent
  tied choices to the first district).
- **Scope of the overhead claim.** The 10% describes ongoing operation once
  a public record exists. Building that record is not free: counting the
  history period, where everyone decides every question directly, a system
  starting from scratch has lifecycle overhead of about 71% to 74% over
  history and evaluation together. Lifecycle overhead is reported beside
  the headline, and the walkthrough says where such records would come
  from.

### Decomposition (declared 2026-11-17, participation step added 2026-11-18)

Each contrast is a paired city difference with its interval, at every
level of the dial and tabulated at the Swiss marker and at the threshold's
bracket. They explain H1; none is a second hypothesis. The
chain representative-by-record → own-of-three among election voters →
own-of-three for everyone → proxy → liquid has four contrasts that sum
exactly to liquid minus representative-by-record; H1's difference is that
sum minus "platform against record". Three steps change one thing each;
the city-wide proxy step changes several at once and is reported as a
combined effect (third review, 2026-11-18).

| Contrast | Arms (`compare` names) | What changes |
|---|---|---|
| Cost of sharing | `district_choice_voters` minus `representative_by_record` | The same three district candidates, records, turnout and participants. Residents who vote in the record election either share its winner or each assign their ballot to their own preferred one of the three; residents who do not vote get the winner in both. Only sharing changes. |
| Choice by non-voters | `district_choice` minus `district_choice_voters` | Residents who would not vote in the election also choose their own one of the three, instead of receiving the winner. (The second review found the earlier pair mixed this into the cost of sharing: the election counted only voters while own-of-three counted everyone.) |
| Platform against record | `representative` minus `representative_by_record` | How the shared representative is chosen: closest latent platform, or residents' record-based preference. Both elections use the same tie-break draw per district, so identical ballots cannot produce different winners. |
| City-wide proxy, combined | `proxy` minus `district_choice` | Several things at once: a pool of 499 residents city-wide instead of three local candidates; onward delegation (proxies follow their own proxies); keeping by acceptance threshold instead of always assigning; and resolvers voting at their own rate (on the dial) instead of the office-holder rate. It is reported as their combined effect and says nothing about how much a wider pool alone buys; no matched arm isolates pool size, because no claim rests on it. |
| Topic specialisation | `liquid` minus `proxy` | Eight topic delegates instead of one, both at matched overhead of at most 10%. |

**Overhead condition for topic specialisation (revised 2026-11-18, third
review).** The contrast is paired by city, so its claim needs comparable
overhead within the same cities. It is assessed only if both arms meet the
10% cap together in at least 95% of cities, the per-city intersection
(`protocol.joint_share`); gating each arm separately would let both pass
at 19 of 20 while only 18 cities meet both caps. The two marginal rates
are reported beside the joint one. Otherwise the contrast is *not
assessable at matched overhead*, and both arms' realised overheads are
reported beside the difference. The interval over cities where both arms
meet the cap is reported beside the all-city one, and, as for H1, a
direction or a practical size stands only when the two intervals agree
(`protocol.specialisation_verdict`).

**Margin for topic specialisation.** Maintaining eight delegations is worth
it if liquid beats the proxy by at least Δ = 0.02. Declared before the
contrast is seen; direction and practical size are reported separately
(revised 2026-11-18, because the earlier categories overlapped: an
interval from −0.015 to −0.005 was both "practically equivalent" and
"proxy better"):
- *Direction:* liquid better (interval wholly above zero), proxy better
  (wholly below zero), or sign inconclusive.
- *Practical size:* *worthwhile* when the lower end is at least +Δ;
  *proxy materially better* when the upper end is at most −Δ; *practically
  equivalent* when the interval lies wholly within (−Δ, +Δ); otherwise
  *size unresolved*. Labelled for all cities and for cities where both
  arms meet the cap; the verdict is the shared label, or *size
  unresolved* when they differ.

A noisy difference near zero is not equivalence.

### Reporting (declared 2026-11-17)

For every arrangement, at every level of the dial:
- **Three shares that sum to one:** matching ballot, contrary ballot and no
  ballot. Fidelity is the first. A voter below one half because nobody
  voted for them has had a different experience from one whose resolver
  voted against them, so the per-voter distribution splits voters below
  one half the same way.
- **Where a difference arises (revised 2026-11-18):** the H1 difference
  (liquid minus representative) and the specialisation difference (liquid
  minus proxy) are split over the same voter-question pairs, both arms
  scored on each: the pairs liquid's voters kept, and the rest. Weighted by
  liquid's kept share the two parts sum to the difference
  (`compare(...).attributions`), so the up-to-10% of kept decisions cannot
  carry the result unseen. Each arm's own fidelity on its kept and
  resolved pairs is still reported, descriptively; those conditions differ
  between arms, so they do not attribute a difference.
- **Loops:** the share of votes whose owner delegated but decides for
  themself because the chain loops, and loops per question (liquid and the
  proxy). A loop member and a voluntary keeper have the same resolver, so
  loop membership is recorded during resolution.
- **Resolver attendance:** the share of questions on which a person holding
  others' votes actually voted, read from their own cast ballot (revised
  2026-11-18: reading it from their own counted ballot was wrong when
  someone else supplies that ballot, as for a candidate whose own vote
  goes to the election winner).
- **Overhead, lifecycle overhead and delegations maintained.**
- **Light and empty records (amendment A6).** These are reported as two
  rows, each with its share and its fidelity, so the averages cannot hide
  either:
  - *Light records:* residents who cast fewer than 10% of the history
    questions themselves can barely rank candidates.
  - *Empty records:* the subset with no recorded ballot at all keep
    everything. The light-record row pools them with residents holding a
    few ballots, who can delegate on wide intervals if the calibrated
    level is low enough, so they are reported separately too.

### Robustness sweeps (declared 2026-11-18)

Declared before any primary city was simulated, and implemented as data in
`delegation/comparison/sweeps.py` (tested in
`delegation/tests/test_sweeps.py`). Each point changes one family from the
primary settings. The stress case is the one declared combination. Under
amendment A6 every point is run across the whole turnout dial, and what a
sweep shows is how the threshold moves.

- **Cities (revised 2026-11-18, sweep review).** Each point runs on
  positions 1 to 48 of the primary seed sequence: six complete rotations of
  the eight topics, so a rotating heavy topic is heavy in exactly six
  cities each and the plain mean weights every topic equally. (Fifty
  cities would have weighted two topics 7/50 and the rest 6/50.) The
  primary configuration's first 48 cities give the matching reference.
  The count is fixed in advance, which
  removes optional stopping. The 95% t-interval's coverage is still
  approximate (normal theory), and at the rotating-agenda points it ignores
  the design's stratification by heavy topic, which makes it conservative.
- **What a shared position holds fixed.** A shared seed position indexes
  the Monte Carlo comparison; what it holds fixed depends on the family:
  - *history:* the same residents and the same evaluation questions; only
    the record changes;
  - *within-topic spread, evaluation mix, stress:* the same residents, with
    new questions drawn;
  - *turnout spread:* the same residents' positions and questions, with
    turnout rates drawn on a different spread;
  - *districts:* different districts are sampled for each count (seed 1's
    2-, 5- and 10-district cities share none), so these points compare
    generated cities, not one geography with more districts;
  - *belief structure:* a different generator, with its own residents,
    districts, questions and turnout draws. Its points are compared with
    its own CES-matched 0.87 point, and the gap between that point and the
    fitted primary is reported as a comparison between generators.

  The arrangement contrasts inside each city, liquid against the
  representative and so on, are always paired, and each city keeps its
  residents across the dial.
- **Turnout.** Every point is run at every level of the dial, with
  delegates at their own rate and the representative at the office-holder
  rate, as in the primary.
- **Calibration.** Liquid and the proxy are fixed by the 10% overhead rule
  at every point, exactly as in the primary run.
- **What is reported.** At each point:
  - the threshold, its bracket, confidence set and status, computed exactly
    as for the primary (`protocol.threshold`) on the point's 48 cities;
    at the rotating-agenda points (both evaluation mixes and the stress
    case), the bootstrap resamples six cities within each heavy topic, and
    both curves are studentized by within-topic variance, keeping the
    balanced design (`SweepPoint.strata`). The curves themselves are the
    primary's: all cities, and the compliant cities' total over their
    number;
  - the difference curve with its pointwise intervals, and the
    specialisation contrast along the dial;
  - the share of cities meeting the cap at each level, and the joint share
    for specialisation.

  Sweeps say where H1 holds. They are curves, not hypothesis tests, so no
  multiplicity correction is made and no sweep result is stated as a
  finding about H1.

| Family | Values (primary in bold) | Population | Grounding |
|---|---|---|---|
| History per topic | 10, 20, **50**, 100 | fitted | Amendment A4: one Congress is 54 to 90 contested roll calls per topic; 10 and 20 are sparse records, 100 about two Congresses |
| Districts (100 residents each) | 2, **5**, 10 | fitted | Liquid's candidate pool is then 199, 499 or 999 residents, while each district's representative still serves 100. The cities differ between counts (see above) |
| Within-topic spread of new questions | ×0.5, **×1**, ×1.5 | fitted | A declared sensitivity range, half to one and a half times the fitted spread, not derived from a diagnostic (revised 2026-11-18: an earlier claim that ×2 erases topics was wrong). The fitted spread matched CES 2022's within-topic correlation (0.523 against 0.528). Descriptively, equal-weight median \|r\| within / between topics under the fitted covariance is 0.538 / 0.422 at ×0.5, 0.449 / 0.353 at ×1, 0.382 / 0.321 at ×1.5 and 0.364 / 0.324 at ×2 |
| Evaluation topic mix (history even) | **even**, one topic 2× heavier, one topic 4× heavier | fitted | 4× is a stated stress value, not measured (Voteview's roll-call files carry no topic codes); 2× is the milder point. The heavy topic rotates with city position, so each topic is heavy in exactly 6 of the 48 cities |
| Spread of engagement (logit SD of turnout rates) | 1.0, 2.07, **2.81**, 3.5 | fitted | Amendment A6. 2.81 is calibrated to Geneva's ten-ballot table (Sciarini et al. 2016, Table 1: 20.2% never and 15.9% always at mean 0.493; the model gives 18.6% and 17.6%). 2.07 fits only the never-voter figure of a 20-ballot report; 3.5 is more polarized, as on online platforms where activity is power-law distributed; 1.0 is a fairly even electorate in which nearly everyone votes sometimes |
| Attendance clustering | **a fresh draw per question**, one draw per ballot day of three questions | fitted | The register counts ballot days, often several measures each (the Swiss average is about 2.8); the model counts questions. Clustering three consecutive questions per draw tests that transfer, at the same mean turnout |
| Belief structure: cross-topic correlation of positions | 0, 0.4, 0.87 (CES-matched), 0.95 | structural | 0.87 matches the fitted population's between-topic item correlation (0.379, the same on both). The fitted topic directions alone correlate at a median of 0.77, and one axis carries 82% of their variance |
| Belief structure: blocks of related issues | two blocks of four topics, 0.87 within, 0.2 across | structural | A less sorted public (Baldassarri and Gelman 2008): as cohesive as the CES within each block, weakly related across. It differs from the CES-matched point only across blocks |
| Stress case | 10 per topic; one history topic 4× heavier and a different one (four topics on) 4× heavier in evaluation | fitted | Declared 2026-11-17: sparse records and a shifting agenda plausibly occur together. Its third element, ordinary delegate turnout, is now the dial's condition everywhere |

**The structural population.** For the belief-structure family the fitted
model is replaced by the one-factor model of `population.py`, extended
with an optional block factor. It has eight dimensions standing for the
eight topics, 50 history and 20 evaluation questions per dimension, five
districts of 100 residents and three candidates per district. Its other
parameters are matched to the fitted population on the same simulated
summaries, so cross-topic structure is the main thing that differs:

| Parameter | Value | Summary matched (structural against fitted) |
|---|---|---|
| District lean SD | 0.26 | District SD of support: 0.065 against 0.067 |
| Cutpoint SD | 1.15 | Item support-rate SD: 0.232 against 0.235 |
| Preference noise SD | 1.11 | Within-topic median \|r\|: 0.464 against 0.458 |

The noise stands in for the fitted model's within-topic spread of
questions, but it is unstructured: in the fitted model two questions in a
topic can differ systematically, and here they differ only by noise. That
limit is stated with the curve. The 0.87 point is the structural curve's
own reference: the other structural points are read against it, within
one generator. Its gap from the fitted primary is a comparison between
generators, reported first, because a large gap means the structural
curve says little about the primary population.

**Figure 2, the attendance frontier (amendment A6, replacing the single
break-even of A2; criterion aligned with H1, 2026-11-19).** On the 200
primary cities, at every level of the dial, the lowest delegate attendance
floor from which liquid *strictly leads* the representative.
- **The criterion** is H1's: a strict lead decided on signed counts, on
  both the all-city and the cap-meeting curve, the later taken
  (`protocol.frontier_reading`). Ties at every floor therefore give *no
  lead*, not floor 0.
- **Rates:** a delegate votes at the larger of their own rate and the
  floor; office holders stay at exactly the office-holder rate.
- **How it differs from H1.** It is a separate figure, not a restatement
  of H1. Its result at each level is a floor; H1 is Figure 1, the
  threshold on the dial. H1 additionally requires the lead to be
  sustained at every higher level and the overhead gate to hold.
- **Floors:** 0 (delegates at their own rate, the dial's condition), 0.2,
  0.4, 0.6, 0.8, 0.9, 0.96 and 1.0 (`sweeps.FRONTIER_FLOORS`). Own rates
  now run down to about 0, so every floor changes some ballots and the
  grid starts at 0. (A2's earlier grid started at the 0.30 plateau of the
  retired uniform turnout.)
- **Why there is one crossing:** raising the floor only adds ballots and
  leaves delegations, and so the cap flags, unchanged. At each level both
  curves therefore never fall, and the first lead is sustained.
- **What is reported, per level:**
  - the grid bracket where liquid first leads on both curves;
  - the later of the two curves' interpolations inside it, labelled a grid
    approximation;
  - the 95% t-interval of the difference at every floor.

  No interval is claimed for a crossing itself. The status is one of:
  - *leads at the lowest floor*, with delegates at their own rate;
  - *crosses*;
  - *no lead in the tested range*;
  - *no city meets the cap at this level*.
- **How to read it:** for each level of citizen turnout, Figure 2 shows how
  reliably delegates must vote for liquid to lead representation.
  - A lead with delegates at their own rate is the status *leads at the
    lowest floor*, not an interpolated point near 0. A bracket starting at
    0 with an interpolation of exactly 0 marks a tie at floor 0, where the
    lead only begins above it, and is drawn as such.
  - Where the status is *leads at the lowest floor* at a level and every
    level above it, with the gate holding, Figure 1's threshold has been
    crossed.

### Running the benchmark (runner built 2026-11-19)

`delegation/comparison/runner.py` simulates the declared cities and reads
every verdict with `protocol.py`. The script is
`scripts/run_liquid_benchmark.py`, tested in
`delegation/tests/test_runner.py`. Three runs:

- **`smoke`:** eight small cities on development seeds (3,000,001 onward,
  never the primary namespace), fitted and structural, at three levels, in
  a few seconds. It checks the pipeline end to end. Cities this small
  cannot keep overhead under 10%, so their reading is uninformative by
  design.
- **`primary`:** the 200 primary cities, each at every level of the dial,
  with the attendance frontier recounted at every floor from the same
  calibration and delegations.
- **`sweeps`:** every declared sweep point on its 48 cities at every level.
  `--point` runs one point.

Each run works as follows:
- **One city per task.** A city's levels run in one task, so the city
  keeps its residents across the dial.
- **What a city-level records:**
  - every arrangement's matching-ballot count, so contrasts are signed
    counts and ties are exact;
  - the voter-question pairs;
  - whether liquid and the proxy meet the overhead cap;
  - the calibration;
  - every arrangement's measures;
  - for primary cities, liquid's matches minus the representative's at each
    frontier floor.
- **Checkpoints.** Each city's record is appended to `records.jsonl` and
  synced to disk, so an interrupted run resumes where it stopped.
- **The manifest** records:
  - the commit and whether the checkout was dirty;
  - the beliefs file's hash;
  - the protocol constants and the sweep definitions;
  - the Python and NumPy versions.

  A primary or sweep run refuses a checkout with uncommitted changes, and a
  resumed run must match its manifest.
- **The analysis** (`analyse`) writes two files:
  - `report.json`, with every reading per point: the threshold verdict,
    bracket, interpolation, first supported level, nominal 95% set, both
    curves and the gate; the reading at each level and at the Swiss marker;
    the specialisation contrast with its joint share; the decomposition; the
    frontier; and the averaged measures;
  - `report.md`, with the headline line for each point.

  Rotating-agenda points use their heavy-topic strata.
- **Speed.** Agreement is computed once per city level and reused by the
  calibration, the choice and the matched arms (`arrangements._AGREEMENTS`,
  a weak cache; results are unchanged, and the test suite passes as
  before). That brings a full-size city level to about 18 s, from about
  41 s. On 14 workers the primary run takes about 45 minutes and the sweeps
  about 3½–4 hours; the 10-district point costs about four times a
  five-district one.
- **Where results go.** Runs write to `.cache/liquid-benchmark/<run>/`,
  which is Git-ignored. The published benchmark is built from them in step
  6 below.

### What everything else is

| Question | Role |
|---|---|
| Full turnout; direct at real turnout | Reference points on the headline figure, no claim |
| Dilution against bundling (the matched three-candidate arms and the personal proxy) | Explanation of why H1 holds or fails, through the declared decomposition and the topic-specialisation margin above (revised 2026-11-17: the proxy step alone changed candidate pool, selection rule, election and onward delegation at once) |
| Belief structure (correlation across issues, blocks of related issues) | Robustness sweep: where H1 holds, not which structure is true (values in "Robustness sweeps") |
| History length, number of districts, within-topic spread, evaluation topic mix | Robustness sweeps, few values, one family at a time from the primary settings (values in "Robustness sweeps") |
| Stress case: sparse records (10 history questions per topic), an uneven agenda (one topic four times as heavy as each other, in history and a different one, four topics on, in evaluation) and ordinary delegate turnout, together | Declared robustness point (2026-11-17; topics fixed 2026-11-18): these plausibly occur together, and one-at-a-time sweeps miss how they interact |
| Outcome agreement with full turnout, concentration, lost votes, loops | Secondary outcomes, reported, no hypothesis |
| Ordinary resolver turnout (delegates vote like anyone else) | The dial's condition for H1 (amendment A6). The symmetric 0.96 floor of A1 is one row of the frontier |
| Frontier: delegate attendance needed at each turnout level | The main figure (amendment A6, replacing A2's single break-even): at every level of the dial, the attendance floor at which liquid matches the representative (see "Robustness sweeps") |
| Turnout at a real direct democracy | Reference marker on the dial, not an assumption: the Swiss mean per federal vote, about 0.45 |
| Per-voter fidelity distribution | Secondary outcome (A5): share of voters below 0.5 and the 10th percentile, with voters below 0.5 split by no ballot against contrary ballot |
| Three shares, the paired kept/resolved attribution, loops, resolver attendance, lifecycle overhead | Reported for every arrangement, the attribution for H1 and for specialisation (see "Reporting") |
| Onward-delegation limits, backup delegates, other ballot types, the account app | Out of scope: design variants, not this test |
| Whether party competition produces left-right correlation | Out of scope: a causal claim about real politics and a study of its own. A low-correlation point on the robustness sweep covers "what if beliefs were less sorted" without asserting why |
| Router error (Jev) | Out of scope for H1; it has its own evaluation. A follow-up may test H1 under measured routing error |
| Free-text categories at any granularity | Out of scope for H1, which delegates at the level of the eight observed topics. Shown in the account app as a design idea, not as a tested result (decided 2026-11-16). Candidate follow-up H2 below |

**Candidate follow-up, H2 (not committed).** *Does delegating at a finer
grain than topics beat topic-level delegation, given limited history?*
Under the H1 model a narrower category inside a topic is a random subset of
that topic's questions: it carries no structure of its own and has less
history, so it can only tie or lose. That is an artefact of where the model
puts structure, not a finding. Finer categories reduce bundling within a
topic and cost evidence; where that trade-off lands depends on how much
subtopics differ, which CES 2024 cannot measure (two to six items per
topic). H2 would need a question generator with explicit levels (topic,
subtopic, question) whose variance at each level is estimated from data,
for example by linking several CES years that share items onto one scale
(concurrent calibration), and the router back in the loop, so that a
voter's category text picks out a region of that hierarchy. Topic-level H1
is the simpler case: if finer categories help, topic-level H1 may
understate liquid; if not, voters lose nothing by using topics. Neither is
established.

### Amendments after the pilot (2026-11-16)

Made after the disclosed pilot (see "Pilot runs, disclosed" under
"Population model"), before any primary run. Each is recorded with the
pilot numbers that prompted it, so a reader can judge whether it is a
correction or a tuning.

- **What the pilot showed.** On the same three pilot cities, every voter
  delegating:

  | Fidelity | Representative | Proxy | Liquid |
  |---|---|---|---|
  | As run | 0.62–0.64 | 0.64–0.66 | 0.59–0.62 |
  | If every resolver voted | 0.62–0.64 | 0.74–0.75 | 0.71–0.72 |
  | …and 100 history questions per topic | 0.62–0.64 | 0.74–0.75 | 0.74 |

  Liquid's whole shortfall against the representative came from resolvers
  who did not vote: the representative never misses a vote, while
  delegates voted at ordinary turnout even when holding others' votes.
  With every resolver voting, liquid beat the representative by about 8
  to 9 points. Removing dilution (representative to proxy) was worth about
  11 points; removing bundling across topics (proxy to liquid) about −2
  with 20 history questions per topic and about 0 with 100. In the measured
  population, almost all of the gain comes from choosing one's own
  resolver, not from splitting by topic. Caveats: the model fits
  within-topic structure worst, and CES items are more party-sorted than
  local measures.
- **A1. Symmetric resolver turnout (primary until amendment A6; scope
  revised 2026-11-17).** Under A6 the symmetric 0.96 floor is no longer the
  primary condition but one row of the frontier; the office-holder rate
  still sets the representative's turnout.
  The office-holder rate answers how often elected officials vote, not how
  often a private citizen votes once a neighbour delegates to them; field
  evidence also separates selection (active voters receive more
  delegations) from behaviour change (delegates need not then participate
  more). Turnout is therefore a central variable of the study rather than a
  settled assumption: the ordinary-turnout condition is reported beside the
  primary with equal prominence, with the break-even (A2) and realised
  resolver attendance. Anyone who resolves votes
  for others votes at one office-holder rate, and that includes the
  representative, who no longer votes with certainty. The rate is **0.96**,
  checked against Voteview on 2026-11-16 (replacing a placeholder of 0.98):
  members of the 118th House cast a yea or nay on 96.2% of the roll calls
  held while they served (median member 97.5%, 10th percentile 91.1%). The
  117th House reached 98.0%, but under its pandemic proxy-voting rule,
  which let absent members vote through a colleague and is itself a form
  of delegation, so it is not the anchor. Computed by
  `scripts/voteview_house_rates.py` from the cached Voteview files, whose
  SHA-256 it checks. Voters who keep a topic vote at
  their own rate. The pilot's arrangement, delegates at ordinary turnout,
  is co-reported. Reason: the pilot compared a representative who never
  misses with delegates who miss as often as anyone, an asymmetry that
  favours representation and is not part of either mechanism. Kling et al.
  found the most-delegated LiquidFeedback users among the most active.
- **A2. Break-even resolver turnout (secondary; superseded by the
  frontier under amendment A6, which computes this break-even at every
  level of the dial).** Resolver turnout is
  swept from ordinary turnout up to the office-holder rate, and the rate at
  which liquid's fidelity equals the representative's is reported as a
  bracket on a declared grid, with an interval for the difference at each
  floor (revised 2026-11-18: no interval for the crossing itself; see
  "Robustness sweeps"). What matters is the turnout of people holding others' votes,
  not general turnout. If liquid's advantage depends on that rate, the
  conclusion is that liquid democracy needs reliable resolvers; notices,
  deadline reminders and backup delegates are the tools that would supply
  them, which links the study to the control center. The study shows the
  condition is necessary, not what produces it.
- **A3. Agreement borrows strength across topics.** A voter judging a
  candidate on one topic also sees that candidate's whole record. Each
  topic's Beta prior is centred on the pair's overall agreement, with its
  strength estimated from the history by marginal maximum likelihood over
  all (voter, candidate, topic) triples (a beta-binomial), so thin topic
  records lean on the whole record and long ones stand on their own. This
  replaces the uniform prior per topic. The proxy is unchanged: it already
  uses the whole record. Reason: with 20 questions per topic the
  per-topic estimate was noisy and the best-of-499 choice amplified it.
- **A4. History length justified by realism.** The primary history length
  is set from a stated account of how long a real voting record would be
  when delegates are chosen, not from the pilot. The history sweep is
  reported prominently, because the pilot showed the comparison is
  sensitive to it.

  *Decided 2026-11-16: one Congress, 50 questions per topic.* The account:
  voters choose delegates with the record a voter has before a House
  election, one two-year Congress, which puts liquid's information on the
  same footing as representation's. One Congress takes 428 (117th) to 720
  (118th) contested substantive roll calls (passage and amendment votes,
  procedural motions excluded, minority side at least 10%; Voteview, same
  script). Spread over the simulation's eight topics, which stand for the
  whole question space, that is 54 to 90 per topic. The primary value is
  the lower, rounded down to 50 (400 history questions). (An earlier
  claim that rounding down is the conservative direction for H1 is
  withdrawn, 2026-11-17: a shorter history hurts per-topic choice, but its
  net effect on liquid against the representative is not established.)
  The sweep reports 10, 20, 50 and 100 per topic. Voteview is a weak
  anchor for how much citizens know about each other: of the 720
  qualifying votes in the 118th House, 525 were amendments, on 194 distinct
  bills, so the count does not establish 50 independent observations per
  topic; the stress case below combines sparse records with an uneven
  agenda. Limit: each voter's own record is their turnout rate times this,
  so a voter at 30% turnout has about 15 trials per topic; how a voter
  would build that record before delegating is the setup overhead already
  reported separately.
- **A5. Per-voter distribution (secondary).** Averages hide the voters
  represented against their views. On the pilot cities, 42% to 46% of
  residents' preferred candidate lost; with every resolver voting, 7% to
  21% agreed with their representative less than half the time, against
  0% to 1% under the proxy and 0% under liquid (10th percentiles 0.45 to
  0.52 against 0.61 to 0.64). The share below 0.5 and the 10th percentile
  are reported for every arrangement.
- **A6. H1 as a turnout threshold, on a turnout dial grounded in register
  data (2026-11-18).** Made while writing the ODD description, when an
  audit of ungrounded parameters found that citizens' own turnout was
  uniform on [0.3, 0.9] with nothing behind it. It was not prompted by
  any outcome: no primary city had been simulated. The pilot outcomes in
  "Pilot runs, disclosed" were seen under that turnout and are recorded
  there.
  - *The evidence.*
    - Geneva's official register tracks individual participation for
      about 210,000 citizens. About 10% vote in none of 20 successive
      federal ballot days, occasional voters are two thirds to four
      fifths of the electorate, and mean turnout per vote is about 0.43
      to 0.49 (Sciarini, Cappelletti, Goldberg and Lanz 2016; Goldberg and
      Sciarini 2021). A secondary report puts always-voters near 10%; the
      paper's figures bound them at 10% to 25%.
    - People choose ballot days, not individual measures: turnout across
      one day's measures rarely differs by a point.
    - Postal voting is already the norm, and adding internet voting in
      Geneva and Zurich did not raise turnout (Germann and Serdült 2017),
      so a lower physical cost does not lift participation much.
    - On an app-based liquid democracy platform, the German Pirate Party's
      LiquidFeedback (13,836 users, 3,565 issues), the median user voted
      on 8 issues and activity was power-law distributed (Kling et al.
      2015).

    The uniform rate implied no never-voters, almost no always-voters and
    a mean of 0.60.
  - *The change.*
    - Turnout becomes a dial. Each resident's rate is
      logistic(location + 2.81·z), with z fixed per resident and the
      location set by the dial's mean.
    - The spread is calibrated to one register statistic under this
      model: Geneva's ten successive ballot days, mean participation 0.493,
      with 20.2% taking part in none and 15.9% in all (Sciarini et al.
      2016, Table 1). Least squares on those two shares gives 2.81, which
      yields 18.6% and 17.6%. A symmetric logit spread cannot match the
      small asymmetry. (Revised 2026-11-19, third A6 review: the first
      calibration, 2.07, matched a 20-ballot never-voter figure but gave
      12.5% and 11.7% on the table.)
    - The register counts ballot days and the model counts questions.
      Transferring the spread to independent questions is an assumption,
      so attendance clustered by ballot days of three is a sensitivity
      point. Spreads 1.0, 2.07 and 3.5 are a sweep family.
    - H1 is restated as the threshold on that dial (see "Hypothesis").
    - Delegates vote at their own rate on the dial, and office holders at
      exactly the office-holder rate.
    - A2's single break-even becomes the frontier.
    - The seed count becomes a fixed 200 cities, and light records are
      reported apart.
  - *Why a threshold.* How many people would take part in an app-based
    system is unknown, and the evidence above suggests no assumed value
    would be secure. A threshold makes that uncertainty the result: "liquid
    needs turnout of at least X", with real direct democracy's turnout
    marked on the curve.
  - *Uniform turnout* remains available in code (`turnout_mean=None`) so
    that development results reproduce. It is not part of the study.
- **Ruled out.** Tuning the acceptance level or the turnout values until
  liquid wins; dropping the proxy arm because it complicates the story;
  adding backup delegates to H1 (a design variant, a possible later study).

**A1 and A3 implemented (2026-11-16).**

- **A1** is `TurnoutPolicy` in `delegation/comparison/arrangements.py`.
  Whoever resolves at least one other voter's vote on a question casts
  their ballot when that question's turnout draw falls below the larger of
  their own rate and a floor: `office_rate` for the representative,
  `resolver_turnout` for delegates. `PRIMARY_TURNOUT` sets both to 0.96
  (0.98 when first implemented; see A1);
  `ORDINARY_RESOLVER_TURNOUT` sets `resolver_turnout` to 0 (co-reported);
  `PILOT_TURNOUT` reproduces the pilot. Each question set now stores its
  uniform turnout draws, so raising a floor only ever adds ballots and the
  A2 sweep is monotone by construction.
- **A3** is `pooled_agreements` in `delegation/comparison/choice.py`, used
  by liquid's delegate choice unless `ChoicePolicy.borrow_strength` is
  false. The prior for a (voter, candidate, topic) is
  Beta(s·μ, s·(1 − μ)), with μ the pair's posterior mean agreement on
  every *other* topic's history questions, so a topic's own questions are
  not counted twice, and one strength s for the population, estimated by
  maximising the beta-binomial marginal likelihood over all triples
  (searched between 0.1 and 10,000 pseudo-questions).
- **Working check, disclosed.** The same three pilot cities, every voter
  delegating:

  | Condition | Representative | Proxy | Liquid (A3) | Liquid (uniform prior) |
  |---|---|---|---|---|
  | A1 symmetric (at the placeholder 0.98, 20 history questions per topic) | 0.613–0.632 | 0.720–0.729 | 0.724–0.731 | 0.693–0.706 |
  | Ordinary resolver turnout | 0.613–0.632 | 0.638–0.664 | 0.637–0.662 | 0.589–0.618 |

  The estimated strength was 55 to 74 pseudo-questions, against 20 real
  history questions per topic: in this population a pair's agreement on
  one topic is well predicted by their agreement on the others, so thin
  topic records lean heavily on the whole record. (Revised 2026-11-17:
  this was first read as evidence that bundling across topics costs
  little. Much of the strength reflects attendance instead, because a
  candidate's absence counts as a miss on every topic; see "Pooling and
  attendance" under "Population model".)
  These runs verify the code; they are not the primary run, whose seeds
  are not yet drawn.

A global sensitivity analysis (screening, then variance-based indices, with
the seed as an input) comes after H1 is settled, not before.

### Method standards

- **Documentation.** The model is described in the ODD form (Overview,
  Design concepts, Details) before the benchmark runs, with this protocol
  as its analysis plan: [`demo-5-odd.md`](demo-5-odd.md) (written
  2026-11-18, following Grimm et al. 2020). It labels every parameter as
  measured, fitted or stated.
- **Verification.** Unit tests, invariants and analytic special cases; any
  faster reimplementation (such as a vectorised resolver for sweeps) is
  checked against `graph.resolve_question` on the same inputs.
- **Validation by patterns.** Before the primary run, the population model
  must reproduce empirical patterns declared in advance: weak issue-pair
  correlation in the mass public (Converse 1964; Baldassarri and Gelman
  2008), "moderates" who mix strongly held positions (Ahler and Broockman
  2018), and constituent agreement with their representative on real roll
  calls (Ansolabehere and Jones 2010, CES). Data used to fit the model is
  kept apart from data used to check it.
- **Randomness.** Many seeds, intervals rather than single draws, and paired
  comparisons on common random numbers.
- **Bias check.** Cross-cutting beliefs are the condition under which
  liquid wins, so the belief model gets the most scrutiny, and its primary
  form comes from data rather than from what the hypothesis needs.

## The comparison

### Arrangements

Each arrangement decides whose ballot counts for a voter on a question.

| Arrangement | Whose ballot counts for you | Dilution | Bundling |
|---|---|---|---|
| **Full turnout** (reference) | Yours, on every question, and you always vote | — | — |
| **Direct** | Yours, on every question, when you turn out | — | — |
| **District representative** | Your district's representative, elected by plurality, on every question | yes | yes |
| Representative by record (`representative_by_record`) | The same election, but residents rank the three candidates by public record, as delegates are chosen | yes | yes |
| Own of three, election voters (`district_choice_voters`) | If you vote in that election, your own preferred one of the three; otherwise its winner | partly | yes |
| Own of three, everyone (`district_choice`) | Your own preferred one of the three | no | yes |
| **Personal proxy** | One person you chose by your overall agreement, on every question | no | yes |
| **Liquid** | Per category, a person you chose by your agreement on that category; yours on everything you keep | no | no |

The personal proxy and the three-candidate arms are not real proposals.
They are the steps between representation and liquid delegation that the
declared decomposition (research protocol) uses to say why H1 holds or
fails: sharing, choice by non-voters and topic delegates each change at
exactly one step, and the step to the city-wide proxy is a combined
effect of several changes. (The first design read the gap from
representative to proxy as dilution alone; that step changed the
candidate pool, the selection rule, the election and onward delegation at
once.)

Abstention is the same everywhere: a voter whose counted ballot is empty
(their resolver did not vote) gets no match.

**Full turnout is the reference corner (decided 2026-11-16).** It scores
fidelity 1 and overhead 1 by definition and is what the claim means by
"direct democracy is preferred". Direct voting at real turnout falls below
it because a non-voter matches nothing; that shortfall is direct
democracy's overhead showing up as abstention, which is the friction
liquid democracy addresses: people skip the questions they cannot keep up
with, and liquid lets them hand those over instead. Without this corner,
direct at real turnout (about 0.60) would sit below a representative who
never misses a vote (about 0.67) and read as the worse arrangement.

### Measures

- **Fidelity** (per voter, per question): 1 if the ballot counted for the
  voter equals their sincere choice, else 0. Averaged over voters and
  questions. Full turnout scores 1; direct voting scores 1 for everyone who
  votes and 0 on a question they skip. Unweighted: every
  question counts the same, because a per-voter salience weight would be
  hard to model credibly (decided 2026-11-14).
- **Overhead** (per voter): the share of questions the voter decides
  themself. Full turnout and direct are 1, representative and proxy 0,
  liquid in between. The
  number of delegations a voter maintains is reported beside it, so liquid's
  upkeep is not hidden.
- **Outcome agreement** (per question): whether the arrangement's winner is
  the full-turnout winner, what the whole city would choose if everyone
  voted. Representatives decide a city question as a
  council majority. This is where Ostrogorski-style cases appear: a council
  elected on bundled platforms that loses the issue-by-issue majority.
- Fidelity is always measured on questions that come *after* the history the
  delegates were chosen from (see below), never on the same questions.

### The headline figures

**The threshold and the frontier (amendment A6).** The study's result is
read from two figures with separate labels:
- *Figure 1, the H1 threshold:* liquid minus representative fidelity
  against mean turnout on the dial, all-city and cap-meeting curves, with
  pointwise intervals and the simultaneous band. The threshold, its
  confidence set and the Swiss reference at 0.45 are marked. This is the
  finding.
- *Figure 2, the attendance frontier:* for each turnout level, the lowest
  delegate attendance floor from which liquid strictly leads, on the same
  two-curve criterion. It shows how far better delegate attendance could
  move Figure 1's result; it is not itself the H1 reading.

**The overhead-fidelity plane.** This is the demo's framing figure.
Overhead is on the horizontal axis and fidelity on the vertical:
- the full-turnout corner at (1, 1);
- direct at a given turnout below it;
- the district representative and the personal proxy;
- the liquid curve, traced by letting voters hand over zero, one, two and
  more of their categories, best-scoring first.

It is drawn at the Swiss marker, and the walkthrough can move it along the
dial.

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
   prior. Candidates are ranked by the lower end of an 80% credible
   interval. (Corrected 2026-11-17: an earlier "18 of 20 beats 2 of 2" did
   not describe this ranking. For one voter on one topic every candidate
   has the same number of trials, the voter's own votes, so among
   candidates the ranking follows the match count; the interval's width
   matters across voters and topics, where it decides whether the best
   candidate clears the acceptance level.)
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
- **Everyone chooses at once.** The account app's creation check refuses
  a delegation that would close a loop, which suits edits made one at a
  time. Applied voter by voter in a simulation where everyone delegates, it
  forces someone to be refused, and that person becomes the resolver of
  everyone. Delegates are therefore chosen simultaneously and loops are
  left to the resolution rule: two people who are each other's best match
  both keep the category.
- **Concentration and lost votes emerge.** Candidates who agree with many
  people and vote reliably attract delegations; ones who skip votes score
  lower because skipped votes count as misses.
- **It is also an app feature.** The same ranking is a delegate
  recommendation in the account app, with its interval shown.

### Population model

The simulation extends `delegation/simulate.py`. Every choice here is an
assumption chosen to make the comparison legible, and the main ones are
swept rather than fixed.

**Revision planned (2026-11-16).** The one-factor left-right model below is
a placeholder. A single left-right axis is largely a product of two-party
competition: voters adopt their party's positions (Lenz 2012; Barber and
Pope 2019), and issue positions have grown more correlated with party
without growing more correlated with each other (Baldassarri and Gelman
2008). The primary population will instead be fitted to measured yes/no
positions on real bills (CES roll-call items), for example with a
multidimensional item-response model whose number of dimensions is chosen
by held-out likelihood, so dimensionality and correlation are outputs of the
data. Synthetic voters and new questions are then drawn from the fit. The
robustness sweep keeps a structural model with chosen correlation,
including blocks of related issues instead of one axis. The model form is
not yet chosen.

**Data source (chosen 2026-11-16): CES 2024 Common Content.** Cooperative
Election Study Common Content, 2024 (Schaffner et al.), Harvard Dataverse
doi:10.7910/DVN/X11EP6, version 9, CC0 1.0, unrestricted files (a 184 MB
CSV, a Stata file and a guide).

- **Why it fits.** About 60,000 respondents, each answering roughly 35
  binary support/oppose items on concrete proposals, which gives the
  within-person cross-issue structure the belief model needs. The grids
  (from the guide): gun policy (`CC24_321grid`, 6 items), immigration
  (`CC24_323grid`, 4), abortion (`CC24_324grid`, 4 binary plus a
  gestational-limit item), environment (`CC24_326grid`, 6), a mixed
  housing, tax, health and student-debt grid (`CC24_328grid`), six bills
  before Congress (`CC24_340grid`) and tax and spending proposals
  (`CC24_341grid`). Respondents carry their state and congressional
  district.
- **Validation anchor.** The guide lists roll-call votes among the
  contextual data. Whether the file carries each respondent's own House
  member's vote on the `CC24_340grid` bills is unconfirmed until the CSV is
  inspected; if not, the members' votes come from Voteview. Agreement
  between respondents and their member on those bills is the empirical
  pattern the simulated representative must reproduce.
- **Fit and check on different data.** The 2024 file fits the model. A
  different year's Common Content (for example 2022), with different items
  and respondents, checks the declared patterns, so calibration and
  validation data stay apart.
- **Known limits.**
  - The items are national and chosen by the study team for being salient
    and divisive, so they are likely *more* party-sorted than typical local
    ballot measures. Which way that moves H1 is not established (claim
    withdrawn 2026-11-17): more sorting can favour a shared representative
    or make a personal match easier to find.
  - The panel is an opt-in online sample matched and weighted to the ACS;
    fits use the guide's recommended common weight (variable name to be
    confirmed in the file).
  - Positions are as measured today, party sorting included. A population
    with less sorting is a robustness point, not a claim.
- **Alternatives considered.** ANES 2024 (about 5,000 respondents, mostly
  seven-point scales: a robustness check, not the primary). Swiss VOTO
  post-vote surveys (real direct-democracy votes, but each respondent covers
  only one ballot day). smartvote (candidates and voters answer the same 75
  items, ideal for congruence, research access unconfirmed).
- **Handling.** The raw files are downloaded to a git-ignored cache, never
  committed. Only derived, aggregate model parameters and their hashes enter
  the repo, with the dataset DOI, version and file checksums recorded.

**The file as downloaded (2026-11-16).** `.cache/ces/2024/
CCES24_Common_OUTPUT_vv_topost_final.csv` (Dataverse file id 12050325),
183,679,005 bytes, MD5 `b740b9305fee50e1a34656b513f55c57` (matches
Dataverse), SHA-256 `8a5e9fbc982961ad910bad9aed8d521fa0a85e85cded43fb308cce0ab22ba5d9`.
60,000 rows, 694 columns.

- **Items.** 36 binary items, coded 1 = support and 2 = oppose, each missing
  for under 1% of respondents: `CC24_321a`-`f` (guns), `CC24_323a`-`d` and
  `CC24_323f` (immigration), `CC24_324a`-`d` (abortion), `CC24_326a`-`f`
  (environment), `CC24_328a`-`e` (housing, tax, health), `CC24_340a`-`f`
  (bills before Congress), `CC24_341a`-`d` (taxes and spending). 57,969
  respondents answered all 36. The items are forced choice with no "don't
  know", so some answers are non-attitudes in Converse's sense; the model's
  noise term has to absorb them.
- **Other columns used.** Weights `commonweight` (pre-election items) and
  `commonpostweight`; districts `cdid118`, `cdid119`; state `inputstate`;
  party identification `pid3`, `pid7`.
- **Members' votes are not in the file.** No column carries how a
  respondent's House member voted on the `CC24_340` bills, so the
  representative validation pattern takes the members' votes from Voteview,
  matched by district.
- **First look at the structure (exploratory, weighted phi correlations, not
  the model).** Mean absolute correlation between items 0.24 (90th
  percentile 0.41). The largest eigenvalue is 10.3 of 36 (29% of variance),
  against 2.2 for the next, so measured positions do have one dominant
  common dimension. Removing what party identification explains (`pid7`)
  halves the mean absolute correlation to 0.12 and drops the first
  eigenvalue's share to 15%, though it still leads (5.6 against 2.5). Phi
  understates the latent correlations, and residualising on party says
  nothing about which way causation runs. The point for the model: a
  single common dimension is a real feature of today's measured beliefs,
  about half of it aligned with party, so the fitted model must be allowed
  to find it rather than being built with or without it.

**Model form (chosen 2026-11-16): Bayesian multidimensional probit item
response model.**

- **The model.** Respondent i has a latent position θᵢ in K dimensions,
  θᵢ ~ N(0, I). Item j has a loading vector aⱼ and an intercept bⱼ. The
  respondent supports the item when aⱼ·θᵢ + bⱼ + εᵢⱼ > 0, with
  εᵢⱼ ~ N(0, 1). This is the simulation's own vote rule (a position, a
  cutpoint, an idiosyncratic term), so the fitted model is directly the
  simulation's generative model. It is compensatory and exploratory: no
  dimension is labelled left-right and none is required; correlation
  between items comes only from shared loadings the data supports.
- **Estimation (revised while building, 2026-11-16): two stages.**
  1. *Items, by limited information.* Each item's threshold from its
     support rate, each pair's tetrachoric correlation from its 2x2 table,
     and loadings from an unweighted least squares factor fit to the
     tetrachoric matrix, converted to (a, b). Consistent and fast; with
     60,000 respondents the item parameters are estimated far more
     precisely than anything downstream needs, so ignoring their
     uncertainty costs nothing measurable.
  2. *Respondents, by Gibbs sampling with the items fixed* (data
     augmentation, Albert and Chib 1992): latent utilities from truncated
     normals, θ from its normal conditional, missing and held-out answers
     imputed inside the sampler. 1,200 iterations, 200 burned, every fifth
     kept, two chains with recorded seeds. Since version 2 the positions
     are conditioned on district (hierarchical; see "Validation and two
     corrections before the freeze").

  The planned fully joint Gibbs sampler over items and respondents
  (Béguin and Glas 2001) was built and recovered known parameters, but
  mixed too slowly at this sample size: on a 15,000-respondent CES
  subsample at K = 3, 2,000 iterations left split R-hat at 1.15 on the
  implied item correlations, the known weakness of data augmentation when
  the latent positions carry most of the uncertainty. With items fixed the
  position sampler mixes adequately (on simulated data, split R-hat at most
  1.07 over 1,000 coordinates). The rotation never needs fixing, because
  the simulation only uses aⱼ·θᵢ + bⱼ and θ's prior is rotation-invariant.
- **Choosing K.** Fit K = 1 to 6 on every respondent. Hold out a seeded
  random 10% of answered cells, re-estimate items and positions without
  them, and score each held-out answer by its posterior predictive
  probability. The chosen K is the smallest whose mean held-out log score
  is within one paired standard error (over held-out cells) of the best.
  Declared before the fit. A standard error clustered by respondent is
  reported beside it, because cells from one respondent are not
  independent; the declared rule is not changed.

  A first run (2026-11-16) was discarded for a bug, not for its result: the
  factor fit clipped any item whose communality exceeded the cap after
  optimising, and at K = 5 and 6 that left the residual RMSR worse than at
  K = 4 (0.067 against 0.038), which nested models cannot do. The fit now
  searches on the item response scale (λ = a/√(1 + |a|²), so communality
  stays below 1 by construction) with a ridge of 10⁻⁴ on a. The RMSR then
  falls at every K (0.085, 0.056, 0.046, 0.038, 0.033, 0.028 for K = 1 to
  6), and the ridge stops one extreme item (`CC24_324c`, "make abortion
  illegal in all circumstances", 10.5% support) running to a Heywood case
  at K ≥ 5 while leaving the RMSR unchanged to four decimals.

  **Result (2026-11-16): K = 6.** 216,214 held-out cells; mean held-out log
  score per cell, with its gap below K = 6 and the clustered standard error
  of that gap:

  | K | Log score | Gap to best | SE (clustered) | RMSR |
  |---|---|---|---|---|
  | 1 | −0.4566 | 0.0309 | 0.0006 | 0.085 |
  | 2 | −0.4430 | 0.0174 | 0.0004 | 0.056 |
  | 3 | −0.4351 | 0.0094 | 0.0003 | 0.046 |
  | 4 | −0.4303 | 0.0046 | 0.0003 | 0.038 |
  | 5 | −0.4293 | 0.0036 | 0.0002 | 0.033 |
  | 6 | −0.4257 | — | — | 0.028 |

  The declared rule chooses K = 6, which is the top of the declared range,
  and the score was still rising (K = 5 to 6 by about 16 standard errors),
  so the range was binding. K = 6 is used as declared. (An earlier claim
  that this is the conservative choice for H1 is withdrawn, 2026-11-17:
  more dimensions can make a shared representative less suitable, make a
  personal match harder to learn, or change which candidate wins; the
  balance is an empirical question.) Extending the range is a possible dated amendment
  before the primary run, not a change made here. Clustered and per-cell
  standard errors agree to two significant figures.

  **First fit (2026-11-16), version 1, since replaced by version 2** (see
  "Validation and two corrections before the freeze"; the item parameters
  and fit checks below are unchanged in version 2).
  K = 6 on all 60,000 respondents, 575 s.
  - Tetrachoric residual RMSR 0.028; 7% of the 630 item pairs miss by more
    than 0.05. The largest misses are pairs within one topic that the model
    makes too weakly related: "always allow abortion" with "expand access to
    abortion" (observed 0.91, fitted 0.75), zoning with affordable-housing
    incentives (0.48 against 0.33), and the two police-staffing items
    (−0.76 against −0.62). Within-topic structure is the part the model
    captures least, which matters for how new questions in a topic are drawn.
  - Support rates match exactly by construction (intercepts come from the
    thresholds), so that is not a check.
  - Position sampler, split R-hat over 12,000 coordinates (2,000 probe
    respondents): median 1.002, 99th percentile 1.05, worst 1.17. The
    district aggregates average over many respondents and draws, so the
    tail matters little for them; longer chains would tighten it.
  - Population: 436 districts with 59 to 235 respondents (median 136).
    Within-district covariance close to identity (diagonal 0.88 to 1.00);
    between-district variance is almost all on one dimension (0.045, a
    district standard deviation of about 0.21), the rest near zero. Whether
    that is enough district-to-district difference is one of the checks to
    run against the data (district-level support rates), since empirical
    Bayes shrinkage and the rotation can both understate it.

  **Pilot runs, disclosed (2026-11-16).** Before the primary settings were
  declared, three seeded cities (seeds 1 to 3, default
  `BeliefCityConfig`) were run through `compare` with every voter
  delegating every category (acceptance 0, not the 10% overhead rule).
  Fidelity: representative 0.624 to 0.640, proxy 0.638 to 0.664, liquid
  0.589 to 0.618, with 14% to 18% of liquid's delegated votes lost to
  resolvers who did not vote. These are not the H1 configuration and decide
  nothing, but they were seen, so any change to the primary settings made
  after them is recorded as such. The diagnostics run on the same three
  cities afterwards, and the amendments they led to, are in "Amendments
  after the pilot" under the research protocol.

  **Validation and two corrections before the freeze (2026-11-16).** The
  declared patterns were checked (`scripts/validate_beliefs.py`,
  `scripts/validate_holdout.py`; results in `.cache/ces/validation.json`).
  Two checks failed on the first model and led to corrections; the fit is
  now `delegation/data/beliefs_ces2024_v2.json` (version 1 removed). The
  items, K and the topic assignment are unchanged. The model v2 column is
  the fit regenerated on 2026-11-18 with the corrected covariance prior
  (see "Covariance prior" below).

  | Check | Data | Model v1 | Model v2 |
  |---|---|---|---|
  | Agreement with one's House member on the three bills with 118th-Congress roll calls (H.R. 7521, 7888, 2), corrected to 118th districts 2026-11-17 | 54.45%, 46.50%, 56.78% | 50.9%, 55.8%, 54.6% | 51.3%, 56.0%, 54.6% |
  | Between-district spread of item support rates, model over data (median, range) | — | 0.62 (0.43–0.73) | 0.94 (0.59–1.16) |
  | Moderates (liberal share 0.4–0.6); their spread of liberal share between topics | 20.3%; 0.258 | 22.6%; 0.245 | 21.6%; 0.246 |
  | CES 2022 items, median absolute correlation within / between topics, topics weighted equally on both sides (corrected 2026-11-17), model under the fitted population covariance (2026-11-18) | 0.528 / 0.469 | — | 0.523 / 0.433 |

  - **Representative (corrected 2026-11-17).** The first version joined
    119th-Congress district numbers (`cdid119`) to 118th-Congress roll calls;
    1,973 of 60,000 respondents have different numbers in the two. Joined on
    `cdid118`, respondents agree with their member 54.45% (TikTok), 46.50%
    (FISA) and 56.78% (H.R. 2) of the time; the simulated representative,
    now elected with turnout drawn as in the simulation (the turnout dial
    at the Swiss marker, spread 2.81), 51.3%, 56.0% and 54.6%. The mean hides that the model is about nine points too generous
    on FISA and three points short on the other two. This is a limited
    check: three bills on two topics, the only CES 2024 bills with a
    118th-Congress House vote (the contraception, abortion-access and
    marriage bills were 117th-Congress votes on the old district lines),
    counting only respondents whose member cast a yea or nay. It does not
    show that the simulation is fair to representation in general.
  - **Correction 1, district variation.** Version 1 drew every respondent's
    position under one N(0, I) prior, which pulls each district toward the
    national mean (the known bias of plausible values that ignore group
    membership), and then shrank the district means again. It reproduced
    only 0.62 of the observed spread. Version 2 samples positions from a
    hierarchical model, θᵢ ~ N(μ_district, W), μ_district ~ N(0, T), with
    W and T sampled in the same Gibbs run (`sample_grouped_positions` in
    `irt.py`, weak inverse-Wishart priors with K + 2 degrees of freedom and
    prior means 0.9 I and 0.1 I; corrected 2026-11-18, see below), and the
    simulation draws each district's mean from its posterior. On
    simulated data with known
    groups the grouped sampler recovered the between-group variance (0.283
    against 0.30) where the ungrouped one gave 0.168. Compared like for
    like (unweighted on both sides, as the model is fitted) the ratio is
    now 0.94 (0.97 before the prior correction below). District means
    are fitted unweighted; `commonweight` is no longer used. The first
    comparison, weighted on the data side only,
    read 0.77 because weighting adds noise to that side alone.
  - **Moderates.** Reproduced: about one respondent in five is moderate
    overall, and moderates are mixed across topics by about the same
    amount in data and model (Ahler and Broockman's pattern on binary
    items: liberal on some topics, conservative on others, rather than
    centrist on each). The model's distribution of liberal share is
    slightly compressed at the liberal end.
  - **Correction 2, question polarity.** Items in a topic are worded in
    both directions, so their loadings point in nearly opposite directions
    and their average cancels toward zero: version 1 generated questions
    that correlated far more weakly than CES 2022's real items. Version 2
    aligns each topic's items to its principal loading direction before
    fitting the topic distribution (reflecting (a, b), which only swaps
    which answer counts as support) and words each new question either way
    with equal chance. (Corrected 2026-11-17.) The first comparison
    weighted topics differently on the two sides: guns and policing
    supplied 91 of the 128 observed within-topic pairs while the model side
    weighted the five topics equally, and the "within-topic too strong"
    reading (0.53 against 0.47) came from that. (Revised 2026-11-18.) The
    model side now uses the population the benchmark draws, positions with
    the fitted within- plus between-district covariance, rather than the
    identity of the item fit's scale. With every topic weighted equally on
    both sides the within-topic medians nearly match (model 0.523, data
    0.528) and between topics the model is weaker (0.433 against 0.469),
    so the model separates within-topic from between-topic agreement a
    little more than the data does. Per topic, model against observed
    median within-topic |r|: environment 0.564 against 0.637, guns and
    policing 0.456 against 0.422, health care 0.358 against 0.314,
    immigration 0.639 against 0.621, reproductive rights 0.576 against
    0.561. No direction of bias is asserted. CES 2022 covers five of the
    eight topics; some of its items repeat 2024 wording. Because this check
    motivated version 2, it is development evidence, not independent
    validation; a later CES wave not yet used is reserved for that.
  - **Covariance prior (corrected 2026-11-18, second review).** For an
    inverse-Wishart prior in K dimensions E[Σ] = scale / (df − K − 1). The
    sampler used df = K + 2 and scale (K + 2) times the guess, so the prior
    means were 7.2 I and 0.8 I at K = 6 rather than the intended 0.9 I and
    0.1 I. The scale is now the guess itself and the fit was regenerated.
    The within-district covariance is unchanged (60,000 respondents swamp
    the prior); the between-district variance fell on the weakly varying
    dimensions (diagonal 0.013 to 0.055 before, 0.006 to 0.053 after),
    which moves the district-spread ratio from 0.97 to 0.94 and the other
    checks by less than half a point. The item parameters and topic
    distributions are unchanged.
  - **Position sampler, version 2.** Split R-hat over 12,000 position
    coordinates: median 1.002, 99th percentile 1.05, worst 1.18; over the
    district means: median 1.002, 99th percentile 1.03, worst 1.10.
    Between-district covariance diagonal 0.006 to 0.053, within-district
    0.92 to 1.05.
  - **K was chosen with the ungrouped sampler** (held-out cells, before
    correction 1). The choice is left as declared; the grouped prior
    changes held-out predictions little because 36 answers dominate a
    respondent's prior.
  - **Pooling and attendance (sensitivity, 2026-11-17; reworded
    2026-11-18).** Delegate choice counts a candidate's skipped question as
    a miss, so a reliable attendee looks good on every topic and the
    per-topic pooling strength may partly reflect attendance. On five
    fitted cities (history questions only, turnout dial at the Swiss
    marker, spread 2.81) the strength is 44 to 52 pseudo-questions as choice
    computes it, and 18 to 22 when only questions both people voted on are
    counted. (41 to 46 under the earlier uniform turnout: more varied
    attendance makes attendance count for more.) That is a sensitivity
    result, not an attribution: counting only jointly cast ballots changes
    both the outcome being predicted and the number of trials, so the gap
    between the two fitted strengths does not identify the share due to
    attendance (an earlier version said "more than half"). Separating the
    two would need a model or a controlled intervention on attendance. The
    strength is not presented as evidence about ideological bundling.
  - **Real-data selection test (development evidence, 2026-11-17; rerun
    2026-11-18 after the second and third reviews;
    `scripts/validate_selection.py`).**
    The simulation's mechanism is that someone chosen for agreeing with
    you on recorded questions agrees with you on the next one. This was
    checked on real CES 2024 respondents rather than the fitted model: 20
    cities, each of 5 real congressional districts with 100 respondents
    who answered all 36 items; each item is held out in turn, resolvers are
    chosen from the other 35 answers, and the score is agreement on the
    held-out item. Agreement only: there is no attendance or turnout here.

    *Corrections in the rerun.* The first run broke ties by row index, and
    rows were grouped by district: the topic-only arm averaged 99 tied
    candidates and sent 96% of its choices to the first district. Every
    choice now scores the average agreement over its tied best candidates.
    In the election, a resident tied among the three picks one of them at
    random and plurality ties are broken at random, and the election is
    scored by its exact winner probabilities (third review: an earlier
    rerun split tied ballots fractionally and took the plurality, a
    different rule; it gave representative agreement 0.60510 against
    0.60539 exactly, and differed by up to 5 points on one city and
    item). Every method is now scored on the same 485 residents who are
    not one of the three candidates; the first run compared means over 485
    and 495 people. Intervals now respect that the same 36 items recur in
    every city: one over cities (average within each city, then a
    t-interval over 20; inference to new cities on these items) and one
    two-way (crossed city and item effects; inference to new items like
    these too, and the one a margin is read against). The first run's
    standard errors treated all 720 city-item scores as independent.

    | Choice | Mean agreement | 95% over cities | 95% two-way |
    |---|---|---|---|
    | Random resident | 0.576 | 0.573–0.580 | 0.544–0.608 |
    | Representative, plurality of record preferences among three | 0.605 | 0.596–0.615 | 0.570–0.641 |
    | Own preferred of the same three | 0.664 | 0.652–0.675 | 0.633–0.694 |
    | Topic delegate, that topic's items only | 0.700 | 0.695–0.705 | 0.667–0.733 |
    | Personal proxy, city-wide | 0.738 | 0.733–0.744 | 0.710–0.767 |
    | Topic delegate, pooled prior (as liquid chooses) | 0.746 | 0.742–0.750 | 0.718–0.774 |

    | Paired contrast | Mean | 95% over cities | 95% two-way |
    |---|---|---|---|
    | Own-of-three minus representative (sharing) | +0.058 | +0.049 to +0.067 | +0.041 to +0.075 |
    | Proxy minus own-of-three (wider pool; one hop, no threshold, no turnout here) | +0.075 | +0.065 to +0.085 | +0.061 to +0.089 |
    | Pooled topic delegate minus proxy (specialisation) | +0.0075 | +0.006 to +0.009 | +0.004 to +0.011 |
    | Unpooled topic delegate minus proxy | −0.039 | −0.042 to −0.035 | −0.053 to −0.024 |

    The ordering is not the same in every topic (the first write-up said it
    was). The pooled topic delegate is at or above the proxy in all eight
    topics, by 0.0005 (environment) to 0.022 (reproductive rights). The
    unpooled topic delegate is below the proxy in seven topics and above it
    in reproductive rights (0.770 against 0.763), and below own-of-three in
    civil rights and liberties, health care and housing, the topics with
    two or three items.

    Reading: selection from a record carries to unseen questions in real
    data; sharing one representative and choosing among three local
    candidates cost most of the gap; and with only two to six items per
    topic, topic specialisation adds little beyond a well-chosen single
    proxy. Under the declared categories the specialisation contrast is
    *liquid better* in direction and *practically equivalent* in size: its
    two-way interval lies above zero and wholly within ±Δ = 0.02. Without
    pooling it is worse. This is a look at the topic-specialisation
    contrast before the freeze, disclosed here; the margin and the
    decomposition were declared before it and are not changed by it.
    Records with 50 questions per topic may differ, and the 36 items are a
    fixed national grid, not a random sample of questions.
- **Topics are observed, dimensions are latent.** Delegation categories are
  topics, assigned to items by hand from their wording, not latent
  dimensions. An authored assignment, approved 2026-11-16:

  | Topic | Items |
  |---|---|
  | Guns and policing | `CC24_321a`-`f` |
  | Immigration | `CC24_323a`-`d`, `CC24_340f` (asylum) |
  | Reproductive rights | `CC24_324a`-`d`, `CC24_340a` (contraception), `CC24_340b` (abortion services) |
  | Environment and energy | `CC24_326a`-`f` |
  | Housing | `CC24_328a` (zoning), `CC24_328b` (affordable-housing incentives) |
  | Health care | `CC24_328c` (Medicaid work requirement), `CC24_328d` (repeal the ACA), `CC24_328e` (expand Medicaid) |
  | Taxes and spending | `CC24_341a`-`d`, `CC24_323f` (student-loan forgiveness) |
  | Civil rights and liberties | `CC24_340c` (marriage recognition), `CC24_340d` (TikTok), `CC24_340e` (surveillance) |

  `CC24_323f` is student-loan forgiveness: its variable name sits in the
  immigration series, but its counts match that statement in the guide's
  health and tax grid.
- **New questions.** The simulation needs hundreds of questions, not 36.
  A new question in topic t draws (a, b) from a normal distribution per
  topic, centred on that topic's fitted items, with its spread estimated
  hierarchically (shrunk toward the spread pooled over all topics, since
  some topics have only two or three items: (nₜSₜ + κS_pool)/(nₜ + κ),
  with κ the length of the (a, b) vector). How different tomorrow's
  questions in a topic are from today's is the largest assumption left. It
  is set by the fit, and a multiplier on the within-topic spread is a
  robustness sweep.
- **Synthetic people and districts.** Districts are real congressional
  districts: each district's mean of θ is estimated from its respondents
  and shrunk toward the national mean (empirical Bayes; about 140
  respondents per district on average). A simulated district draws its
  residents from N(district mean, pooled within-district covariance). A
  simulated city takes a seeded sample of real districts, so how much
  districts differ comes from data and no lean parameter is invented.
  Weights: item parameters are fitted unweighted, as is usual for item
  response models; district means use `commonweight`.
- **What enters the repo.** Only aggregates: item parameters, topic
  assignment and per-topic distributions, district means with their
  shrinkage, the within-district covariance, and the chosen K with its
  held-out scores, written to a versioned JSON with the source file's
  checksums. No respondent-level values. The simulation then runs from that
  file without the 184 MB download.
- **Checks before the primary run (the declared patterns).**
  - The model must reproduce the 2024 items' correlation structure (fit
    check) and, on a different CES year (validation), the distribution of
    correlations between items it has never seen.
  - Ahler and Broockman's pattern: respondents who look moderate on
    average but hold strong positions on both sides of individual items,
    in the proportion found in the data.
  - Representative agreement: how often respondents agree with their real
    House member on the `CC24_340` bills (members' votes from Voteview).
    The simulated representative is honest, so it should do at least as
    well; how far it departs is reported per bill.
- **Where the code is.** The estimator, pure, in
  `delegation/comparison/irt.py` (tested in
  `delegation/tests/test_irt.py`). The CES loading and fit, which read the
  cached file, in `scripts/fit_ces_beliefs.py` (`choose-k`, then
  `fit --k K`, `retopic`), writing `delegation/data/beliefs_ces2024_v2.json`. The city
  generator in `delegation/comparison/beliefs.py` (tested in
  `delegation/tests/test_beliefs.py`); the one-factor model in
  `population.py` stays as the structural robustness sweep. A population
  now names its categories (topics here, issue dimensions there) and its
  districts (real district keys here).
- **Alternatives not taken.** Tetrachoric factor analysis alone, with no
  respondent stage (it gives no full likelihood to choose K on held-out
  data and no posterior for respondents; it is now stage 1, with stage 2
  supplying both). A logistic model fitted with stochastic
  gradient descent (needs PyTorch, which the project does not yet use, and
  gives point estimates). Resampling real respondents' posterior draws as
  synthetic people (preserves non-normal shapes, but puts
  respondent-level values in the repo).

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
  question, so direct voting is not idealised; full turnout is the ideal.
  Turnout is independent of preferences here, so at real turnout direct
  voting still picks the full-turnout winner on almost every question (on
  all of them in the first run); turnout that depends on preferences is a
  possible sensitivity.
- **Representatives.** Each district has a few candidates drawn from its
  residents; their platform is their true position. Voters choose the
  closest platform (unweighted distance across dimensions) and plurality
  decides. The representative votes their sincere position on every
  question, so representation is not handicapped by bad faith.

### Routing condition

Out of scope for H1 (2026-11-16); kept as the first follow-up. Per-category delegation is only low-overhead because questions are filed
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

Reported as curves, not single numbers. The values, populations and
seeds of the robustness sweeps for H1 are declared in "Robustness sweeps"
under the research protocol (2026-11-18).

Later, outside H1: the acceptance level (fixed for H1 by the 10% overhead
rule), turnout including delegates' turnout, and exact against measured
routing (see "Routing condition", now a follow-up).

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

**What each part claims (decided 2026-11-16).** The walkthrough carries the
empirical claim, H1, at the level of the eight topics. The control center
keeps free-text categories at any granularity, routed by the decision model,
and presents them as a design idea: what a finished system could offer, not
something the study shows to be better than topics. The app says so where
categories are written (a short note linking to the walkthrough's scope),
and the walkthrough names finer-grained delegation as untested (H2).

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
   evaluation, and fidelity, overhead and outcome agreement. *Implemented*
   in `delegation/comparison/` (2026-11-14), tested in
   `delegation/tests/test_comparison.py`. Tests include: direct voting
   matches every voter who votes; the factor loading produces the stated
   cross-issue correlation; the liquid-over-proxy gap is larger when issues
   cut across than when they are fully correlated; a longer history picks
   proxies who agree more on the evaluation period. (The planned test that
   representative and proxy fidelity converge with correlated positions was
   wrong: a proxy is chosen per voter, so it removes dilution even on one
   dimension.) Decided while building: everyone chooses delegates at once,
   and loops are left to the resolution rule. Applying the creation check
   one voter at a time made whoever was processed last the resolver of the
   whole city once everyone delegated; with simultaneous choice, mutual
   best matches both keep. First run, default city, acceptance 0:
   with cross-cutting issues (loading 0) liquid scored 0.737 against the
   proxy's 0.672 and the representative's 0.665; with fully correlated
   issues (loading 1) the proxy scored 0.769 against liquid's 0.742,
   because one overall history is a larger sample than six per-issue ones.
   Exploratory, not the benchmark.
6. **Benchmark.** The runner is built (`delegation/comparison/runner.py`,
   `scripts/run_liquid_benchmark.py`; see "Running the benchmark"). What
   remains:
   1. the freeze commit;
   2. the primary and sweep runs from that clean commit;
   3. the published results, `eval/benchmarks/delegation_frontier_v1/`: the
      threshold (Figure 1), the attendance frontier (Figure 2), the
      overhead-fidelity plane and the sweeps, with the run manifest. They
      are rebuilt from the recorded runs, as the synthetic preference
      benchmark is.

   The routing condition is a follow-up outside H1.
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
    needed is decided from the benchmark. First run: 13% to 14% of
    delegated votes were lost this way.
12. **Turnout and the direct reference.** Settled 2026-11-16: a
    full-turnout corner is the reference (see "Arrangements").

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
- Germann and Serdült, *Internet voting and turnout: Evidence from
  Switzerland*, Electoral Studies 47 (2017) —
  https://michagermann.github.io/publication/germannserduelt2017
- Goldberg and Sciarini, *Voter turnout in direct democracy: A joint
  analysis of individual, referendum and community factors*, European
  Journal of Political Research (2021) — doi:10.1111/1475-6765.12493
- Sciarini, Cappelletti, Goldberg and Lanz, *The Underexplored Species:
  Selective Participation in Direct Democratic Votes*, Swiss Political
  Science Review 22(1) (2016) — doi:10.1111/spsr.12178
- Kling et al., *Voting Behaviour and Power in Online Democracy* —
  https://arxiv.org/abs/1503.07723
- TypeSafe, *Introducing System One Models & Jev* —
  https://typesafe.ai/blog/introducing-system-one-models-and-jev
- TypeSafe docs — https://docs.typesafe.ai
- OpenAI Decisions guide —
  https://developers.openai.com/api/docs/guides/decisions
- Sun, Xu, Shi, Yang, *Type-Safe Is Not Error-Free* —
  https://arxiv.org/abs/2609.26758
