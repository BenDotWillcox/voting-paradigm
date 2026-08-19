# Evaluation Harness

`eval/` contains reproducible evaluation code shared by the demos. The
preference-model work currently has two separate tracks.

## Fixed-Bank Synthetic Track

The existing harness compares Gaussian and Bradley-Terry preference models
under fixed-sequence, random, and max-variance acquisition policies. Synthetic
personas have known latent utilities, and held-out pairs never enter
acquisition.

```bash
python -m eval.run_preference_eval
```

Use this track for model misspecification, response-noise, acquisition-policy,
and parameter-sweep development. It does not establish human-voter validity.

## Standardized Human-Measure Track

The human track will evaluate pre-answer predictions on independent civic
measures in one standardized fictional jurisdiction. Political identity is not
a model input. The primary outcomes will be prequential log loss and
high-confidence delegated error; question efficiency is secondary.

Phase 1 provides:

- strict Pydantic contracts in `eval/contracts.py`;
- deterministic fixture loading and canonical SHA-256 manifests in
  `eval/fixture_io.py`;
- the non-held-out eight-domain fixture in
  `eval/fixtures/preference_eval_dev_v1.json`; and
- a fixture validator:

```bash
python -m eval.validate_fixture \
  eval/fixtures/preference_eval_dev_v1.json
```

The development fixture is contract scaffolding, not the final 48-measure
evaluation bank. It is deliberately fictional, constructed, and marked
`development_only`. Do not report generalization gaps or other research
outcomes from it: its one-measure-per-domain shape intentionally confounds
domain, ballot format, option count, and authored novelty tier so every
contract path can be exercised cheaply.

## Phase 2 Deterministic Replay

Phase 2 adds a leakage-safe prediction adapter boundary and prequential runner
in `eval/prequential.py`. An adapter receives the frozen jurisdiction, one
target packet, and only the evidence available at the snapshot cutoff. Future
participant responses are held in a separate session script and enter the
evidence stream only after the immediate pre-answer snapshot is frozen.

The committed synthetic session exercises:

- zero-evidence and post-onboarding snapshots for every target;
- post-wave snapshots for every still-unanswered target;
- one immediate pre-answer snapshot used for primary scoring;
- stable and tentative choices, unsure, and deliberate abstention;
- binary, ranked, approval, score, and quadratic response payloads; and
- deterministic response ordering, timestamps, sequence numbers, and hashes.

Run the complete development replay with:

```bash
python -m eval.run_human_measure_eval
```

The command compares a genuine uniform zero-information baseline with an
explicitly labeled scripted test double. The scripted adapter exists to test
replay, chronology, and metric behavior; it is not a research baseline and its
development result is not evidence that preference modeling works.

Primary option metrics include every initial `choice` response, including
tentative choices. Stable and tentative results are also reported separately.
`unsure`, `abstain`, and `retest` do not define option labels and are excluded
from option log loss and delegated risk. Voting on an unsure or abstain response
is counted separately as unsupported delegation.

`eval/human_metrics.py` computes log loss, multiclass Brier score, top-choice
accuracy, settledness Brier score, candidate-threshold risk/coverage, the full
observed risk/coverage curve, and unsupported delegation. Candidate thresholds
default to 65%, 75%, 85%, and 95%; no product default is selected. Exact
probability ties receive fractional top-choice credit, making null-baseline
accuracy independent of fixture option order. Delegated risk is conditional on
coverage: `wrong automatic choice votes / automatic choice votes`; coverage is
`automatic choice votes / eligible choices`. Report risk together with coverage
and the automatic-vote count.

Settledness treats a stable choice or stable deliberate abstention as settled,
while unsure and tentative responses are unsettled. Deliberate abstention means
the participant has reached a civic decision not to cast an option vote; unsure
means the preference remains unresolved.

The private metric object retains the full observed risk/coverage curve and
wrong-vote confidence diagnostics. It also reports checkpoint slices by model,
checkpoint, and wave, including the prediction denominator and minimum/maximum
available evidence-event counts. Zero-evidence and post-onboarding slices score
the full eventual response set; post-wave slices score only measures still
unanswered at that checkpoint, so their denominators and composition must be
considered when comparing them.

The allowlisted publication candidate emits only the fixed
candidate-threshold grid of 65%, 75%, 85%, and 95% and a machine-readable model
role. The serializer enforces that grid regardless of additional thresholds
used for private diagnostics. Exact confidence and checkpoint diagnostics can
permit per-measure response reconstruction when the fixture and model are
reproducible, so they must never cross the public serializer. Aggregate output
still requires explicit release review and is not a formal
ballot-confidentiality guarantee for a single participant.

Before releasing an artifact based on real participant data:

