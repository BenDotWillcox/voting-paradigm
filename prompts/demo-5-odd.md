# Demo 5: ODD description of the comparison model

This is a description of the simulation behind demo 5's hypothesis H1, in the
ODD form (Overview, Design concepts, Details) as updated by Grimm et al.
(2020). It is written before the benchmark runs, as the method standards in
[`demo-5-liquid-democracy.md`](demo-5-liquid-democracy.md) require. The
design doc's research protocol is the analysis plan; this document says what
the model is. Where the two overlap, the design doc gives the reasons and the
history of each decision, and this document gives the model as it stands.

It describes the code frozen with the research protocol on 2026-11-19,
after amendment A6 (H1 as a turnout threshold) and the benchmark runner:
`delegation/comparison/` (population, beliefs, choice, arrangements, measures,
protocol, sweeps) and `delegation/graph.py` for the resolution rule. A later
change to the model is a dated amendment in the design doc. Values marked
*measured* come from data, *fitted* from the CES model, and *stated* are
chosen and declared. A stated value is an assumption and is labelled as
one.

---

## 1. Purpose and patterns

**Purpose.** The model compares ways of deciding a city's yes/no questions on
two axes: the civic overhead they ask of voters and the fidelity with which
they represent each voter. It estimates one quantity:

> **H1 (amendment A6).** At comparably low civic overhead, there is a level
> of citizen turnout above which liquid delegation, with delegates chosen
> per category from public vote history, represents voters more faithfully
> than single-member district representation elected by plurality. The
> study estimates that level.

The model is for comparison, not prediction. It does not forecast how a real
city would vote, whether people would delegate, or how many would take
part. Turnout is a dial the model is run across, not an assumption it
depends on. For each level the model asks how much fidelity each
arrangement delivers to the same synthetic voters on the same questions.
Real turnout appears only as a reference marker: the Swiss mean per
federal vote, about 0.45.

**Patterns.** The population model was required, before any primary run, to
reproduce empirical patterns declared in advance. The numbers below are for
the version 2 fit, regenerated 2026-11-18; details are in the design doc,
"Validation and two corrections before the freeze".

| Pattern | Source | Data | Model |
|---|---|---|---|
| Agreement with one's House member on the three bills with 118th-Congress roll calls | Ansolabehere and Jones (2010); CES 2024, Voteview | 54.45%, 46.50%, 56.78% | 51.3%, 56.0%, 54.6% |
| Between-district spread of item support rates (model over data, median) | CES 2024 | — | 0.94 |
| Moderates (liberal share 0.4–0.6), and their spread of liberal share between topics | Ahler and Broockman (2018) | 20.3%; 0.258 | 21.6%; 0.246 |
| Median \|r\| within / between topics on CES 2022 items the fit never saw (development evidence) | Converse (1964); Baldassarri and Gelman (2008) | 0.528 / 0.469 | 0.523 / 0.433 |

A sixth check uses real respondents instead of the model. On CES 2024
respondents, a resolver chosen for agreement on 35 items agrees with the
respondent on the 36th more often than a random resident does (0.738 against
0.576 for a city-wide proxy). This is the mechanism the model relies on. It
is development evidence, reported in the design doc.

---

## 2. Entities, state variables and scales

| Entity | State variables | Notes |
|---|---|---|
| **Resident** (agent) | Latent position θ ∈ ℝ^K (K = 6); district; engagement score z and own turnout rate *p* ∈ (0, 1); sincere vote on every question; own ballot (cast or not) on every question; a public record (their history ballots) | 100 per district. Everyone in the city is both a voter and a potential candidate or delegate |
| **District** | A real congressional district key; mean position μ; three candidates; an elected representative under each election rule | 5 per city in the primary setting |
| **Question** | Topic (one of eight); loadings *a* ∈ ℝ^K and intercept *b*; wording direction; period (history or evaluation) | Binary: support or oppose |
| **Topic** (delegation category) | Name; per-topic distribution of question parameters | Civil rights and liberties, environment and energy, guns and policing, health care, housing, immigration, reproductive rights, taxes and spending |
| **Delegation** | (delegator, topic, delegate), or a single (delegator, delegate) for the proxy | Chosen once, at the end of the history period |
| **City** | Seed; districts; residents; history and evaluation question sets; per-question turnout draws | The unit of replication and the independent unit of inference |
| **Arrangement** | Rule assigning each (voter, question) a resolver whose ballot counts for the voter | Seven in `compare` (Section 3) |

