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

The adapter closes every authorization with a usage row and terminal record.
A zero-cost cancellation additionally requires a hash-bound attestation that
the request was never sent or that the provider confirmed it was voided. An
aborted transport therefore remains reserved until that evidence exists.
Provider-reported token counts that exceed the local upper bound are recorded
at their true price under a distinct hard-failure outcome; any amount above the
authorization is explicit rather than discarded. Such an overrun prevents
further authorization once a cap is exhausted and makes the end-of-run cap
audit fail if actual spend crossed it. Incremental running totals serve the
live path, while the full ledger validator remains the end-of-run audit.

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
Stochastic probes bind the Phase 4D request seed and a unique repeat index in
`1..3`. The provider execution record separately says whether that seed was
sent and whether the provider confirmed honoring it; seeded sampling is not a
hidden candidate capability and an unconfirmed seed is never presented as a
determinism guarantee.

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

`eval/phase4_provider.py` supplies the shared runtime adapter beneath all five
LLM roles. A private request carries the exact prompt, JSON input, response
schema, and interviewer tool definitions, while its durable binding contains
only hashes and public execution coordinates. The same executor accepts an
injected provider transport for every role; it contains no candidate-specific
or model-specific orchestration branch. The committed transport is a
deterministic no-network test double. A concrete hosted or self-hosted
transport is selected only with the three candidate artifacts.

`eval/phase4_together.py` now freezes the no-spend portion of that selection.
The tracked `preference_eval_phase4_together_v5.json` suite binds Together's
20 August 2026 serverless catalog and privacy/capability documentation, exact
upstream Hugging Face revisions, revision-bound weight-manifest identities,
license provenance, advertised serving model strings and quantization, exact
price cards, and one candidate-independent prompt/schema/tool contract for all
five roles. The suite is honest about the hosted boundary: Together does not
publish a cryptographic serving-weight attestation, so the recorded serving
revision is the exact captured catalog hash rather than a claim of bit-level
identity with the upstream checkpoint. Qualification results must retain that
limitation.

The original v1 through v4 suites remain tracked as hash-pinned audit artifacts.
The v2
suite raises the interviewer logical-call envelope from 5,000 to 15,000 input
tokens and from 500 to 1,000 output tokens, raises extractor/proposer input
envelopes from 4,000 to 6,000, and sets held-out direct/hybrid readout input
envelopes to 7,000/8,000. Exact calibration showed that the v1 bounds could not
carry all accumulated evidence, the interviewer's required tool-call follow-up,
or the post-wave-six retest inputs. The v2
transport originally combined tools and strict structured output in both
rounds. The v3 suite corrected that shared protocol: round one
requires at least one tool call and sends no final-output `response_format`;
after the tool result, round two removes the tools and requires the strict
decision schema. Both payloads are counted. No candidate, price, privacy rule,
or budget segment changed. The v4 suite fixed the broader provider-
contract class exposed by the extractor failure. A machine-readable manifest
covers all 26 provider-facing invariants. Nonsemantic list ordering and repeated
identifiers are normalized on receipt, and reversed fixed-ontology pairs are
canonicalized with sign inversion. Request-bound semantics cover all five
roles. The interviewer, evidence-extractor, and ontology-proposer wire contracts
advance to v2; the direct and hybrid readout contracts remain byte-identical v1
contracts so successful readout calls can carry forward.

The operative v5 suite changes only the interviewer's final provider-facing
decision. The interviewer still uses the LLM to navigate the dynamic vetted
question surface: the exact current tool call ranks candidates from the full
question bank and the model decides which returned candidate to ask (or whether
to clarify or pause). This is not a tiny static questionnaire or a local
deterministic question selector. For an ask decision, the provider now returns
only the selected question's id. Trusted local code requires that id to identify
a candidate from the same tool invocation, verifies the candidate's canonical
content hash locally, and hydrates the existing full decision before validation,
storage, and hashing. The model therefore keeps the substantive navigation
choice without having to reproduce canonical fields or an opaque digest. The
operative v2 invariant manifest, hash
`944efa35f60c3a9286f96b201ef21a9b1ff7ecda1a9a6ae96369c491e959523b`,
records this selector's grounding as post-parse and its local materialization as
normalized plus post-parse. The preserved v1 manifest remains byte-identical for
historical audit reconstruction.

The exact tool-result context used for hydration is ephemeral and is excluded
from durable provider records; its hash is bound into the finalization so the
materialization is still auditable. An unknown, stale, or unreturned selector
closes as model invalid output. Missing, malformed, or conflicting local
context closes separately as a transport-contract failure, so a harness defect
cannot be recorded as a model capability failure. Suite v5's canonical hash is
`e97b6213955cf86d18da98d2d1300679b17ab773838d1ed10fcdb84b1f1de9b8`.

Together was chosen over self-hosting because the USD 20 total budget cannot
cover the sustained accelerator rental needed for the 120B and 550B candidates.
Self-hosting would provide stronger weight attestation, but it would make this
personal study infeasible and prevent a same-provider comparison. The hosted
tradeoff is explicit and reversible in a future candidate artifact.

There are two narrower provenance limits. All three serving revisions use the
same catalog-snapshot hash; that proves which advertised rows and prices were
captured, not which internal model build Together deployed, and it cannot
detect a silent redeployment. GPT-OSS and Nemotron retain the upstream/serving
quantization family, while GLM changes from a BF16 upstream checkpoint to
Together's advertised FP4 build. Any GLM result therefore describes that
Together FP4 deployment, not the upstream revision by itself. The external
model rows, revisions, prices, capabilities, and the unusually specific
512300-token Nemotron context value must be re-read from their public sources
during live preflight; the tracked hashes detect local drift but cannot prove
that a transcription was correct.

The Together codec renders an already hash-bound private provider envelope to
the documented OpenAI-compatible chat shape with JSON Schema, the request
seed only when the binding says it was sent, and interviewer functions. In the
interviewer's final phase, the schema appears both in the system message and
`response_format`; exact token counting includes both copies. The codec
contains no credential, HTTP client, or network call. A live account privacy
check and paid capability probes remain mandatory before qualification;
validation alone can never spend money.

Provider request v2 hash-binds the exact semantic-validator artifact. The paid
runtime resolves that identity through a trusted local registry before parsing,
so a caller cannot substitute a weaker validator while keeping the same public
request coordinates. The request-specific adapters enforce the exact public
question, grounding, ontology-gap, option-set, and citation semantics supplied
to each role.

`eval/phase4_together_live.py` makes those readiness statements enforceable.
The shared provider runtime calls each transport's authorization gate before
creating a budget reservation. The Together paid transport requires the exact
suite/profile, a manually confirmed account-privacy artifact, an authenticated
catalog receipt, a tokenizer-readiness receipt, a frozen headroom policy, and
an active user authorization. Qualification additionally requires the completed
capability matrix. The transport exact-counts its rendered payload immediately
before each send, runs a bounded interviewer tool loop, aggregates provider
usage across follow-ups, and leaves an authorization outstanding when delivery
may have occurred but usage cannot be audited.