- obtain explicit participant approval for the exact artifact;
- inspect consecutive-threshold count deltas for singleton or very small bins;
- withhold the artifact or prepare a separately reviewed coarser aggregate when
  those deltas create unsafe cells;
- do not publish per-measure predictions beside the aggregate artifact; and
- do not treat anonymous participant labels as sufficient privacy protection.

## Contract Invariants

- Every persisted record declares a version.
- Unknown fields fail validation.
- Option IDs, display order, packet arguments, response fields, and source
  provenance are validated.
- `unsure` and `abstain` are distinct non-ballot states.
- Rankings may be partial and contain tied tiers.
- Score responses cover every option explicitly; downstream voting adapters may
  still omit zero-score options when casting a ballot.
- Quadratic allocations obey the same `votes²` credit cost used by the voting
  package. Each measure explicitly declares whether negative votes are
  meaningful; the development budget-allocation contest does not allow them.
- Prediction snapshots contain full option probabilities and an explicit
  evidence cutoff.
- Exact probability ties resolve to a deterministic snapshot option by frozen
  display order; headline accuracy splits credit across tied maxima.
- Presentations distinguish initial and retest exposures. A retest prediction
  may use the original answer, but cannot use evidence from the retest
  presentation it predicts.
- Event and response sequence numbers share one chronological stream. Sequence
  order must agree with wall-clock time, and artifact cutoffs cannot include
  records created after the artifact.
- Runs carry the fixture hash and must pass `validate_run_against_fixture`
  before scoring or replay.
- Dynamic ontology versions cannot use evidence after their own cutoff.
- Canonical hashes use Unicode-normalized, validated content rather than source
  formatting or unnormalized URL spelling.
- Frozen files and their manifests remain replayable without PostgreSQL.

## Evidence Layers And Prediction Fields

`EvidenceEvent` is the audit-level provenance record. Its `modality` says how
the observation entered the session. `preferences.types.Evidence` is the
model-level normalized pairwise or slider observation. Future structured-model
adapters will perform that explicit, auditable conversion; the similarly named
records are not interchangeable.

Retest is a presentation kind, not an evidence modality. The underlying answer
may still be a structured response, correction, override, or free-text
extraction.

Prediction and response fields intentionally preserve distinct concepts:

- prediction `confidence` is the top-option probability in v1 and is stored
  explicitly for threshold decisions and audit;
- `settled_probability` estimates whether the participant has a stable,
  expressible choice, not which option they will choose;
- response `preference_strength` is the participant's reported intensity; and
- `order_seed` records reproducible presentation ordering.

Top choice, ranking, approval, and score fields are retained as the participant
entered them. Cross-format inconsistency is a diagnostic to measure and, in
the UI, potentially confirm; it is not silently rejected or rewritten by the
schema.

## Private Human Data

Every `EvaluationRun` and `EvidenceEvent` is private by default, including
normalized claims, metadata, and pseudonymous identifiers—not only raw response
text. Store local run records under `eval/private_runs/`, which is ignored by
Git. Never commit a human run.

Public artifacts use the dedicated allowlist schema and serializer in
`eval/public_artifact.py`, containing only approved aggregate metrics and
explicitly public labels. They are never produced with
`EvaluationRun.model_dump*` or by subtracting a small denylist from a run
record. Raw responses, normalized claims, metadata, and
participant/run/evidence/presentation/response identifiers remain private.
Serializer tests plant sensitive strings across the private replay and prove
none appear in the public artifact. The raw-response field's 20,000-character
limit is an ingestion safeguard, not a privacy boundary. Generated aggregate
results go under `eval/results/`, which is ignored by Git.

Formal consent, retention, deletion, and publication records are required
before any separately approved pilot. They are not implied by the Phase 1
development fixture or Ben's private self-case study.

## Next

Phase 3A freezes the authoring inputs for the final standardized bank:

- the fictional State of Meridian and City of Harborview baseline;
- the exact 48-slot domain/source/tier/ballot matrix;
- source, political-cue, and neutrality-review requirements;
- a seeded six-wave presentation-order policy; and
- the balanced 12-measure retest target.

Validate and hash that profile with:

```bash
python -m eval.validate_bank_profile \
  eval/fixtures/preference_eval_bank_profile_v1.json
```

`eval/bank_profile.py` also provides
`validate_final_fixture_against_profile`, which enforces every
machine-checkable bank requirement. Primary-official source classification,
factual traceability, contextual-sufficiency review, adversarial neutrality
review, reviewer provenance, and participant-independent approval remain
explicit review-ledger gates rather than guesses made from packet prose.

See `eval/PHASE3_AUTHORING.md` for the authoring matrix, review workflow,
retest rules, remaining deliverables, and packet-blind case-study exposure
policy.
Phase 3B sourced and drafted the exact measures in domain batches. Codex
authored the bank and Claude conducted the participant-blinded content review;
the ledger must disclose the AI reviewer and bind its model/version and locked
prompt by hash. Human content review remains required before an external pilot.
Ben has already seen the topic-level authoring briefs; exact packet language,
options, quantitative values, arguments, and uncertainties remain withheld
until presentation. Intended-novel results must carry that exposure caveat.