**Scales.** There is no space and no clock. A city has two periods:
- *history:* 400 questions, 50 per topic in the primary setting, on which
  everyone votes for themself and which form the public record;
- *evaluation:* 160 questions, 20 per topic, on which the arrangements are
  scored.

Delegations are fixed between the two periods. A city of 500 residents
stands in for a much larger one: what the model needs is the ratio of
representatives to residents (one per 100), the size of liquid's candidate
pool (499 residents) and enough history per pair to rank candidates, not a
realistic population count.

---

## 3. Process overview and scheduling

Each city is processed in this order. Everything is deterministic given the
city seed.

1. **Draw the city** (Section 7.1): districts, district means, residents,
   turnout rates, and the history and evaluation questions with sincere votes
   and per-question turnout draws.
2. **History period.** Each resident casts their own ballot on each history
   question when its turnout draw falls below their own rate. These ballots,
   absences included, are the public record.
3. **Elections.** In each district three residents are drawn as candidates.
   Two elections are held, with one shared set of turnout draws and one shared
   tie-break per district:
   - the *platform* election: voters pick the closest platform;
   - the *record* election: voters rank candidates by agreement over the
     history record.
4. **Delegate choice** (Sections 7.4–7.5). From the history record alone:
   - each resident's agreement with every other resident is scored overall
     (proxy) and per topic (liquid);
   - the acceptance level is fixed by the 10% overhead rule on history
     questions;
   - every resident chooses simultaneously: per topic, the top-ranked
     candidate if that candidate's lower bound reaches the acceptance level,
     otherwise keep.
5. **Resolution** (Section 7.6). For each evaluation question and
   arrangement, every voter's resolver is found. For liquid and the proxy this
   follows delegation chains under the loop rule.
6. **Counting** (Section 7.7). Each resolver casts their sincere ballot when
   their turnout draw falls below their rate. An office holder holding
   anyone else's vote votes at exactly the office-holder rate; a delegate
   holding anyone else's vote votes at the larger of their own rate and a
   floor. Each voter's counted ballot is their resolver's ballot, or none.
7. **Tally.** Each question is decided by plurality over counted ballots, with
   abstentions set aside and a seeded tie-break per question shared by every
   arrangement.
8. **Measures** (Section 7.8). These are computed on the evaluation period
   only, per arrangement, against the voters' sincere votes and against the
   full-turnout winners.

The arrangements, in the order `compare` returns them:

| Arrangement | Whose ballot counts for a voter |
|---|---|
| `full_turnout` | Their own, always cast (the reference corner: fidelity 1, overhead 1) |
| `direct` | Their own, cast at their own turnout |
| `representative` | Their district's platform-elected representative, voting at the office-holder rate |
| `representative_by_record` | Their district's record-elected representative |
| `district_choice_voters` | Their own preferred one of the three if they voted in the record election, otherwise that election's winner |
| `district_choice` | Their own preferred one of the three |
| `proxy` | One resident chosen on overall agreement, followed transitively; their own on everything if no candidate is acceptable |
| `liquid` | Per topic, a resident chosen on agreement in that topic, followed transitively; their own on the topics they keep |

---

## 4. Design concepts

**Basic principles.**
- *Beliefs.* A multidimensional probit item-response model: a person
  supports a question when a · θ + b + e > 0. Positions are not reduced to
  one left-right axis; the number of dimensions and their correlation come
  from data. The design doc gives the reasons (Lenz 2012; Barber and Pope
  2019; Baldassarri and Gelman 2008).
