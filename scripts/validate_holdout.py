"""
Out-of-sample check of the belief model's question generator on CES 2022.

The simulation draws new questions per topic from distributions fitted to
the 2024 items. If those distributions are right, questions the model never
saw should correlate within and between topics the way new draws do. This
compares the absolute tetrachoric correlations of CES 2022 items, grouped by
the same topics, with the implied correlations of question pairs drawn from
the fitted per-topic distributions.

CES 2022 Common Content (Harvard Dataverse doi:10.7910/DVN/PR4L8P, version 4,
CC0), file CCES22_Common_OUTPUT_vv_topost.csv (file id 10140882), cached at
.cache/ces/2022/. Only the five topics with a 2022 policy grid are covered;
the 2022 grids of bills and executive orders mix topics and are left out.
Some 2022 items repeat 2024 wording, so this is a check of the generator on
a different year's question set, not on entirely new wording.

Run through scripts/validate_beliefs.py (`holdout`).
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys

import numpy as np

from delegation.comparison.irt import implied_correlation, tetrachoric_matrix
from scripts.fit_ces_beliefs import ROOT

CSV_2022 = ROOT / ".cache/ces/2022/CCES22_Common_OUTPUT_vv_topost.csv"
MD5_2022 = "0819d70f07dbf2978e3df2496097773a"
SEED = 20261118

TOPICS_2022 = {
    "health_care": [f"CC22_327{c}" for c in "abcd"],
    "guns_policing": [f"CC22_330{c}" for c in "abcdef"] + [f"CC22_334{c}" for c in "abcdefgh"],
    "immigration": [f"CC22_331{c}" for c in "abcd"],
    "reproductive_rights": [f"CC22_332{c}" for c in "abcdef"],
    "environment_energy": [f"CC22_333{c}" for c in "abcde"],
}


def _load_2022() -> tuple[list[str], list[str], np.ndarray]:
    digest = hashlib.md5()
    with CSV_2022.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != MD5_2022:
        sys.exit(f"{CSV_2022} does not match its recorded MD5.")
    items = [(item, topic) for topic, ids in TOPICS_2022.items() for item in ids]
    code = {"1": 1.0, "2": 0.0}
    rows: list[list[float]] = []
    with CSV_2022.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            rows.append([code.get(row[item], np.nan) for item, _ in items])
    return [i for i, _ in items], [t for _, t in items], np.array(rows)


def _weighted_quantiles(values: np.ndarray, weights: np.ndarray) -> list[float]:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cumulative = (np.cumsum(w) - 0.5 * w) / w.sum()
    return [round(float(np.interp(q, cumulative, v)), 3) for q in (0.1, 0.25, 0.5, 0.75, 0.9)]


def _quantiles(values: np.ndarray) -> list[float]:
    return [round(float(q), 3) for q in np.quantile(values, [0.1, 0.25, 0.5, 0.75, 0.9])]


def holdout() -> dict[str, object]:
    """
    Absolute correlations of CES 2022 items against new questions drawn from
    the model, compared with matched weights: every topic counts equally
    within topics, and every topic pair counts equally between topics, on
    both sides. (Unmatched, guns and policing supplies 91 of the 128
    observed within-topic pairs while the model side weights topics
    equally.) Results per topic are reported too. Development evidence: this
    check helped motivate version 2 of the fit, so it is not an independent
    validation.
    """
    ids, topics, y = _load_2022()
    observed = np.abs(tetrachoric_matrix(y))
    raw = json.loads((ROOT / "delegation/data/beliefs_ces2024_v2.json").read_text())
    k = int(raw["dimensions"])
    # The benchmark population's covariance: residents vary around their
    # district's mean (within) and districts vary around the nation
    # (between), not the identity of the item fit's scale (second review)
    population = raw["population"]
    cov = np.array(population["within_cov"]) + np.array(population["between_cov"])
    rng = np.random.default_rng(SEED)
    names = sorted(TOPICS_2022)

    def draw(topic: str, n: int) -> np.ndarray:
        spec = raw["topics"][topic]
        params = rng.multivariate_normal(spec["mean"], spec["cov"], size=n, method="eigh")
        return params[:, :k]

    def model_abs_r(first: str, second: str, n: int) -> np.ndarray:
        a, c = draw(first, n), draw(second, n)
        return np.abs(np.diag(implied_correlation(np.vstack([a, c]), cov)[:n, n:]))

    topic_of = np.array(topics)
    upper = np.triu_indices(len(ids), 1)
    pair_first, pair_second = topic_of[upper[0]], topic_of[upper[1]]
    values = observed[upper]
    same = pair_first == pair_second

    per_topic: dict[str, object] = {}
    within_obs_w = np.zeros(values.size)
    for t in names:
        mask = same & (pair_first == t)
        within_obs_w[mask] = 1.0 / mask.sum() if mask.any() else 0.0
        per_topic[t] = {
            "observed_pairs": int(mask.sum()),
            "observed_median_abs_r": round(float(np.median(values[mask])), 3) if mask.any() else None,
            "model_median_abs_r": round(float(np.median(model_abs_r(t, t, 2000))), 3),
        }
    between_obs_w = np.zeros(values.size)
    for x in range(len(names)):
        for z in range(x + 1, len(names)):
            mask = ((pair_first == names[x]) & (pair_second == names[z])) | (
                (pair_first == names[z]) & (pair_second == names[x])
            )
            between_obs_w[mask] = 1.0 / mask.sum() if mask.any() else 0.0
    within_model = np.concatenate([model_abs_r(t, t, 2000) for t in names])
    between_model = np.concatenate(
        [model_abs_r(names[x], names[z], 1000) for x in range(len(names)) for z in range(x + 1, len(names))]
    )
    return {
        "items": len(ids),
        "respondents": int(y.shape[0]),
        "evidence": "development: motivated version 2; not an independent validation",
        "weighting": "each topic (within) and each topic pair (between) weighted equally on both sides",
        "model_population": "positions with the fitted within- plus between-district covariance",
        "within_topic": {
            "observed_pairs": int(same.sum()),
            "observed_abs_r_quantiles": _weighted_quantiles(values[same], within_obs_w[same]),
            "model_abs_r_quantiles": _quantiles(within_model),
        },
        "between_topic": {
            "observed_pairs": int((~same).sum()),
            "observed_abs_r_quantiles": _weighted_quantiles(values[~same], between_obs_w[~same]),
            "model_abs_r_quantiles": _quantiles(between_model),
        },
        "per_topic_within": per_topic,
        "quantiles": "10th, 25th, 50th, 75th, 90th percentiles of |r|",
    }