Phase 3B infrastructure lives in `eval/bank_authoring.py` and
`eval/review_artifacts.py`. Each six-measure `DomainBankBatch` binds frozen
slots to exact measures and `MeasureSourceEvidence`; source captures preserve
retrieved-content hashes and explicit source roles, while content traces bind
exact adapted strings to packet sources, frozen jurisdiction facts, or
explicit structured assumptions. Constructed measures must declare at least
one assumption, and every declared source and assumption must support an exact
trace. These first content-bearing authoring records use the v2 trace,
source-evidence, batch-item, and domain-batch contract family; the final
fixture, bank profile, and review-log contracts remain v1. The assembler fails unless it
receives exactly one valid batch for every domain, then emits measures in
frozen slot order:

```bash
python -m eval.build_final_bank \
  eval/fixtures/preference_eval_bank_profile_v1.json \
  eval/restricted_bank/batches/fiscal_economy_labor.json \
  eval/restricted_bank/batches/health_social_provision.json \
  eval/restricted_bank/batches/education_family.json \
  eval/restricted_bank/batches/housing_land_use.json \
  eval/restricted_bank/batches/transportation_infrastructure.json \
  eval/restricted_bank/batches/environment_energy.json \
  eval/restricted_bank/batches/justice_safety_rights.json \
  eval/restricted_bank/batches/governance_elections_technology.json \
  --fixture-id preference_eval_final_v1 \
  --created-at 2026-08-01T12:00:00-05:00 \
  --output eval/restricted_bank/preference_eval_final_v1.json
```

All eight restricted six-measure domain batches passed structural validation
and the locked participant-independent Claude review by 2026-08-11. All 48
measure versions are approved at exact hashes. The eight participant-safe
review results live under `eval/review_summaries/`; exact batches, source
caches, and disposition logs remain ignored and separately backed up. The
first review's mid-review status associated finding existence with specific
slots without exposing exact content. That non-content communication deviation
is documented in `eval/PHASE3_AUTHORING.md`; future review status must remain
aggregate-only throughout.

Exact review uses `eval/prompts/phase3_packet_review_v1.md`, whose canonical
hash is pinned in code. Restricted disposition logs may contain packet text;
participant-facing review evidence must be produced only through
`build_nonrevealing_review_summary`, which emits hashes, provenance, approval,
and aggregate counts without copying free text.
`bank_review_ledger_entries_for_batch` deterministically turns the same
validated review and source-role records into final ledger entries.

`python -m eval.validate_domain_batch PROFILE BATCH` prints only aggregate
counts and hashes. After exact-content review,
`python -m eval.validate_batch_review PROFILE BATCH RESTRICTED_LOG
--summary-output SAFE_SUMMARY` validates the frozen Claude prompt and writes
the allowlisted participant-safe summary.

Until every predeclared blinded participant has completed both initial
presentations and retests, exact batches, fixtures, variants, and detailed
review logs remain under the Git-ignored `eval/restricted_bank/` directory and
never enter a PR. Claude reviews those files locally. Retrieved source
documents remain under `.cache/eval-authoring/sources/` and are never
committed. Only generated safe summaries and aggregate hashes under
`eval/review_summaries/` may be reviewed or committed during this period.
Keep a separate access-controlled backup of ignored artifacts and verify its
hashes. See `eval/PHASE3_AUTHORING.md` for the later disclosure rules.

Retest paraphrases are separate `RetestPacketVariant` records linked to
canonical measures, not duplicate fixture measures. A
`RetestVariantRegistry` freezes those links and
`validate_final_bank_bundle` validates the canonical fixture, retest selection,
slot-to-measure review ledger, content hashes, and reviewer provenance together.
Phase 3C realizes the profile's six waves of eight and 7-14 day retest interval
through a deterministic presentation plan. Run validation enforces exact wave
order, per-presentation option-order seeds, canonical-versus-retest packet
versions, original-response-before-retest independence, elapsed intervals,
and complete planned coverage. Its progressive form accepts honest run
prefixes without claiming completion.

The restricted retest review uses
`eval/prompts/phase3_retest_review_v1.md`; its normalized canonical hash is
pinned in `eval/retest_review.py`. The registry remains unusable until the
locked review approves every exact variant hash. The first near-verbatim
registry and second mechanically rewritten registry were both rejected and
remain in the restricted audit trail. Direct review found nine version-3
packets approval-ready and requested three targeted repairs. Version 4 keeps
the nine approval-ready packet hashes unchanged, changes one field in each of
three packets, and is approved at all 12 exact packet hashes. The final review
ledger and execution-bundle manifest bind the approved 48-measure fixture,
registry version 4, and presentation plan version 4. Automated quantity,
source, decision-rule, and identity guards do not establish semantic
equivalence. The four Phase 3C commands
keep exact content in ignored paths and print only aggregate manifests:

