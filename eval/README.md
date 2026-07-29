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
default to 65%, 75%, 85%, and 95%; no product default is selected. Settledness
treats a stable choice or stable deliberate abstention as settled, while unsure
and tentative responses are unsettled.

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
- Exact probability ties resolve by frozen option display order.
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

Phase 3 will author and freeze the final standardized jurisdiction,
48-measure bank, and retest variants. The Phase 2 runner deliberately stops
before classical-model adapters, direct LLM integration, the final bank, or a
human-facing UI.