Future held-out prompts cannot honestly be rendered exactly before the
participant creates their evidence. The frozen rule is therefore: count all
renderable qualification requests exactly, use an explicitly wave-aware
held-out calibration for the budget decision, exact-count each future request
before transmission, and pause rather than truncate or send if it exceeds the
authorized envelope.

The runtime prices an aggregate token upper bound against an exact price card,
reserves the maximum before transmission, and updates cached committed totals
in constant time. Success, invalid output, provider error, transport error,
transport-contract error, token-bound overrun, cache hit, and attested
cancellation have explicit terminal records. A never-sent transport failure
does not incur a fixed request fee; a sent or unknown failure does. A
cancellation releases its reservation only with structured no-charge evidence,
while every provider-observed response retains its token usage and true price.
The runtime can resume once from a progressive ledger/journal pair and
reconstruct its running totals before the next request. The full historical
ledger validator remains the end-of-session audit oracle, so the live path
avoids the cubic session behavior that repeated full replay would cause.
Authorization times must strictly follow every earlier runtime event, and
finalization times cannot move backward. Concrete transports should therefore
use locally observed receipt times for these audit fields rather than raw
provider-server timestamps; the runtime rejects clock skew before it can make
the incremental budget proof disagree with timestamp replay.

Together live authorizations are segment-scoped. Capability and qualification
calls use the USD 4 qualification segment. A retry of a closed failed call
requires a fresh live authorization for the USD 3 retry reserve and preserves
`retry_of_call_id` lineage through the shared ledger. The live authorization
contract still excludes the held-out-study segment; that separate participant
boundary is not part of this qualification slice.

Provider inputs use either a public-development attestation or a pseudonymous
participant attestation. Participant input requires an opaque participant id,
a hash-bound local identifier scan, zero unresolved findings, and an exact
count showing every hit was redacted or participant-confirmed as a false
positive. This is a pseudonymization control, not an anonymity guarantee.

`eval/phase4_qualification.py` defines the auditable qualification bundle.
Exactly three candidate and price-card artifacts are evaluated on one exact
public fixture;
every LLM role must be exercised, interviewer tool results must replay, all
structured outputs must validate, and order/label probes must have zero
invalid outputs or top-choice flips. Failed hard gates remove a candidate
before ranking. Remaining candidates use the frozen priority order with
sequential practical-equivalence bands: within 0.001 Jensen-Shannon divergence
proceeds to development log loss, within 0.01 log loss proceeds to projected
held-out cost, within USD 0.10 proceeds to p95 latency, and within 100 ms uses
candidate id only as a deterministic final tie-break. This lets a negligible
float difference in one criterion avoid silencing every later criterion while
preserving the declared priority. Sensitivity is the equal-weight mean of the
prompt-class and stochastic-class mean Jensen-Shannon divergences. Every cost
projection binds one shared workload plus an exact token-counter/envelope
artifact and price card, so a candidate cannot win by silently projecting
fewer calls. The Together no-spend projection uses the same conservative role
bounds for every candidate, but its sum-of-all-envelopes total is a stress
diagnostic rather than a live authorization artifact. Renderable development requests must be counted
with every candidate's exact tokenizer; held-out budgeting uses a wave-aware
calibration because future participant evidence does not exist yet. Both must
include the duplicated schema and tool-loop allowance. A minimum headroom rule
is then predeclared. The binding sequential proof adds the largest single-call
envelope reservation to exact projected spend under each segment cap; the
execution plan must remain sequential for that proof to apply. Every future
payload is exact-counted before send;
over-envelope requests pause without transmission. Until those steps are
complete the validator reports `live_authorization_ready: false`.
Provider-reported token usage remains the billing truth after a call. A projected study
that exceeds the USD 13 held-out segment cannot qualify. The bundle binds the
complete provider ledger and execution journal, embeds content-free per-call
contract assessments and robustness aggregates, and rebuilds every candidate
result from those exact sources during validation. It requires zero held-out
spend and emits only aggregate diagnostics.

Validate a completed qualification with:

```bash
python -m eval.validate_phase4_qualification \
  eval/restricted_bank/phase4/qualification.json \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/restricted_bank/phase4/provider_usage_ledger.json \
  eval/restricted_bank/phase4/provider_execution_journal.json
```

The Together suite closes the candidate, price, shared-contract,
request-codec, live authorization boundary, and initial budget-feasibility
parts. The v2 conservative envelopes project 456 qualification calls at
USD 3.5604. For the 1,104-call held-out workload their non-authorizing
sum-of-all-envelopes diagnostics are USD 16.7520, USD 1.9368, or USD 9.0720
for GLM, GPT-OSS, and Nemotron. The exact no-spend readiness pass supplies the
authorization inputs: all 456 public-development calls are rendered and
counted with each revision-pinned upstream tokenizer, and a public synthetic
calibration counts six initial waves plus 12 post-wave-six retests. The latter
add 96 direct and 96 hybrid readout calls per candidate, for 1,104 future calls
per candidate. Because calls execute sequentially, authorization gates exact
projected spend plus the largest one-call envelope reservation rather than the
counterfactual sum of reserving all calls simultaneously.
No paid request may be sent until Ben separately authorizes qualification
spend. Qualification must not use restricted participant responses or the
held-out-study segment.

The 64 calls for each readout role are eight development measures times one
canonical call plus seven staged prompt/order/label/stochastic calls, producing
one complete robustness set per measure and arm. The interviewer, extractor,
and ontology proposer receive eight development calls each. Those calls test
their schema/tool compliance and replay gates only; qualification does not
claim to compare conversational-role quality across candidates.

Validate the frozen no-spend suite without credentials or network access:

```bash
python -m eval.validate_phase4_together \
  eval/fixtures/preference_eval_phase4_together_v5.json \
  eval/fixtures/preference_eval_phase4_robustness_v1.json
```

For the first authenticated but zero-inference preflight, create the ignored
repository-root `.env.local` manually with exactly one secret line:

```text
TOGETHER_API_KEY=<project-scoped key>
```

Never pass the key as a CLI argument or paste it into a review/chat. Confirm in
Together's Privacy & Security settings that training data sharing remains off,
acknowledge the documented default nonstorage and temporary-caching terms, then
run:

```bash
python -m eval.preflight_phase4_together \
  eval/fixtures/preference_eval_phase4_together_v5.json \
  eval/private_runs/phase4/together_catalog_preflight_v5_unique.json \
  --api-key-file .env.local \
  --confirm-project-scoped-key \
  --confirm-training-sharing-disabled \
  --confirm-default-nonstorage \
  --acknowledge-temporary-caching \
  --execute-zero-spend
```