```bash
python -m eval.build_presentation_plan PROFILE FIXTURE RETEST_REGISTRY \
  --plan-id PLAN_ID --created-at CREATED_AT --output RESTRICTED_PLAN

python -m eval.validate_retest_review PROFILE FIXTURE RETEST_REGISTRY \
  RESTRICTED_REVIEW_LOG --summary-output SAFE_SUMMARY

python -m eval.build_final_review_ledger PROFILE FIXTURE RETEST_REGISTRY \
  RESTRICTED_RETEST_REVIEW \
  --batch-review DOMAIN_BATCH DOMAIN_REVIEW \
  --ledger-id LEDGER_ID --created-at CREATED_AT --output RESTRICTED_LEDGER

python -m eval.validate_final_bundle PROFILE FIXTURE RETEST_REGISTRY \
  RESTRICTED_LEDGER RESTRICTED_PLAN --created-at CREATED_AT \
  --manifest-output RESTRICTED_MANIFEST
```

Repeat `--batch-review DOMAIN_BATCH DOMAIN_REVIEW` once for each of the eight
domains. `validate_final_bundle` is the final structural gate; a completed run
must additionally pass `validate_completed_run_against_plan` before analysis.
The frozen Phase 3C bundle is ready for blinded case-study scheduling, but the
six waves and retests have not yet been executed.

## Phase 4A Architecture And Comparison Freeze

Phase 4A defines the preference-system experiment before selecting an LLM
provider or prompt. The LLM interviewer is an elicitation orchestrator with
typed access to posterior uncertainty, candidate-question scores, evidence
coverage, and conflicts. An explicit probabilistic model remains the sole
owner of durable preference state; LLM-extracted evidence has zero weight
until participant confirmation. The direct LLM predictor is a required
experimental control, not the intended state architecture.

The public profile freezes four acquisition policies, six reporting-anchor
model arms, six component ablations, three evidence conditions, held-out
target isolation, and one action rule. Model representation and readout
variants replay the same realized evidence at the same cutoffs. Acquisition
policies create different evidence streams, so causal acquisition claims
require seeded synthetic counterfactuals or later randomized participants;
one case-study path is descriptive only.
The separately declared party-conditioned prior is evaluation-only, requires
external support, and may use optional metadata collected only after retest; it
never enters the live preference evidence.

Validate and hash the public contract without loading the restricted measure
bank:

```bash
python -m eval.validate_phase4_protocol \
  eval/fixtures/preference_eval_phase4_protocol_v1.json \
  eval/fixtures/preference_eval_bank_profile_v1.json
```

The complete rationale and Phase 4A-4E sequence are in
`eval/PHASE4_PROTOCOL.md`. The evaluated action policy selects the
top-probability option for single-choice measures and requires valid
format-specific outputs for ranked, approval, score, and quadratic measures.
It displays confidence and permits participant override or abstention.
Confidence thresholds remain diagnostics; the model cannot improve its score
by abstaining or deferring.

## Phase 4B Acquisition And Interviewer Boundary

Phase 4B makes the first acquisition comparison executable without choosing or
calling a live LLM provider. `fixed_sequence` asks the canonical first unseen
vetted pair and is independent of answers, posterior state, and seed. The
synthetic comparison includes fixed-sequence, random, and max-variance policies
by default; the tool-using LLM policy remains a separate interactive evidence
stream rather than being simulated as a conventional selector.

`eval/phase4_interviewer.py` defines the provider-neutral boundary:

- versioned requests and three structured actions (ask a returned vetted
  question, clarify linked existing evidence, or pause);
- typed read-only uncertainty, candidate-score, coverage, and conflict tools;
- exact question, bank, posterior-state, conversation-history, evidence-cutoff,
  prompt, backend, model, and seed bindings;
- complete tool request/result audit records and constrained action validation;
  and
- in-memory and content-addressed directory caches. The persistent cache stores
  only the input hash plus structured output/tool trace, never raw private
  conversation text. Cache hits re-run the pure local tools and reject any
  stored result that differs from the current implementation.

The deterministic backend is a test double, not the LLM experimental arm. A
later live adapter must implement the same `InterviewerBackend` protocol and
use a private ignored directory such as `eval/private_runs/interviewer_cache/`.
Although raw conversation is excluded, cached tool traces contain
participant-derived structure such as observed pairs, conflicts, domain
coverage, and evidence links. The ignored, access-controlled path protects
that structure; `JsonDirectoryInterviewerCache` cannot make an arbitrary path
private.
No target packet is part of an interviewer request, and the contract pins
`target_packet_visible` to false. Phase 4B ends at a validated structured
decision and uses canonical vetted question rendering. Participant-facing
clarification rendering remains part of the later session integration.

