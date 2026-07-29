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

Phase 1 adds:

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
- Runs carry the fixture hash and must pass `validate_run_against_fixture`
  before scoring or replay.
- Dynamic ontology versions cannot use evidence after their own cutoff.
- Canonical hashes use Unicode-normalized, validated content rather than source
  formatting or unnormalized URL spelling.
- Frozen files and their manifests remain replayable without PostgreSQL.

## Evidence Layers And Prediction Fields

`EvidenceEvent` is the audit-level provenance record. Its `modality` says how
the observation entered the session. `preferences.types.Evidence` is the
model-level normalized pairwise or slider observation. Phase 2 adapters will
perform that explicit, auditable conversion; the similarly named records are
not interchangeable.

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

Raw human responses are private by default. Store local run records under
`eval/private_runs/`, which is ignored by Git, and use pseudonymous session
identifiers. Never commit a run containing raw responses or direct identifiers.
Public evaluation artifacts must omit raw response text and expose only the
approved derived metrics or redacted examples. The raw-response field is
bounded to 20,000 characters as a basic ingestion safeguard.

Formal consent, retention, deletion, and publication records are required
before any separately approved pilot. They are not implied by the Phase 1
development fixture or Ben's private self-case study.

## Next

Phase 2 will add the prequential runner and primary metrics on top of these
contracts. The final standardized jurisdiction and 48-measure bank will be
authored and frozen only after the development runner and validators are
working.