The command re-fetches every public source and makes one authenticated
`GET /v1/models`. It requires exact candidate identities and prices, records
both the public catalog's advertised context window and the live endpoint's
context ceiling, and requires the live ceiling to fit the largest predeclared
request envelope. Together's live endpoint can report an implementation
ceiling that differs from the rounded or provider-advertised public catalog
value, so those two fields are deliberately not treated as interchangeable.
The aggregate CLI output reports both the mismatch count and the maximum
relative difference in parts per million; this is a deployment diagnostic, not
an arbitrary rejection threshold. The safety gate uses the live ceiling and
the exact study workload. Candidate hashes continue to bind the advertised
catalog value as provenance, while the separately hash-bound live receipt
records deployment capacity; neither hash claims that the advertised value is
the live deployment's internal ceiling.
The command makes no inference request, reports zero provider spend, stores no
API-key value or hash, and refuses to write outside `eval/private_runs/`. It
does not authorize capability probes or qualification.

Earlier ignored catalog receipts bind preserved suite versions and cannot
authorize v5. Re-run this zero-inference command after v5 merges; exact hash
binding intentionally prevents carrying a v4 or earlier receipt across the
protocol revision. The v4 suite and its receipt remain audit inputs for the
preserved provider-contract attempts, not live authorization inputs.

Build the separate no-key, no-inference tokenizer-readiness artifact with:

```bash
python -m eval.prepare_phase4_together_readiness \
  eval/fixtures/preference_eval_phase4_together_v5.json \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/fixtures/preference_eval_dev_v1.json \
  eval/fixtures/preference_eval_dev_session_v1.json \
  eval/fixtures/preference_eval_dev_semantic_map_v1.json \
  eval/fixtures/preference_eval_phase4_together_readiness_v5.json \
  --tokenizer-cache .cache/eval-tokenizers/phase4e \
  --download-tokenizers
```

The command downloads only revision-pinned tokenizer assets, never model
weights. It constructs a deterministic 456-call public-development plan with
exact payload hashes, creates a resumable prefix cursor, and calibrates six
future waves plus 12 post-wave-six retests using only public synthetic evidence
growth and original-response records. Every accumulated evidence record remains
materialized in every later wave, matching the unbounded production request
contract; the calibration validator requires input-token totals and per-request
maxima to increase strictly through every applicable presentation for every
candidate and role. Every real future request is counted immediately before
transmission and pauses if it exceeds the frozen role envelope. The headroom
freeze requires at least USD 0.40 in the USD 4 qualification segment and USD
0.50 in the USD 13 held-out segment after adding the largest single-call
reservation to exact projected spend.

The resulting v5 artifact projects qualification costs of USD 1.307109, USD
0.159562, and USD 0.860604 for GLM, GPT-OSS, and Nemotron respectively. Its
1,104-call-per-candidate held-out calibration projects USD 11.322791, USD
1.354910, and USD 7.142624. The corresponding sequential reservation headroom
is USD 1.647325 for qualification and USD 1.651809, USD 11.642240, and USD
5.844776 for the three held-out candidates. Interviewer totals include the
initial request and one synthetic tool-result follow-up. Qualification models
the exact one-candidate capability result; held-out calibration models ten
deterministic ranked candidates. A real request returning more candidates is
still exact-counted and pauses before transmission if it exceeds the frozen
envelope. These are deterministic local projections, not provider billing
claims: Together does not attest that its serving tokenizer is byte-identical
to the upstream tokenizer. Provider-reported usage remains billing truth.

For audit replay, the preserved v4 readiness artifact remains at hash
`517e955976eaeec708cbedfadb46673038dcfd47e472407573997c4913ab1cd5`;
its associated suite, capability plan, and delta retain the v4 numbers recorded
in the historical recovery section below. V5 is a new authorization chain, not
an in-place reinterpretation of those artifacts.

Validate the artifact without a tokenizer download or network access:

```bash
python -m eval.validate_phase4_readiness \
  eval/fixtures/preference_eval_phase4_together_readiness_v5.json \
  eval/fixtures/preference_eval_phase4_together_v5.json \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/fixtures/preference_eval_dev_v1.json \
  eval/fixtures/preference_eval_dev_session_v1.json \
  eval/fixtures/preference_eval_dev_semantic_map_v1.json
```

The validator emits aggregate counts, hashes, costs, and headroom only. The
readiness bundle hash is
`f6ac45a3da3a4c14784aa6a9562ec1e3c62cd141aba214748b4f6a9fcbbaf5fd`.
It records zero inference calls and zero provider spend. The original external
action was a separately authorized 15-call capability preflight. Those calls
are the exact first 15 entries of the qualification plan, so a complete success
could have resumed at call 16 rather than paying to repeat them.

Build or validate the tracked zero-spend capability plan with:

```bash
python -m eval.prepare_phase4_together_capability \
  eval/fixtures/preference_eval_phase4_together_v5.json \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/fixtures/preference_eval_phase4_together_readiness_v5.json \
  eval/fixtures/preference_eval_dev_v1.json \
  eval/fixtures/preference_eval_dev_session_v1.json \
  eval/fixtures/preference_eval_dev_semantic_map_v1.json \
  eval/fixtures/preference_eval_phase4_together_capability_v4.json

python -m eval.validate_phase4_capability \
  eval/fixtures/preference_eval_phase4_together_capability_v4.json \
  eval/fixtures/preference_eval_phase4_together_v5.json \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/fixtures/preference_eval_phase4_together_readiness_v5.json \
  eval/fixtures/preference_eval_dev_v1.json \
  eval/fixtures/preference_eval_dev_session_v1.json \
  eval/fixtures/preference_eval_dev_semantic_map_v1.json
```

The plan hash is
`e42b7d71c9ccfb07e6583313f07af60678178ef72eacf7182fa78255fa6f1fde`.
It binds one canonical request for every combination of three candidates and
five LLM roles. The 15 calls project to 71,973 microusd; their complete local
authorization envelopes sum to 129,000 microusd. The plan itself records zero
calls and zero spend.

The original all-candidate runner is now an audit path only. It must not be
re-authorized because its v2-suite interviewer request combined tools, automatic
tool choice, and strict final-output formatting in the same provider round.
The corrected v3 protocol is executed only through the candidate-isolated
continuation below, after a fresh v3 catalog receipt and separate user approval.

Two paid attempts were made on 21 August 2026 with public development inputs.
The first stopped after two GLM calls on an HTTP 503 and spent 2,277 microusd.
The second stopped after four GLM calls when the interviewer response failed
strict structured-output validation before making a tool call; it spent
10,866 microusd. The combined 13,143-microusd spend and exact private state,
authorization, ledger, journal, and finalization hashes are bound by the
tracked continuation artifact. The 503 remains a transient provider failure;
the interviewer result is harness-inconclusive because v2 used the confounded
wire shape described above. Neither attempt produced a capability receipt, and
no candidate is rejected by those attempts.