## Phase 4C Confirmed Fixed-Ontology Evidence

`eval/phase4_evidence.py` implements the first Phase 4C slice without a live
extractor provider. It keeps four layers separate:

- private raw conversation messages;
- hash-bound extraction requests and independently confirmable claim
  proposals, each with source message IDs, extractor provenance and
  confidence, unsupported-assumption flags, and a literal zero provisional
  model weight;
- explicit participant accept, edit, or reject decisions for each proposal;
  and
- active typed `preferences.Evidence` records that can update an explicit
  posterior only after confirmation.

Accepted or edited inferred claims receive durable evidence-event IDs.
Extractor confidence remains audit metadata rather than silently becoming a
model weight. If a proposal carries unsupported-assumption flags, an accept or
edit decision must acknowledge every flag. Rejections create no evidence.
Corrections append a new confirmed event that supersedes one active event;
they never mutate or delete the earlier record, so replay before and after the
correction cutoff is deterministic.

`materialize_all_evidence_conditions` derives structured-only,
conversation-only, and combined views at the same event cutoff. Corrections
carry explicit structured or conversation provenance. Combined evidence uses
the latest correction; each single-source ablation uses the latest event in
that lineage with matching provenance. A conversational correction therefore
does not leak its revised value into structured-only: that counterfactual
retains the prior structured answer.

Accept and edit decisions both materialize as `free_text_extraction` because
both begin with an extractor proposal. The typed decision kind remains in
metadata so analysis can distinguish a verbatim participant acceptance from a
participant-authored edit rather than quietly conflating them.

The legacy direct HTTP route accepts only pairwise/slider evidence in both the
client-supplied state and the newly submitted observation. Its wire schema
also pins `confirmed_by_participant` to false. Confirmed inferred/correction
evidence must enter through a future server-side Phase 4C ledger integration,
not through a self-asserted client snapshot. The deterministic extractor is a
scripted boundary test double, not an LLM arm or a selected provider.

## Phase 4C Participant-Governed Ontology Expansion

`eval/phase4_ontology.py` layers an append-only expanding-ontology ledger over
the confirmed evidence boundary without changing the fixed-ontology contract.
Each ledger is bound to one evidence condition, so conversational dimensions
cannot leak into the structured-only ablation. Structured-only retains the
seed ontology because it has no raw conversation input; conversation-only and
combined expansion use only their condition-eligible evidence lineages.
An LLM may propose a missing value dimension, possible duplicates, and exact
support links, but the proposal carries a literal zero provisional weight. It
cannot alter the ontology until the participant independently admits it, maps
it to a reviewed existing dimension, or rejects it. Unsupported assumptions
and every proposed duplicate candidate must be acknowledged on a non-rejection
decision.

Each private proposal context binds the exact conversation prefix, active
confirmed evidence claims, active ontology definitions, extractor
configuration, policy, seed, and parent snapshot. It uses a stable evidence-
ledger identity hash rather than the full mutable ledger hash; exact per-prefix
hashes prevent tampering while allowing later evidence to append without
retroactively rewriting an earlier context. Target packets remain unavailable.
The deterministic backend is a provider-neutral test double, not a selected
LLM provider.

Duplicate defense has two layers. NFKC/casefold/whitespace-normalized exact
semantic duplicates are detected deterministically and cannot be admitted as
new dimensions. The proposer may also flag less-exact candidates for explicit
participant review; a map decision can target only one of those reviewed
candidates. Seed dimensions remain active and cannot be merged or pruned.

A participant admission and an independent evidence lineage contribute
separately weighted terms to a support score, so a genuinely new value can
enter from participant language even before the fixed ontology can encode it
without asserting that admission and observation are the same unit. The score
controls deterministic shrinkage up to the policy's full-weight threshold.
Corrections retain their original lineage and therefore cannot inflate support
by being counted as independent observations. Participant-
confirmed support, merge, and prune events are replayed at any event cutoff.
Merges preserve the superseded dimensions and union evidence provenance;
prunes preserve history and are permitted only for non-seed dimensions below
the versioned support-score and inactivity thresholds. Retired dimensions keep
their provenance but expose no shrinkage weight; model consumers use
`active_dimension_states`.

The policy values are versioned inputs, not yet the frozen experimental
hyperparameters. All raw messages, evidence-bearing contexts, proposals, and
ledgers remain private artifacts under the ignored run boundary.

## Phase 4D Versioned Prediction Boundary