- *Representation.* Single-member districts and plurality, with honest
  candidates whose platform is their true position.
- *Delegate choice.* Empirical-Bayes agreement from a public voting record,
  ranked by the lower end of a credible interval, so a short record counts
  for less than a long one.
- *Loops.* Everyone on a loop decides for themself (after Christoff and
  Grossi's default-opinion idea).

**Emergence.** These arise from individual choices and are not imposed:
- the delegation graph and its chains;
- loops, and the concentration of votes on one resolver (largest share per
  question);
- resolver attendance, fidelity and its distribution across voters;
- how often an arrangement's winners match full turnout.

**Adaptation.** At one decision point, the end of history, each resident
decides per topic whether to delegate and to whom. They delegate to their
best-ranked candidate when that candidate's lower bound reaches the
acceptance level, and keep the topic otherwise. A delegate may themself
delegate onward. There is no revision after the choice.

**Objectives.** Implicit. A voter wants a resolver who will vote as they
would, and accepts one only with enough evidence: the lower bound, not the
mean, must reach the acceptance level.

**Learning.** None within a city. Delegations are not updated in light of the
evaluation period.

**Prediction.** Voters predict future agreement from past agreement. The
posterior for a pair's agreement on a topic is a beta distribution, with the
prior centred on the pair's agreement on every other topic and its strength
estimated from the whole city (Section 7.4).

**Sensing.**
- Every resident sees every other resident's full public history record:
  each ballot cast and each absence.
- Nobody sees anyone's latent position, sincere vote on an unvoted question,
  or anything from the evaluation period.
- In the platform election, voters see candidates' true positions (honest
  platforms).

**Interaction.** Indirect only:
- through elections, where a district's residents jointly select one
  representative;
- through the delegation graph, where a voter's ballot can be cast by
  someone they never chose directly.

Deliberation, persuasion and campaigning are not modelled.

**Stochasticity.** Every random element has its own seeded stream:
- the district sample, district means, resident positions, turnout rates;
- question topics, parameters, wording direction, idiosyncratic vote terms
  and turnout draws;
- candidates and election turnout;
- tie-breaks for candidate ranking, elections and tallies.

Turnout draws are stored and shared across arrangements, so raising a
turnout floor only ever adds ballots and every arrangement in a city is
compared on common random numbers.

**Collectives.** Two kinds:
- *districts,* which elect one representative each;
- *the set of voters resolved by one person on a question,* which emerges
  from the graph.

There are no parties.

**Observation.**
- Measures are taken per city, arrangement and level of the turnout dial,
  on the evaluation period.
- The primary outcome is the paired city difference in fidelity, liquid
  minus representative, as a curve over the dial. It is computed from
  signed match counts, so ties are exact.
- The threshold is the lowest level from which liquid strictly leads at
  every higher level. It is read on two curves, all cities and the cities
  meeting the overhead cap, and the later of the two is taken.
- Inference treats the city seed as the unit, and each city contributes
  its whole curve. Intervals, the bootstrap and the verdicts are as
  declared in the research protocol and implemented in `protocol.py`.

---

## 5. Initialization

A city is fully determined by its configuration and seed.

