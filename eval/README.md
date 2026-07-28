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
`development_only`.

## Contract Invariants

- Every persisted record declares a version.
- Unknown fields fail validation.
- Option IDs, display order, packet arguments, response fields, and source
  provenance are validated.
- `unsure` and `abstain` are distinct non-ballot states.
- Rankings may be partial and contain tied tiers.
- Quadratic allocations obey the same `votes²` credit cost used by the voting
  package.
- Prediction snapshots contain full option probabilities and an explicit
  evidence cutoff.
- A snapshot cannot reference future evidence or an already observed target
  response.
- Dynamic ontology versions cannot use evidence after their own cutoff.
- Canonical hashes depend on validated content, not source-file formatting.
- Frozen inputs remain replayable without PostgreSQL.

## Next

Phase 2 will add the prequential runner and primary metrics on top of these
contracts. The final standardized jurisdiction and 48-measure bank will be
authored and frozen only after the development runner and validators are
working.