`eval/phase4_prediction.py` adds `prediction_snapshot.v2` and
`evaluation_run.v2` as separate models; `eval/contracts.py` and its v1 records
remain unchanged. A v2 run embeds the private Phase 4C evidence ledger and any
condition-specific expansion ledgers, while continuing to reuse the frozen
measure-presentation and participant-response records. `as_v1_execution_run`
projects only that presentation/response surface so the Phase 3 wave, option-
order, retest-independence, and timing validators remain reusable without
routing v2 predictions through a v1 schema.

Each model configuration names one frozen Phase 4A arm and exact versioned
artifacts for the preference model, semantic mapper, readout, provider model,
and prompt that the arm actually uses. The snapshot binds that configuration,
the exact packet hash, the stable evidence-ledger identity, one materialized
evidence condition and cutoff, the exact eligible evidence and conversation
prefix, and posterior/ontology hashes for explicit-state arms. The reproducibly
derived `model_input_sha256` hashes the exact model-consumable packet,
evidence/conversation view, active state/ontology, component stack, and seed
without copying raw transcript content into a second field. Full ontology
history and configuration identity remain separately bound audit provenance.
The target response is literally unavailable at the input boundary, and the
run validator rejects evidence or messages created after target exposure as
well as snapshots frozen at or after the target response.

All arms emit a normalized probability for every option, a display-order-
deterministic top option, confidence equal to that top probability, and a
separate complete ballot action. Single-choice selects the top option; ranked
predictions cover every option; approval includes the top option; score and
quadratic payloads cover every option and keep the top option maximal; and
quadratic allocations also obey sign and credit-budget rules. This makes
confidence/calibration comparable without pretending that a rich ballot is a
single categorical choice. LLM and hybrid predictions retain private cited
evidence IDs and unsupported-assumption flags.

At a common target checkpoint, every present model arm must use the same event
cutoff. Arms in the same evidence condition must bind the same exact evidence
and conversation view. The active ontology receives its own feature-universe
hash separate from the full history hash; if fixed and expanding hybrid arms
use one identical component stack, evidence view, posterior state, active
feature universe, and model input, their probability and ballot outputs must
agree. This is the contract-level hook for the fixed/expanding sanity check.

### Authored classical readouts

`eval/phase4_semantic.py` makes the option-to-value bridge a separate reviewed
artifact rather than hiding it in either preference model. Each sparse stance
map binds the exact fixture, packet, option order, and fixed ontology. Weights
are relative across the options in one contest: every used dimension is
option-centered, so a negative value can mean "less aligned than the other
options" rather than opposition in isolation. Runtime normalization fixes the
largest pairwise stance-vector distance at one, preventing an author from
changing confidence by uniformly rescaling a map.

The public, non-held-out development artifact is
`eval/fixtures/preference_eval_dev_semantic_map_v1.json`. Validate it with:

```bash
python -m eval.validate_phase4_semantic_map \
  eval/fixtures/preference_eval_dev_semantic_map_v1.json \
  eval/fixtures/preference_eval_dev_v1.json
```

The command emits only aggregate counts and hashes. The future 48-measure map
must stay inside the ignored restricted tree and receive participant-
independent content review before use; the development map is infrastructure
evidence, not a held-out result.

The final-bank map is governed by the public precommitment at
`eval/fixtures/preference_eval_semantic_authoring_profile_v1.json`. Validate
that profile before opening any restricted packet:

```bash
python -m eval.validate_phase4_semantic_profile \
  eval/fixtures/preference_eval_semantic_authoring_profile_v1.json \
  eval/fixtures/preference_eval_bank_profile_v1.json \
  eval/fixtures/preference_eval_phase4_protocol_v1.json
```

The profile allows only the exact participant-facing packet and frozen
ontology definitions. Participant responses, preference evidence, posterior
state, political identity, partisan history, demographics, and outside policy
facts are forbidden. An author records each dimension with coarse option
positions `-1`, `0`, or `1`, marks it `primary` or `secondary`, cites an exact
participant-facing packet path for every option position, and writes a
restricted rationale. The builder derives centering and weights
deterministically (`primary=1`, `secondary=0.5` before runtime normalization),
which prevents arbitrary decimal tuning.

Keep the rationale bundle and derived map under `eval/restricted_bank/`. Build
the map with aggregate-only stdout:

```bash
python -m eval.build_phase4_semantic_map \
  eval/restricted_bank/semantic_map/authoring_bundle.json \
  eval/fixtures/preference_eval_semantic_authoring_profile_v1.json \
  eval/fixtures/preference_eval_bank_profile_v1.json \
  eval/fixtures/preference_eval_phase4_protocol_v1.json \
  eval/restricted_bank/final/preference_eval_final_v1.json \
  --output eval/restricted_bank/semantic_map/semantic_map.json
```