`eval/phase4_capability_continuation.py` preserves that outcome without
weakening the frozen three-candidate qualification. The tracked
`preference_eval_phase4_together_capability_continuation_v2.json` binds the
historical v1 plan and corrected v2 plan, retains all three candidates, and
derives one independently testable five-role plan per candidate. Its hash is
`afa317dc2618001028c855bc4f1656e1ba57358a5eb5a5c92574010e2419d75e`.
The 15 corrected calls project to 71,091 microusd and reserve at most 129,000
microusd: 78,000 for GLM, 9,000 for GPT-OSS, and 42,000 for Nemotron. Each plan
requires its own explicit approval and private execution state, so one
candidate's failure cannot suppress the other's evidence. The continuation
proves a 142,143-microusd cumulative worst case—prior spend plus every corrected
maximum reservation—under the original 150,000-microusd capability ceiling.
The continuation explicitly forbids qualification authorization. After all
three checks, a separate no-spend aggregation step must bind the candidate
receipts into the full capability matrix before qualification. The frozen
qualification bundle records every tested candidate; hard-gate failures remain
disqualified results, and selection proceeds only among eligible candidates
without post-hoc replacement.

The first corrected v3 candidate check completed all five GLM calls for 14,121
microusd. Direct readout, extraction, hybrid readout, and the corrected
two-phase interviewer passed; the ontology proposer returned an invalid strict
structured output. Because that invalid response was intentionally discarded,
the result remains a provisional candidate failure until the other two
candidates exercise the exact same role schema. The ignored state is bound at
`5dc62a9aded1215d3050809f6964fd0398231115167f28ab92eafd239b6b8213`.

The tracked zero-spend adjudication policy
`preference_eval_phase4_together_capability_adjudication_v1.json`, hash
`939134d659d35a93aafb6a6fd11fec8fda25326681a93434ef918247f50ac581`,
freezes that provisional status before either comparison candidate runs. If
all three candidates fail the same role and exact response schema, the result
requires shared-harness review before any candidate rejection. A nonuniform
pattern receives candidate-specific review using content-free diagnostics.
Future invalid-output paths write an ignored sidecar containing only the error
count, Pydantic error types, and schema-relative field paths. Input values,
error messages, and error context are structurally omitted; the sidecar binds
the exact finalization and response-schema hashes without changing the provider
journal or preserved state hashes.

Rebuild or validate that policy from the preserved private GLM authorization
and state without making a provider call:

```bash
python -m eval.prepare_phase4_together_capability_adjudication \
  eval/fixtures/preference_eval_phase4_together_capability_continuation_v2.json \
  eval/fixtures/preference_eval_phase4_together_capability_v2.json \
  eval/fixtures/preference_eval_phase4_together_v3.json \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/private_runs/phase4/together_glm_5_2_candidate_capability_authorization_v3.json \
  eval/private_runs/phase4/together_glm_5_2_candidate_capability_state_v3.json \
  eval/fixtures/preference_eval_phase4_together_capability_adjudication_v1.json

python -m eval.validate_phase4_capability_adjudication \
  eval/fixtures/preference_eval_phase4_together_capability_adjudication_v1.json \
  eval/fixtures/preference_eval_phase4_together_capability_continuation_v2.json \
  eval/fixtures/preference_eval_phase4_together_capability_v2.json \
  eval/fixtures/preference_eval_phase4_together_v3.json \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/private_runs/phase4/together_glm_5_2_candidate_capability_authorization_v3.json \
  eval/private_runs/phase4/together_glm_5_2_candidate_capability_state_v3.json
```

The continuation also predeclares the shared-failure interpretation for the
corrected interviewer protocol. If all three candidates successfully complete
the required tool phase and then fail strict validation in the separate final
phase, that uniform pattern is treated as evidence that Together's structured-
output implementation does not support the shared root-union schema. It
requires a new versioned schema/protocol and a fresh all-candidate capability
check; it must not be recorded as three model capability failures. A failure
from only one candidate or a nonuniform failure pattern does not trigger this
shared-harness disposition. The later no-spend aggregator must enforce this
rule from the exact candidate receipts.

Rebuild or validate the continuation with the ignored source attempts:

```bash
python -m eval.prepare_phase4_together_capability_continuation \
  eval/fixtures/preference_eval_phase4_together_capability_v1.json \
  eval/fixtures/preference_eval_phase4_together_capability_v2.json \
  eval/fixtures/preference_eval_phase4_together_v2.json \
  eval/fixtures/preference_eval_phase4_together_v3.json \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/fixtures/preference_eval_phase4_together_readiness_v2.json \
  eval/fixtures/preference_eval_phase4_together_readiness_v3.json \
  eval/fixtures/preference_eval_dev_v1.json \
  eval/fixtures/preference_eval_dev_session_v1.json \
  eval/fixtures/preference_eval_dev_semantic_map_v1.json \
  eval/fixtures/preference_eval_phase4_together_capability_continuation_v2.json \
  --attempt eval/private_runs/phase4/together_capability_authorization_v1.json \
    eval/private_runs/phase4/together_capability_state_v1.json \
  --attempt eval/private_runs/phase4/together_capability_authorization_v2.json \
    eval/private_runs/phase4/together_capability_state_v2.json

python -m eval.validate_phase4_capability_continuation \
  eval/fixtures/preference_eval_phase4_together_capability_continuation_v2.json \
  eval/fixtures/preference_eval_phase4_together_capability_v1.json \
  eval/fixtures/preference_eval_phase4_together_capability_v2.json \
  eval/fixtures/preference_eval_phase4_together_v2.json \
  eval/fixtures/preference_eval_phase4_together_v3.json \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/fixtures/preference_eval_phase4_together_readiness_v2.json \
  eval/fixtures/preference_eval_phase4_together_readiness_v3.json \
  eval/fixtures/preference_eval_dev_v1.json \
  eval/fixtures/preference_eval_dev_session_v1.json \
  eval/fixtures/preference_eval_dev_semantic_map_v1.json \
  --attempt eval/private_runs/phase4/together_capability_authorization_v1.json \
    eval/private_runs/phase4/together_capability_state_v1.json \
  --attempt eval/private_runs/phase4/together_capability_authorization_v2.json \
    eval/private_runs/phase4/together_capability_state_v2.json
```

The candidate authorizer and runner are
`python -m eval.authorize_phase4_together_candidate_capability` and
`python -m eval.run_phase4_together_candidate_capability`. Both require the
continuation, adjudication policy, historical and corrected plans, both
suite/readiness versions, the two ignored historical attempt pairs, and the
ignored provisional GLM authorization/state pair. Authorization
requires an exact five-call confirmation and the selected plan's exact maximum
spend; execution separately requires
`--execute-paid-candidate-capability` and repeats that exact amount. The
runner loads the API key only after every tracked/private binding, candidate
eligibility rule, adjudication rule, and manual amount has passed. Any future
invalid output first checkpoints the billed-call audit state and then must
persist its content-free diagnostic before returning the terminal failure.
These v3 authorization and execution commands are now audit-only.