| Setting | Primary value | Kind |
|---|---|---|
| Population | Fitted CES 2024 model, `beliefs_ces2024_v2.json` | fitted |
| Districts per city | 5, sampled without replacement from the 436 districts in the fit (all have at least 50 respondents) | stated |
| Residents per district | 100 | stated (scale) |
| District mean | Drawn from its posterior N(mean, covariance) in the hierarchical fit | fitted |
| Resident position | N(district mean, W), with W the fitted within-district covariance | fitted |
| Own turnout rate | logistic(location + 2.81·z), with z ~ N(0, 1) per resident and the location set so the mean rate equals the dial's level; constant across questions | the dial is swept, not assumed. Levels 0.1 to 0.9 (`protocol.TURNOUT_GRID`), with the Swiss mean of 0.45 as the reference marker (*measured*). The spread 2.81 is *calibrated* to one register statistic under this model: Geneva's ten ballot days at mean 0.493, 20.2% in none and 15.9% in all (Sciarini et al. 2016, Table 1); the model gives 18.6% and 17.6%. It is swept at 1.0, 2.07 and 3.5 |
| Attendance draws | A fresh uniform draw per resident and question | stated: the register counts ballot days, often several measures each, so the transfer to independent questions is an assumption. A sensitivity point shares one draw per ballot day of three questions |
| History questions | 50 per topic (400) | measured anchor: one Congress has 54 to 90 contested roll calls per topic (Voteview, 117th and 118th House; amendment A4) |
| Evaluation questions | 20 per topic (160) | stated |
| Topic mix | Even in both periods | stated |
| Within-topic spread of question parameters | ×1 of the fitted spread | fitted |
| Candidates per district | 3, random residents | stated |
| Office-holder rate | Exactly 0.96 at every level, whatever the office holder's own rate (the representative, and the three candidates in the matched arms) | measured: 118th House members cast a yea or nay on 96% of roll calls while serving (Voteview; amendment A1) |
| Resolver floor | 0: delegates vote at their own rate on the dial. Floors from 0 to 1 form the frontier's second axis | declared (amendment A6) |
| Credible mass for lower bounds | 0.8 | stated |
| Acceptance level | Highest level whose history overhead is at most 10%, per city and arrangement | calibrated by the protocol |
| Seeds | Primary city *i* has seed 1,000,000,000 + *i*, *i* = 1 to 200, each run at every level of the dial. Development used seeds 1 to 5, 20261114, 20261116 and small test seeds | declared (`protocol.primary_city_seeds`) |

---

## 6. Input data

The model reads one input file at runtime:
`delegation/data/beliefs_ces2024_v2.json`. It holds aggregates only: item
parameters, topic distributions, the within- and between-district covariances,
district posterior means and covariances, fit checks and the source file's
checksum. No respondent-level values enter the repository.

It is fitted from the CES 2024 Common Content (Schaffner et al.; Harvard
Dataverse doi:10.7910/DVN/X11EP6, version 9, CC0): about 60,000 respondents
answering 36 binary support/oppose items, assigned to the eight topics by an
authored mapping. Voteview roll calls (117th and 118th House) anchor the
history length and the office-holder rate; they are not read at runtime. The
fitting and validation scripts (`scripts/fit_ces_beliefs.py`,
`scripts/validate_beliefs.py`, `scripts/validate_holdout.py`,
`scripts/validate_selection.py`, `scripts/voteview_house_rates.py`) read raw
data cached in the Git-ignored `.cache/`.

---

## 7. Submodels

### 7.1 Beliefs and questions (`beliefs.py`, fitted by `irt.py`)

**The fit.** A two-stage estimate:
1. Items: tetrachoric correlations of the 36 items, then an unweighted
   least-squares factor fit on the item-response scale (λ = a/√(1+|a|²),
   ridge 10⁻⁴), converted to (a, b). K = 6 was chosen by held-out
   log-likelihood.
2. Positions: hierarchical Gibbs sampling with items fixed,
   θᵢ ~ N(μ_district, W) and μ_district ~ N(0, T). W and T have weak
   inverse-Wishart priors (K + 2 degrees of freedom, prior means 0.9 I and
   0.1 I). Two chains; split R-hat median 1.002, worst 1.18 over positions
   and 1.10 over district means.

**Topic distributions.**
- Within each topic, items are aligned to the topic's principal loading
  direction, which reflects (a, b) for an item worded the other way.
- A normal distribution over (a, b) is fitted to the aligned items. Its
  covariance is shrunk toward the pooled within-topic covariance,
  (nₜSₜ + κS_pool)/(nₜ + κ), with κ = K + 1.

**A new question in topic t.**
- (a, b) is drawn from N(meanₜ, spread² · covₜ), where spread is the
  within-topic multiplier (1 in the primary).