The builder resolves the output path before writing and refuses to place a
non-development map anywhere outside the repository's designated
`eval/restricted_bank/` root. This is a hard boundary: an accidental tracked
output would permanently reveal the held-out mapping through Git history.

Independent review uses the locked prompt at
`eval/prompts/phase4_semantic_review_v1.md`. It directly checks exact binding,
packet-only grounding, ontology fidelity, direction, primary/secondary
magnitude, option symmetry, sparsity, and political-cue exclusion for every
measure. A rejected round remains a restricted draft and cannot emit an
approval summary. After every exact mapping is approved, validate the log and
generate the only participant-visible artifact with:

```bash
python -m eval.validate_phase4_semantic_review \
  eval/restricted_bank/reviews/semantic_map_review.json \
  eval/restricted_bank/semantic_map/semantic_map.json \
  eval/restricted_bank/semantic_map/authoring_bundle.json \
  eval/fixtures/preference_eval_semantic_authoring_profile_v1.json \
  eval/fixtures/preference_eval_bank_profile_v1.json \
  eval/fixtures/preference_eval_phase4_protocol_v1.json \
  eval/restricted_bank/final/preference_eval_final_v1.json \
  --summary-output eval/review_summaries/semantic_map_summary.json
```

Only that validator-generated safe summary and approved artifact hashes may
enter Git history while the participant remains blinded. The exact map,
rationales, detailed findings, and rejected rounds stay ignored and receive
one access-controlled backup. Claude is the frozen independent AI reviewer
for the personal case study; a separate human content review remains required
before any external pilot.

The safe summary also derives a `phase4_reviewed_semantic_mapper.v1`
attestation. Every non-development `Phase4EvaluationRun` that includes a
mapped classical or hybrid arm must carry that exact mapper, authoring-profile,
review-log, and safe-summary provenance. Run validation requires the approved
mapper hash on every mapped arm and requires the approval count to match the
fixture. Public development runs may continue to exercise an unreviewed
development map, but an unreviewed held-out map cannot enter a valid run. The
attestation is evaluation provenance and deliberately does not alter the model
input hash.

`eval/phase4_classical_readout.py` replays the Gaussian linear or Bradley-
Terry posterior from the exact structured-only evidence cutoff. Both models
then use one common uncertainty-aware readout. For each option pair, the
normalized stance map yields a posterior mean difference and variance. The
standard logistic-normal correction converts that pair into an approximate
log odds; complete-graph averaging couples those pairwise values into one
multiclass softmax. Zero posterior means therefore remain exactly uniform,
while higher posterior uncertainty flattens confidence. Settledness stays
separate: it is the minimum posterior probability that the predicted top
option clears each opponent by the versioned utility margin.

The common ballot-action subpolicy is reusable by later LLM and hybrid arms.
It keeps contract-level `1e-12` top ties in frozen display order, preserves
configurably grouped ranking ties, approves
options at or above uniform probability, maps uniform score ballots to five,
and produces budget-valid integer quadratic allocations. Model, mapper,
readout, posterior-state, and input hashes are all recomputed by the artifact-
aware validator; a caller cannot make a forged state hash self-consistent and
silently pass. Readout temperature, settledness margin, and other versioned
policy values remain development inputs until the Phase 4E freeze.

### Provider-neutral LLM and hybrid readouts

`eval/phase4_llm_readout.py` implements the final Phase 4D readout boundary.
The direct-LLM control receives the exact neutral measure plus only the
structured, conversation, or combined evidence surface named by its model
configuration. The request contains no participant response and cannot name a
posterior or semantic mapper. Hybrid requests add a freshly replayed explicit
posterior projected into the target option space through the exact authored
semantic map, including per-option moments and every frozen-order pairwise
margin and probability; caller-supplied posterior hashes are never trusted.

The expanding hybrid uses the same fixed posterior projection and adds only
active, participant-admitted non-seed dimension states. With no active
expansions its model input hash is intentionally identical to the fixed hybrid,
so the fixed/expanding equivalence gate remains live. Once an admitted
dimension becomes active, its semantic definition, support state, and
shrinkage weight enter the active-ontology hash. Merged and pruned history does
not enter the provider input.

Provider model, prompt, readout policy, target packet, evidence, conversation,
posterior, active ontology, and seed are all exact hash-bound inputs. Each LLM
snapshot separately records the full private provider-request hash. Structured
responses must cover every option, cite only eligible evidence, and identify
unsupported assumptions by affected option. A content-addressed cache stores
responses but not private request text; filesystem caches must still live in
an ignored, access-controlled directory because responses may contain private
audit diagnostics. Every response becomes a ballot through the same common
five-format action policy used by the classical baselines.

`DeterministicLLMReadoutBackend` exercises this contract and cache without
pretending to be an experimental model. A live adapter, final provider/model,
prompt, and policy values are Phase 4E freeze decisions, not defaults hidden in
the infrastructure.