Future candidate authorizations use
`preference_eval_phase4_adjudicated_candidate_authorization.v1`, a private
wrapper around the existing five-call authorization. It binds the exact
adjudication-policy and provisional-state hashes, and the resulting execution
state binds the wrapper hash rather than an unadjudicated authorization. The
historical GLM authorization and state remain on their original contracts.

The two comparison candidates then stopped at the evidence extractor with the
same content-free paths. That exposed a broader provider-contract defect rather
than a single-role prompt omission: 26 invariants across the five response
models were either schema-visible, prompt-visible, normalizable, or dependent
on the exact public request. The correction records that classification in a
machine-readable manifest, normalizes nonsemantic list order and repeated IDs,
and canonicalizes reversed fixed-ontology pairs with sign inversion. Exact
request-bound adapters now check all five roles inside the paid runtime, so
semantic failures become audited `invalid_output` outcomes rather than escaping
to a later validator.

The interviewer, evidence-extractor, and ontology-proposer wire contracts move
to v2. Direct and hybrid readout remain byte-identical v1 contracts, and their
four exact successful calls carry forward. Provider request v2 binds the
semantic-validator artifact hash and resolves it through the trusted local
registry. Because GLM's provisional ontology failure occurred under the same
hidden-invariant class, the corrected delta includes all three models: three
conversational roles for GLM and four each for GPT-OSS and Nemotron.

Bound v2 execution does not accept a caller-supplied registry or response
adapter. The provider runtime lazily resolves the exact module-owned registry,
whose duplicate identities cannot be overwritten. Validator implementation
identity `f077e2713b7ba0e6735f07e0ee367cc6d2203074841f78afda86ca450c009a09`
binds the manifest, emitted schemas, prompt suffixes, semantic constants,
reviewed validator/normalizer source, behavior-probe inventory, and the exact
Pydantic 2.13.4 / pydantic-core 2.46.4 parsing runtime. `requirements.txt`
pins Pydantic accordingly and the semantic module fails closed on a different
runtime before a request can be built.

The tracked
`preference_eval_phase4_together_capability_delta_v1.json`, hash
`25d286a8ceb16373e6868bb62bd81d3cf9b4cb0d2255f4ce02f66b2d4687f8e2`,
binds suite v4
`aea27b51ed24c8e4c11bfe0648a04ff0e29d25faeb519a9afa95e594a3d84283`,
readiness v4
`517e955976eaeec708cbedfadb46673038dcfd47e472407573997c4913ab1cd5`,
and capability plan v3
`2b78f3659e8a38e5ae74ea070172ea7eb9bc83a6c251a8bde2524573c6f12381`.
It carries four calls, reruns eleven, records 31,639 microusd already spent,
projects 52,140 microusd more, and caps new authorizations at 93,300 microusd.
The 124,939-microusd cumulative worst case remains below the original
150,000-microusd capability ceiling. Creating and validating the delta made no
provider call and spent nothing.

Rebuild the content-free delta from the ignored audits with
`python -m eval.prepare_phase4_together_capability_delta`; validate it with
`python -m eval.validate_phase4_capability_delta`. Both require the source
adjudication/continuation/plan/suite, all ignored capability states and
diagnostics, and the corrected plan/suite/readiness plus public development
inputs. The exact CLI surface is available through `--help`; stdout contains
only counts, hashes, and microusd totals.

The same private rebuild emits the tracked, content-free
`preference_eval_phase4_together_capability_delta_source_proof_v1.json`, hash
`58d65a797d832a39ae1c3e2f65cddff893a296e04fa88b07f97ab89a187d5b15`.
It binds the exact source-attempt, carry-forward, rerun, and semantic-manifest
hashes after the ignored audits validate, while omitting values, messages, and
context. Both the zero-spend validator and each paid candidate command require
this proof. The manual authorization binds its exact hash, so repartitioning a
carry and rerun cannot reuse an already approved execution boundary.

The reviewed v1 execution path used
`python -m eval.authorize_phase4_together_delta_candidate` and
`python -m eval.run_phase4_together_delta_candidate` with a fresh suite-v4
catalog preflight and explicit user approval. That suite-v4 path is now audit-
only. Its API-key loading and spend gates remain part of the preserved record;
new authorization must bind the selector-recovery v2 chain instead.

Candidate execution follows the first-occurrence order frozen by the delta.
For every candidate after the first, pass matching `--prior-authorization`
and `--prior-state` arguments in that order to both commands. The new
authorization binds the exact prefix of terminal state hashes and actual spend,
then proves prior actual spend plus every remaining worst-case reservation is
still within the original 150,000-microusd ceiling. Omitting an earlier attempt
or reordering candidates fails before the API key is loaded. A sent call whose
true bill exceeds its manual or provider cap is still checkpointed as a
content-free, auditable terminal state, cannot produce a receipt or resume,
and blocks every later candidate authorization.

The later GLM suite-v4 delta attempt added one more piece of evidence to that
history. Its extractor passed, and its interviewer made a valid tool call, but
the final response failed validation at the nested question field while trying
to reproduce the complete canonical question object. The content-free
diagnostic does not identify which nested invariant failed. The attempt spent
8,588 microusd. It is treated as a harness-inconclusive serialization burden
rather than evidence that the LLM cannot navigate preferences: choosing among
the exact candidates returned by the ranking tool is the research behavior,
while copying trusted canonical fields is not.

Suite v5 therefore uses an id-only selector and trusted local hydration
described above. The tracked suite, readiness, and capability-plan hashes are,
respectively,
`e97b6213955cf86d18da98d2d1300679b17ab773838d1ed10fcdb84b1f1de9b8`,
`f6ac45a3da3a4c14784aa6a9562ec1e3c62cd141aba214748b4f6a9fcbbaf5fd`,
and `e42b7d71c9ccfb07e6583313f07af60678178ef72eacf7182fa78255fa6f1fde`.
The chained
`preference_eval_phase4_together_selector_recovery_delta_v2.json`, hash
`0a09365d59e01694fbe33a3d4d3b6af335c35a01f0e45ae658467309bd53adb4`,
and its content-free source proof, hash
`c60ca23180894287f18f964e503f91ecb59a70a497f0d9a54fee075145be8261`,
bind both the reviewed v1 recovery chain and the later selector attempt.

Five exact successes carry forward: the four previously preserved readouts and
the later GLM extractor. Ten calls rerun: GLM's interviewer and ontology
proposer, plus extractor, hybrid readout, interviewer, and ontology proposer
for each comparison candidate. The chain records 40,227 microusd already
spent, projects 43,584 microusd more, caps new authorizations at 80,500
microusd, and bounds the cumulative worst case at 120,727 microusd under the
original 150,000-microusd ceiling. Building the v5 suite, readiness, plan,
delta, and proof made no inference call and spent nothing.