- It is then worded either way with probability ½: (a, b) → (−a, −b).
- A resident supports it when a · θ + b + e > 0, with e ~ N(0, 1) drawn
  fresh per resident and question. That gives the sincere vote.

### 7.2 Turnout

Each resident has an engagement score z ~ N(0, 1), drawn once. Their own
rate is *p* = logistic(location + σ·z), with σ = 2.81. The location is
solved numerically so that the mean of *p* over z ~ N(0, 1) equals the
dial's level (`population.turnout_location`).

Turning the dial moves every resident's log-odds by the same amount. The
same residents therefore stay ranked the same, and each city keeps its
positions, questions and turnout draws at every level. Raising the dial
only ever adds ballots.

For every question there is a uniform draw *u* per resident, and they cast
their own ballot when *u* < their rate. With attendance clustering (a
sensitivity point), consecutive questions in groups of three share one draw,
as the measures of one ballot day do.

A person holding anyone else's vote on a question uses a different rate:
- an *office holder* (the elected representative, or one of the three
  candidates in a matched arm) votes at exactly the office-holder rate,
  0.96. Their own rate plays no part, so the comparator is the same at
  every level of the dial;
- a *delegate* votes at max(*p*, floor). The floor is 0 on the dial and
  rises to 1 on the frontier.