`confidence` is comparable across every arm because it always equals the top
option probability and is the quantity used for risk/coverage analysis.
`settled_probability` is deliberately family-specific: classical arms report
a posterior minimum pairwise-margin probability, while LLM arms report a
versioned provider self-assessment. Do not pool or threshold settledness across
those model families.

The Phase 4E profile below freezes prompt/order robustness requirements. LLM
predictions retain private supporting-evidence IDs and unsupported-assumption
flags. Repeated calls are sensitivity or Monte Carlo diagnostics, not
independent human observations. The Phase 2 runner still deliberately stops
before live-provider execution or a human-facing UI.

## Phase 4E Qualification And Robustness Precommitment

`eval/phase4_robustness.py` freezes the public rules used to qualify a live
model without selecting one in code. The primary experiment requires an
open-weight model, allows hosted inference, and does not require local
inference. Exactly three candidates are compared on public development data;
one qualified model must then serve the interviewer, evidence extractor,
ontology proposer, direct readout, and hybrid readout roles. Exact upstream
and serving revisions, weight and license hashes, provider terms, and required
tool/structured-output capabilities are recorded. Closed-weight models have no
automatic fallback. A model upgrade creates a new candidate artifact and
results remain attributable to the exact revision, so later upgrades can be
compared without changing orchestration code.

The participant boundary is pseudonymous, not anonymous: provider requests use
opaque IDs and exclude direct identifiers, political identity, and demographic
proxies. Contact/consent records stay separate. A local scan must redact a
flagged identifier or record that the participant confirmed it was a false
positive before transmitting the text, and provider terms must prohibit
training on requests. Public results remain aggregate-only.

The personal-study API budget is a hard USD 20, represented as integer
microusd: USD 4 for qualification, USD 13 for the held-out study, and USD 3 for
retries. Every attempted provider call requires an authorization that fits the
remaining segment and total caps. Authorizations are hash-bound to subsequent
usage records, and their maximum costs consume the cap as soon as they are
issued. A completed call replaces its reservation with actual billed cost;
outstanding calls continue to reserve their maximum, so concurrent requests
cannot jointly oversubscribe the budget without permanently discarding unused
room. Cache hits cost zero and retries use only the reserve with an exact
original-call link. The profile does not authorize spending by itself and this
slice makes no provider calls.

The adapter must close every authorization with either a usage row or an
explicit zero-cost failure/cancellation record. Until that lifecycle record is
implemented, an abandoned authorization intentionally remains reserved and an
attempt without a recorded call cannot enter the retry reserve. The adapter
also needs incremental running totals for live authorization; the full ledger
validator remains the end-of-run audit rather than the per-call hot path.

The primary estimator is one provider call. Three repeats, two locked prompt
paraphrases, one alternate option order, and one neutral option-label mapping
are staged shadow diagnostics rather than a factorial ensemble. Order and label
changes require exact top-choice equivariance; prompt and stochastic changes
measure sensitivity. All invalid outputs, flips, probability deltas,
Jensen-Shannon divergence in bits, and unsupported-assumption deltas are
recorded. Every prediction, comparison, and aggregate binds the exact public
profile and open-weight candidate revision; each shadow also binds its exact
prompt/order/label/stochastic artifact and applicable probe coordinates.
Deterministic order and label builders and participant-safe aggregate contracts
make those comparisons replayable. Top-option ties use the same `1e-12`
display-order rule as the Phase 4D prediction contract.

Order and label probes require their deterministic construction seed.
Stochastic probes always bind a repeat index and bind a sampling seed only when
the candidate backend honestly exposes one; seeded sampling is not a hidden
capability requirement.

Version 1 treats order/label invalid outputs and top-choice flips as hard
failures while recording their probability movement. Probability-delta and
divergence thresholds are calibrated on public development data in the final
freeze; adding those threshold fields changes the profile version and hash.
Invalid canonical calls are candidate-qualification failures rather than
shadow-comparison rows, so aggregate `invalid_output_rate` covers shadow
variants only.

The primary outcomes are prequential log loss and high-confidence delegated
error on the fixed public confidence grid. Accuracy, Brier score, calibration,
acquisition/model/ontology/readout deltas, retest consistency, generalization,
learning curves, rich-ballot fidelity, assumptions, robustness, cost, and
latency are secondary. The personal case study is descriptive; it cannot
support a population-superiority claim, and held-out responses cannot select a
model, prompt, or threshold.

Validate the exact public profile with:

```bash
python -m eval.validate_phase4_robustness \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/fixtures/preference_eval_phase4_protocol_v1.json \
  eval/review_summaries/semantic_map_summary.json
```

The next 4E slice implements provider adapters and produces auditable
candidate-qualification artifacts on public development data. It must not use
the restricted participant responses or spend from the held-out study segment.