Rebuild and validate the content-free v2 chain from its ignored source audits
with `python -m eval.prepare_phase4_together_selector_recovery`; use `--help`
for the exact private source paths. Stdout is aggregate-only. The paid recovery
was run only after independent review and merge, a fresh suite-v5 catalog
preflight, and Ben's short-lived approvals for the exact candidate amounts.

Reviewers can recheck the complete tracked chain without access to any ignored
provider attempt with `python -m eval.validate_phase4_selector_recovery`; its
`--help` lists the 14 public artifact inputs. The command rejects a
`private_runs` path before reading it and prints only aggregate hashes, counts,
and microusd totals.

The candidate-specific authorization and execution commands above accept the
selector-recovery v2 plan/proof through explicit schema dispatch while keeping
the historical v1-only artifact loaders unchanged. They derive the exact
2/4/4-call candidate subsets from the reviewed v2 plan, bind the v2 semantics
manifest, and preserve the same ordered prior-state/spend-prefix checks.

If the reviewed id-only selector still fails, stop adding provider-specific
patches and reassess whether the remaining failure belongs to the provider, the
harness, or the intended research scope. A missing or invalid local hydration
context remains a harness error and cannot support a candidate verdict.
OpenRouter is deferred as a controlled
alternate-host diagnostic only; it is not part of qualification. Any such
diagnostic requires an exact model and endpoint pin, disabled fallbacks,
response-healing disabled, recorded routing provenance, and a separate reviewed
budget and authorization. A cross-host difference would be deployment evidence,
not a model-family result.

### Phase 4E Capability Aggregation

The suite-v5 recovery produced enough evidence to close the audited capability-
attempt sequence but not to construct the frozen v1 capability receipt.
GLM-5.2 and GPT-OSS 120B
each have exact five-role coverage after their carried and newly observed
successes are merged. They are **capability-passed**, not qualified. Nemotron 3
Ultra's exact Together deployment returned an HTTP 400 with no model output
returned, no provider-reported token usage, and no charge on its first recovery
call. That deployment is
**provider/deployment-inconclusive**; the event is not a model response, does
not reject the underlying model family, and is not compared as a quality
result. Its later recovery roles remain unattempted.

`eval/phase4_capability_aggregation.py` rebuilds that disposition from the
reviewed selector delta, the fresh catalog receipt, and all three exact ignored
authorization/state pairs. The tracked aggregate has canonical hash
`e9a0bd7141a9536041e3d242d0696daade3b3325c562cf1bd2a4b5f34dd8452e`;
its content-free private-source proof has hash
`de14bde9c424c530a62367ffec202d936f8180ec123db300996baa4956c9a156`.
The result covers all 15 corrected-plan coordinates: 5 carried successes, 6
new successes, 1 provider failure, and 3 roles not attempted after that
failure. Seven recovery calls were issued. Recovery spend was 10,815 microusd,
bringing cumulative capability spend to 51,042 microusd and leaving 98,958
microusd under the original 150,000-microusd ceiling. Aggregation itself made
zero provider calls and spent zero.

Rebuild the aggregate from ignored audits with
`python -m eval.prepare_phase4_capability_aggregation`; use `--help` for the
exact private source arguments. Review the tracked artifacts without private
access with `python -m eval.validate_phase4_capability_aggregation`; its
`--help` lists the 16 public inputs. Both commands print aggregate-only output,
and the public validator rejects any `private_runs` path before reading it.

This record deliberately has no capability-preflight receipt, qualification
authorization, selected model, or replacement candidate, so the reviewed
workflow remains blocked. This is not an unbypassable property of the old v1
validator: v1 checks a supplied receipt's hash and matrix but cannot replay its
private provider audit. `Phase4QualificationBundle.v1` also requires exactly
three complete candidate results. On this aggregate alone, qualification would
require a separately reviewed versioned scope amendment that preserves the
original three-candidate roster, identifies the two runnable deployments,
retains the Nemotron/Together result as inconclusive and not run in
qualification, forbids a post-hoc replacement, and defines both the
two-deployment authorization/result requirements and their frozen
comparison/selection rules. The one-call diagnostic below was completed before
that amendment was authored; its terminal evidence is bound into the later
scope proof. Any amended qualification runner must consume and source-validate
its scope as the actual gate; its result must not emit or be described as a v1
`Phase4QualificationBundle`.

### Phase 4E Nemotron HTTP Diagnostic Retry

The capability aggregate above is an immutable record of the evidence that
existed when it was built. The original Nemotron HTTP 400 response body was
not retained and cannot be reconstructed. The diagnostic-retry slice does not
rewrite that event. Instead, `eval/phase4_capability_retry.py` binds the exact
failed evidence-extractor request to one new call id with explicit retry
lineage.

Provider HTTP failures now produce a private, content-free diagnostic made
only from finite local categories: HTTP status, envelope shape, allowlisted
error type and code, and an allowlisted rejected top-level request field when
the provider supplies one. Raw response bodies, free-text error messages,
response headers, and unrecognized remote values are never retained. Unknown
values collapse to `unrecognized`; empty, non-JSON, and unstructured bodies
remain distinguishable without copying their contents. The diagnostic binds
the exact request and finalization hashes. A Together error envelope is not
guaranteed to supply an actionable parameter, so even a repeated 400 may
remain root-cause-inconclusive.

The tracked no-spend retry plan and source proof are:

- `preference_eval_phase4_together_capability_diagnostic_retry_v1.json`
- `preference_eval_phase4_together_capability_diagnostic_retry_source_proof_v1.json`

Their canonical hashes are respectively
`bb357556cd6b67a8f96d2a19e56d537bf511c3a9940dd1fb7072e10c98d0239b`
and
`3b0d3de1d85819ea7f233c923cee83600670e289f8bf50df9492695736a4b3cc`.

They preserve the original three-candidate roster and bind exactly one
Nemotron `evidence_extractor` replay under `retry_reserve`. The request-content
hash must equal the failed call's hash. The maximum authorization is 7,200
microusd, public development input is mandatory, participant content is
forbidden, and the runner cannot fall back to another deployment, continue to
Nemotron's remaining roles, select a model, or record a model-capability
rejection. Building and validating these artifacts makes no provider call and
spends nothing.

Use `python -m eval.validate_phase4_capability_diagnostic_retry` to review the
public plan/proof chain; `--help` lists the public inputs. After independent
review and merge, run a fresh zero-inference catalog preflight. Then create a
private approval with
`python -m eval.authorize_phase4_capability_diagnostic_retry`; the approval is
valid for at most 30 minutes and must name one call and exactly 7,200
microusd. Only then may
`python -m eval.run_phase4_capability_diagnostic_retry` issue the single paid
request with `--execute-paid-diagnostic-retry` and
`--confirm-max-spend-microusd 7200`. Private state stays under
`eval/private_runs/`.