The draws are stored, so all arrangements in a city share them. Only people
who decide a question (they resolve their own vote or hold someone else's)
can cast a ballot on it.

### 7.3 Elections

**Candidates.** In each district, three distinct residents are drawn at
random.

**Turnout.** A resident votes in the election when a separate election draw
falls below their own rate, so election turnout follows the dial too. Both
elections use the same draws.

**Platform election** (`representative`). Each voting resident votes for the
candidate whose true position is closest to theirs in unweighted Euclidean
distance over θ. Plurality decides, with a seeded tie-break per district.

**Record election** (`representative_by_record`). Each voting resident votes
for their preferred candidate by whole-record agreement, ranked as in 7.5. A
candidate who turns out votes for themself, in both elections. The same
tie-break draw per district is used,
so identical ballots give identical winners in the two elections.

### 7.4 Agreement from the record (`choice.py`)

**Counts.** For voter *v* and candidate *c* over a set of history questions:
- matches: the questions *v* voted on where *c* cast the same ballot;
- trials: the questions *v* voted on.

A candidate's absence is a miss, so agreement mixes political agreement with
attendance.

**Proxy.** A uniform Beta(1, 1) prior over the whole record.

**Liquid (amendment A3).** Each topic's agreement has the prior
Beta(s·μ, s·(1 − μ)):
- μ is the pair's posterior mean agreement on every other topic, so a topic's
  own questions are not counted twice;
- s is one strength for the city, estimated by maximising the beta-binomial
  marginal likelihood over all (voter, candidate, topic) triples, searched
  between 0.1 and 10,000 pseudo-questions.

**Ranking statistic.** The lower end of the central 80% credible interval of
the posterior.

### 7.5 Delegate choice and the overhead rule

**Ranking.** For each voter and topic, candidates other than the voter are
ranked in this order:
1. by lower bound;
2. then by posterior mean;
3. then by a seeded random key per (voter, candidate);
4. then by index.

The random key exists because rows are grouped by district: breaking ties by
index would send tied choices to the first district.

**Empty records.** A resident with no recorded ballot at all keeps every
topic. Every candidate would tie on the prior alone, so any delegate would
be chosen by the tie-break, not from the record.

**Choice.** The voter delegates the topic to their top-ranked candidate when
that candidate's lower bound reaches the acceptance level, and keeps it
otherwise. Every voter chooses at once.

**Overhead rule.** Overhead on history questions is computed at every
distinct level at which any delegation changes, plus 0 and 1, with exact
per-topic resolution. The acceptance level chosen is the highest at which it
is at most 10%. No early exit or bisection is used, because overhead need not
fall steadily as the level falls. A city where no level reaches 10% uses its
lowest-overhead level and is flagged. The proxy is calibrated the same way on
its single category.

### 7.6 Resolution and the loop rule (`arrangements.py`, `graph.py`)

Routing is exact: a question belongs to its own topic and no other. Within
one topic each voter has at most one next hop, so resolution is a walk on a
functional graph:
- a voter who keeps the topic resolves for themself;
- a voter who delegates follows the chain to its first member who keeps;
- **everyone on a loop decides for themself**, and voters upstream of a
  loop resolve to the loop member their chain reaches first.

This fast path is tested against `graph.resolve_question`, the account
app's general resolver, on the same inputs. Loop membership and the number of
loops per question are recorded.

**Matched arms.** `district_choice` assigns each resident to their preferred
candidate, and a candidate to themself. `district_choice_voters` does the
same for residents who voted in the record election, and assigns everyone
else to that election's winner. These arms do not delegate onward.

### 7.7 Counting and the tally

- **Counted ballot.** A voter's counted ballot on a question is their
  resolver's sincere ballot if the resolver cast one (7.2), and none
  otherwise.
- **Tally.** Each question's winner is the plurality of counted ballots,
  abstentions set aside, with a seeded tie-break per question shared by every
  arrangement.
- **Reference.** The full-turnout reference counts every sincere vote.

### 7.8 Measures (`measures.py`)

All measures are over the evaluation period, per arrangement:

- **Fidelity.** The share of (voter, question) pairs whose counted ballot
  equals the voter's sincere vote, unweighted.
- **Three shares.** Every pair's counted ballot is a match, a contrary
  ballot or no ballot, and the three shares sum to 1.
- **Overhead.** The share of (person, question) pairs on which the person
  decides: they resolve their own vote, or someone else's vote depends on
  their ballot.
- **Lifecycle overhead.** For arrangements that need a record:
  (H + overhead · E)/(H + E), where H and E are the numbers of history and
  evaluation questions. It counts the history period as fully self-decided.
- **Outcome agreement.** The share of questions whose winner equals the
  full-turnout winner.
- **Resolver attendance.** The share of (holder, question) pairs on which a
  person holding others' votes cast a ballot, read from their own cast.
- **Delegated and lost votes.** The share of votes resolved by someone else,
  and the share of those whose resolver did not vote.
- **Fidelity on kept and resolved pairs.** Each arrangement's fidelity on
  the pairs its voters kept and on the rest. For H1 and specialisation, the
  difference is also split over liquid's kept and resolved pairs with both
  arms scored on the same pairs, and the two parts sum to the difference.
- **Per-voter distribution.**
  - The share of voters with fidelity below ½, and the 10th percentile.
  - For voters below ½, their mean share of no-ballot and contrary pairs.
- **Concentration.** The largest share of all votes on one question held by
  one resolver, averaged over questions and at its maximum.
- **Loops.** The share of pairs on a loop, and loops per question.
- **Light and empty records.** Two rows, each with a share and a fidelity:
  - residents who cast fewer than 10% of the history questions
    themselves;
  - the subset who cast none, who keep every question.

### 7.9 The structural population (`population.py`; belief-structure sweep only)

**Positions.** Eight dimensions stand for the eight topics. A resident's
position on dimension *d* is

λ_g·g + λ_b·b_block(d) + √(1 − λ_g² − λ_b²)·ε_d + district lean_d

- *g* is a shared factor, *b* a factor shared within the dimension's block,
  and ε_d is specific to the dimension;
- district leans are N(0, 0.26²) per district and dimension;
- dimensions correlate at λ_g² + λ_b² within a block and λ_g² across blocks,
  before leans.

**Questions.** Each question lies on one dimension, with a random direction
and cutpoint c ~ N(0, 1.15²). A resident supports it when
direction · (position_d − c) + noise > 0, with noise ~ N(0, 1.11²).

**Matching.** These three parameters were matched to the fitted population on
the same simulated summaries, as the design doc records. Noise stands in for
the fitted model's structured within-topic spread, and the doc states that
limit.

### 7.10 Inference and sweeps (`protocol.py`, `sweeps.py`)

These are part of the analysis plan rather than the model, listed so the run
can be replayed. `runner.py` executes them (`scripts/run_liquid_benchmark.py`
`primary`, `sweeps`, `analyse`), and its manifest binds each run to one
commit. All of them are declared in the research protocol:
- the turnout grid and the fixed 200 primary cities;
- the threshold:
  - the sustained strict crossing, on signed match counts converted to
    fidelity by the pairs per city;
  - read on the all-city and cap-meeting curves, the later taken, with
    unobserved cap-meeting levels never claimed;
  - its nominal 95% confidence set, from a simultaneous bootstrap-t band
    over both curves:
    - each curve is a ratio of exact count totals to a city count, the
      same at every sweep point as in the primary;
    - each resample is studentized by its own spread;
    - a moved mean with zero or undefined spread, decided on exact totals,
      counts as an infinite deviation;
    - at rotating-agenda points, resampling and variance are within heavy
      topics;
    - coverage is approximate, and a rare outcome absent from a sample
      cannot be recovered;
  - reversal flags on both curves;
  - the overhead gate where liquid is claimed ahead;
- the direction and size readings at a single level;
- the specialisation gate on the joint share;
- the 48-city robustness sweeps, each run across the dial;
- the attendance frontier (Figure 2), on the threshold's strict two-curve
  criterion, which is a separate figure from H1.

---

## What the model leaves out

These are not modelled:
- deliberation, agenda-setting and compromise by representatives;
- strategic voting, campaigning and changing preferences;
- revision of delegations over time;
- routing error (exact routing is assumed; measured routing is a follow-up);
- weighting questions by how much a voter cares.

Bundling lets a voter trade issues they care little about for ones they care
about, which an unweighted comparison does not credit. The model also says
nothing about whether people would be willing to delegate, or how a real
public record would be published.

## References

- Ahler, D. J., and Broockman, D. E. (2018). The delegate paradox: why
  polarized politicians can represent citizens best. *Journal of Politics*
  80(4).
- Ansolabehere, S., and Jones, P. E. (2010). Constituents' responses to
  congressional roll-call voting. *American Journal of Political Science*
  54(3).
- Baldassarri, D., and Gelman, A. (2008). Partisans without constraint:
  political polarization and trends in American public opinion. *American
  Journal of Sociology* 114(2).
- Barber, M., and Pope, J. C. (2019). Does party trump ideology? Disentangling
  party and ideology in America. *American Political Science Review* 113(1).
- Christoff, Z., and Grossi, D. (2017). Binary voting with delegable proxy.
  https://arxiv.org/abs/1707.08741
- Converse, P. E. (1964). The nature of belief systems in mass publics. In
  *Ideology and Discontent*, ed. D. Apter.
- Germann, M., and Serdült, U. (2017). Internet voting and turnout:
  evidence from Switzerland. *Electoral Studies* 47.
- Goldberg, A. C., and Sciarini, P. (2021). Voter turnout in direct
  democracy: a joint analysis of individual, referendum and community
  factors. *European Journal of Political Research*.
- Grimm, V., Railsback, S. F., Vincenot, C. E., et al. (2020). The ODD
  protocol for describing agent-based and other simulation models: a second
  update to improve clarity, replication, and structural realism. *Journal
  of Artificial Societies and Social Simulation* 23(2) 7.
- Lenz, G. S. (2012). *Follow the Leader? How Voters Respond to Politicians'
  Policies and Performance.* University of Chicago Press.
- Sciarini, P., Cappelletti, F., Goldberg, A. C., and Lanz, S. (2016). The
  underexplored species: selective participation in direct democratic
  votes. *Swiss Political Science Review* 22(1).
- Schaffner, B., et al. Cooperative Election Study Common Content, 2024.
  Harvard Dataverse, doi:10.7910/DVN/X11EP6, version 9.
- Lewis, J. B., Poole, K., Rosenthal, H., et al. *Voteview: Congressional
  Roll-Call Votes Database.* https://voteview.com
