"""Cross-demo evaluation harness.

The preference demo currently has two deliberately separate tracks:

- fixed-bank synthetic model/acquisition comparisons, entered through
  ``eval.run_preference_eval``; and
- versioned human-measure contracts and development fixtures, validated
  through ``eval.validate_fixture``; and
- deterministic prequential human-measure replay, entered through
  ``eval.run_human_measure_eval``.

The human-measure track stays file-backed so a published result can be replayed
without a database snapshot.
"""