The paid authorization is also single-use at the local runner boundary. Before
loading credentials or making a network request, the runner exclusively claims
the retry-plan hash in `eval/private_runs/`; the claim body binds the
authorization-bundle hash and the hashed private-relative state-output path.
A crash
before the send or an ambiguous delivery leaves that claim in place and
requires reconciliation plus a new reviewed approval; changing or deleting
the requested state-output path cannot make the same plan sendable again.

Interpret the terminal result without turning this deployment diagnostic into
a model verdict:

- Success shows that the first 400 was not a persistent rejection of this
  exact request. It does not authorize the three unattempted suffix roles.
- A repeated HTTP 400 establishes reproducible rejection by the exact Together
  deployment. Its finite diagnostic may identify a request field, but a
  generic envelope still leaves the harness-versus-deployment cause open.
- Another provider, transport, or availability failure remains inconclusive.
- A valid HTTP response with invalid structured output returns to the existing
  model-versus-validator adjudication path.
- Any other outcome stops for review. No fallback or automatic continuation is
  allowed.

The paid retry later returned an HTTP 500 `server_error` with no model output,
no provider-reported tokens, and no charge. Its disposition is
`provider_or_transport_inconclusive`. The single-use claim prevents another
send under that plan. This does not reject Nemotron's model family, but it does
leave the exact Together deployment unrunnable for the controlled
qualification.

### Phase 4E Two-Deployment Qualification Scope

The reviewed no-spend scope amendment is frozen in:

- `preference_eval_phase4_two_deployment_qualification_scope_v1.json`
- `preference_eval_phase4_two_deployment_qualification_scope_source_proof_v1.json`

Their canonical hashes are respectively
`42010288efd4dcba8bec9cd8aa9c4cef8c94d7e32e8e17b6b4a812e419708b46`
and
`d7dc3c435570c438cdd4c851273ed3a28f6c9a37180c095246cd393666836dff`.
The source proof fully revalidates the ignored retry authorization, terminal
state, source state, and fresh retry catalog before retaining only finite HTTP
metadata and hashes. It contains no request, response, value, message, or
conversation content.

The original GLM-5.2, GPT-OSS 120B, and Nemotron 3 Ultra roster remains frozen.
GLM and GPT-OSS are the two runnable deployments. Nemotron/Together remains
`provider_deployment_inconclusive_not_run`: it is not rejected, replaced,
ranked, or used to produce qualification quality metrics. The amendment was
created before any qualification metric was observed and made zero provider
calls with zero spend.

The original 456-entry readiness manifest is immutable. The amendment derives
its exact 304-entry GLM/GPT-OSS subsequence without renumbering source ordinals.
Ten exact successful capability calls already present in that manifest are
hash-bound carry-forwards and must not be replayed or reauthorized. A later
paid runner may send only the remaining 294 requests: 147 per deployment, with
14 interviewer, 14 extractor, 14 ontology-proposer, 126 direct-readout, and
126 hybrid-readout calls in total.

The complete two-deployment scope projects 1,466,671 microusd and has a
2,384,400-microusd all-envelope maximum. Removing the ten carried calls leaves
1,421,524 microusd projected and 2,297,400 microusd in exact new-call
reservations. With 51,042 microusd already spent on capability work, the
cumulative worst case is 2,348,442 microusd, leaving 1,651,558 microusd under
the frozen USD 4 qualification segment cap. The largest single reservation is
25,400 microusd, and sequential projected headroom is 2,502,034 microusd.

The amendment binds the exact legacy hard-failure list, ordered selection
criteria, and practical-equivalence bands. `provider_call_failure` is the sole
legacy hard-gate override. Its exact five underlying outcomes—provider error,
transport error, transport-contract error, token-bound exceeded, and
cancelled—pause the whole scope without selection pending a separately
reviewed continuation. All other candidate hard gates remain unchanged,
including required-role, structured-output, role-contract, interviewer-tool,
robustness-output, strict order/label, and projected-study-cost failures.
Selection requires a terminal result for both runnable deployment attempts, so
one failure cannot silently turn the run into a one-deployment contest. Both
attempts must reach a terminal disposition before selection: a provider,
transport, ambiguous-delivery, or harness pause blocks selection, while a
candidate-local substantive hard failure may stop that candidate early and
still permit selection of a fully completed, hard-gate-passing sibling. One
selected deployment still serves every LLM role.

The subsequent zero-spend execution slice makes those precommitments
enforceable. Its tracked plan is
`preference_eval_phase4_two_deployment_qualification_execution_v1.json`, with
canonical hash
`11b199fe5a7b2e312172b3c949a4f99c80ca58013a38be4ed76d98eb64c485a1`.
The plan preserves all 304 original readiness ordinals, marks the ten reviewed
capability successes as replay-forbidden carry records, and exposes exactly
294 provider calls to the paid boundary. The corresponding private carry
bundle is rebuilt from all five ignored capability source states and
revalidates every stored output against the current role adapter before it can
be authorized.

The qualification metric policy is now frozen before provider output exists:
only the six development responses in `choice` state contribute prediction
quality; canonical direct and hybrid readouts are reported separately and
then equally weighted; log loss uses a `1e-15` floor; exact top-probability
ties receive fractional credit; delegated-risk diagnostics use the complete
`[0.65, 0.75, 0.85, 0.95]` grid; and robustness remains disaggregated by
candidate, readout role, and measure before the frozen banded selection rule
is applied.

`phase4_qualification_runtime.py` defines a distinct exact-request
authorization and candidate-isolated progressive state rather than extending
the legacy three-candidate contracts. Every paid request must rebuild from its
source manifest entry, match its content hash and envelope reservation, remain
public-development-only, and fit the shared USD 4 qualification cap after the
51,042 microusd already spent. State is checkpointed after every call. A
substantive invalid output terminates only that candidate while the sibling is
still attempted; any provider, transport, ambiguous-delivery, shared-budget,
or local-harness condition blocks selection and requires review. New
interviewer tool results are locally replayed and hash-compared. The two
historical carried interviewer successes are accurately marked replay-
unverifiable because their tool transcripts were never retained.

The paid runner is one-shot. It acquires an fsynced claim keyed by the exact
execution-plan hash before loading the API key or constructing an HTTP client.
Any existing claim blocks automatic rerun even if a checkpoint was deleted;
interruption therefore requires manual provider-side reconciliation. The
runner uses the shared Together invocation mechanics, disables redirects and
environment proxy inheritance, and accepts no fallback, replacement, or
automatic retry.

Build the amendment from the exact ignored retry audit with
`python -m eval.prepare_phase4_qualification_scope_amendment`; use `--help` for
the complete source list. Public review uses
`python -m eval.validate_phase4_qualification_scope_amendment`, which rejects
`private_runs` inputs before reading them and prints aggregate-only counts,
costs, and hashes.

