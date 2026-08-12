# Evaluation Harness

`eval/` contains reproducible evaluation code shared by the demos. The
preference-model work currently has two separate tracks.

## Fixed-Bank Synthetic Track

The existing harness compares Gaussian and Bradley-Terry preference models
under random and max-variance acquisition policies. Synthetic personas have
known latent utilities, and held-out pairs never enter acquisition.

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

Later Phase 4 work will add provider-neutral interviewer tools, confirmed
conversational evidence, authored/direct-LLM/hybrid prediction readouts, and
prompt/order robustness. LLM predictions will retain private supporting-
evidence IDs and unsupported-assumption flags. Repeated calls are sensitivity
or Monte Carlo diagnostics, not independent human observations. The Phase 2
runner still deliberately stops before those implementations or a human-facing
UI.