Build or revalidate the execution plan and private carry with
`python -m eval.prepare_phase4_two_deployment_qualification`; use `--help` for
the reviewed public chain and five ignored source-state paths. Paid execution
still requires this slice to be reviewed and merged, followed by a new
zero-inference catalog preflight and a fresh explicit approval for exactly 294
calls, 2,297,400 microusd of new reservations, and 2,348,442 microusd
cumulative worst-case qualification spend. The no-spend authorizer and paid
runner are respectively
`python -m eval.authorize_phase4_two_deployment_qualification` and
`python -m eval.run_phase4_two_deployment_qualification`; neither legacy live
authorization nor `Phase4QualificationBundle.v1` can enter this path.
After both candidate attempts reach a terminal state,
`python -m eval.assemble_phase4_two_deployment_qualification` revalidates the
full public chain, historical carry sources, exact authorization, durable
execution claim, and both private candidate audits before deriving metrics or
selection. It writes the content-bearing result only inside that ignored run
directory and confines the tracked aggregate receipt to
`eval/review_summaries/`; stdout and failures remain aggregate-only.

Use a new catalog-receipt name for this one-shot run; do not overwrite any
historical preflight. The following PowerShell template fixes the otherwise
long positional order and keeps every content-bearing artifact ignored. Run
it only after this slice is reviewed and merged. The authorizer is zero-spend;
the runner is the only paid command and can send at most 294 calls because a
frozen stop gate may terminate either candidate early.

```powershell
$public = @(
  'eval/fixtures/preference_eval_phase4_together_selector_recovery_delta_v2.json'
  'eval/fixtures/preference_eval_phase4_together_selector_recovery_source_proof_v2.json'
  'eval/fixtures/preference_eval_phase4_together_capability_delta_v1.json'
  'eval/fixtures/preference_eval_phase4_together_capability_delta_source_proof_v1.json'
  'eval/fixtures/preference_eval_phase4_together_capability_v3.json'
  'eval/fixtures/preference_eval_phase4_together_v4.json'
  'eval/fixtures/preference_eval_phase4_together_readiness_v4.json'
  'eval/fixtures/preference_eval_phase4_together_capability_v4.json'
  'eval/fixtures/preference_eval_phase4_together_v5.json'
  'eval/fixtures/preference_eval_phase4_together_readiness_v5.json'
  'eval/fixtures/preference_eval_phase4_robustness_v1.json'
  'eval/fixtures/preference_eval_dev_v1.json'
  'eval/fixtures/preference_eval_dev_session_v1.json'
  'eval/fixtures/preference_eval_dev_semantic_map_v1.json'
)
$scope = @(
  'eval/fixtures/preference_eval_phase4_two_deployment_qualification_scope_v1.json'
  'eval/fixtures/preference_eval_phase4_two_deployment_qualification_scope_source_proof_v1.json'
  'eval/fixtures/preference_eval_phase4_together_capability_aggregation_v1.json'
)
$scopeReview = @(
  'eval/fixtures/preference_eval_phase4_together_capability_aggregation_source_proof_v1.json'
  'eval/fixtures/preference_eval_phase4_together_capability_diagnostic_retry_v1.json'
  'eval/fixtures/preference_eval_phase4_together_capability_diagnostic_retry_source_proof_v1.json'
)
$sources = @(
  '--source-state'; 'eval/private_runs/phase4/together_glm_5_2_candidate_capability_state_v3.json'
  '--source-state'; 'eval/private_runs/phase4/together_glm_5_2_delta_state_v4_20260826.json'
  '--source-state'; 'eval/private_runs/phase4/together_glm_5_2_selector_recovery_state_v5_20260826.json'
  '--source-state'; 'eval/private_runs/phase4/together_gpt_oss_120b_candidate_capability_state_v1.json'
  '--source-state'; 'eval/private_runs/phase4/together_gpt_oss_120b_selector_recovery_state_v2_20260826.json'
)
$plan = 'eval/fixtures/preference_eval_phase4_two_deployment_qualification_execution_v1.json'
$carry = 'eval/private_runs/phase4/together_two_deployment_qualification_carry_v1.json'
$catalog = 'eval/private_runs/phase4/together_catalog_preflight_two_deployment_v1.json'
$authorization = 'eval/private_runs/phase4/together_two_deployment_qualification_authorization_v1.json'
$run = 'eval/private_runs/phase4/together_two_deployment_qualification_run_v1'

python -m eval.preflight_phase4_together `
  eval/fixtures/preference_eval_phase4_together_v5.json $catalog `
  --api-key-file .env.local --confirm-project-scoped-key `
  --confirm-training-sharing-disabled --confirm-default-nonstorage `
  --acknowledge-temporary-caching --execute-zero-spend

python -m eval.authorize_phase4_two_deployment_qualification `
  @public @scope $plan $carry $catalog $authorization @sources `
  --approve-call-count 294 --approve-max-spend-microusd 2297400 `
  --confirm-cumulative-authorized-max-microusd 2348442 `
  --confirm-public-development-only --confirm-no-participant-content `
  --confirm-no-automatic-retry --confirm-no-fallback-or-replacement `
  --valid-minutes 240

python -m eval.run_phase4_two_deployment_qualification `
  @public @scope $plan $carry $catalog $authorization $run @sources `
  --api-key-file .env.local --execute-paid-two-deployment-qualification `
  --confirm-call-count 294 --confirm-max-spend-microusd 2297400 `
  --confirm-cumulative-authorized-max-microusd 2348442

$resultTime = (Get-Date).ToUniversalTime().ToString('o')
python -m eval.assemble_phase4_two_deployment_qualification `
  @public @scope @scopeReview $plan $carry $authorization $catalog $run `
  "$run/private_result_v1.json" `
  eval/review_summaries/phase4_two_deployment_qualification_receipt_v1.json `
  @sources `
  --candidate-state "$run/together_glm_5_2_qualification_state_v1.json" `
  --candidate-state "$run/together_gpt_oss_120b_qualification_state_v1.json" `
  --qualification-id phase4_two_deployment_qualification_v1 `
  --receipt-id phase4_two_deployment_qualification_receipt_v1 `
  --created-at $resultTime
```

Use a new, previously unused output filename for every preflight. The command
does not treat an existing receipt as append-only and must never overwrite the
historical evidence bound by an earlier authorization.

The two candidate states and full result must share the run-specific
`eval/private_runs/` directory. Only the aggregate receipt directly under
`eval/review_summaries/` is tracked-eligible; it omits provider requests,
responses, parsed outputs, tool payloads, and participant content. The
assembler revalidates the durable claim, both exact terminal states, every
carried source chain, all 304 coordinate dispositions, and the frozen result
policy without making a provider request or spending money.
