"""
Fit the belief model for demo 5's comparison to the CES 2024 Common Content.

The raw file is not in the repo. Download it from Harvard Dataverse
(doi:10.7910/DVN/X11EP6, version 9, file id 12050325) to
.cache/ces/2024/CCES24_Common_OUTPUT_vv_topost_final.csv; its MD5 is
checked before anything is read.

Commands (no network use):

    python -m scripts.fit_ces_beliefs choose-k   # held-out score for K = 1..6
    python -m scripts.fit_ces_beliefs fit --k K  # final fit, writes the JSON

Only aggregates are written: item parameters, the topic map and per-topic
distributions, district means and the within-district covariance, the
held-out scores and convergence diagnostics. No respondent-level value
leaves the cache. Design: prompts/demo-5-liquid-democracy.md, "Model form".
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from delegation.comparison.irt import (
    ItemParameters,
    PositionConfig,
    estimate_items,
    holdout_log_scores,
    holdout_mask,
    implied_correlation,
    sample_positions,
    split_rhat,
    support_rates,
)

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / ".cache/ces/2024/CCES24_Common_OUTPUT_vv_topost_final.csv"
CSV_MD5 = "b740b9305fee50e1a34656b513f55c57"
CSV_SHA256 = "8a5e9fbc982961ad910bad9aed8d521fa0a85e85cded43fb308cce0ab22ba5d9"
OUT_DIR = ROOT / ".cache/ces/fits"
BELIEFS_PATH = ROOT / "delegation/data/beliefs_ces2024_v1.json"

SOURCE = {
    "dataset": "Cooperative Election Study Common Content, 2024",
    "doi": "10.7910/DVN/X11EP6",
    "dataverse_version": 9,
    "license": "CC0 1.0",
    "file": "CCES24_Common_OUTPUT_vv_topost_final.csv",
    "dataverse_file_id": 12050325,
    "md5": CSV_MD5,
    "sha256": CSV_SHA256,
}

# Topic assignment approved 2026-11-16; short labels paraphrase the guide.
ITEMS: tuple[tuple[str, str, str], ...] = (
    ("CC24_321a", "guns_policing", "Ban assault rifles"),
    ("CC24_321b", "guns_policing", "Make concealed-carry permits easier to obtain"),
    ("CC24_321c", "guns_policing", "Background checks on all gun sales"),
    ("CC24_321d", "guns_policing", "10% more police, fewer funds elsewhere"),
    ("CC24_321e", "guns_policing", "10% fewer police, more funds elsewhere"),
    ("CC24_321f", "guns_policing", "Mental health and school safety package"),
    ("CC24_323a", "immigration", "Legal status for long-resident workers"),
    ("CC24_323b", "immigration", "More border patrols"),
    ("CC24_323c", "immigration", "Build a border wall"),
    ("CC24_323d", "immigration", "Permanent status for Dreamers"),
    ("CC24_340f", "immigration", "Deny asylum to illegal border crossers (bill)"),
    ("CC24_324a", "reproductive_rights", "Always allow abortion as a choice"),
    ("CC24_324b", "reproductive_rights", "Abortion only for rape, incest or life"),
    ("CC24_324c", "reproductive_rights", "Make abortion illegal in all cases"),
    ("CC24_324d", "reproductive_rights", "Expand access to abortion"),
    ("CC24_340a", "reproductive_rights", "Protect access to contraceptives (bill)"),
    ("CC24_340b", "reproductive_rights", "Protect access to abortion services (bill)"),
    ("CC24_326a", "environment_energy", "EPA may regulate CO2"),
    ("CC24_326b", "environment_energy", "20% renewable electricity requirement"),
    ("CC24_326c", "environment_energy", "Stronger Clean Air/Water enforcement, even at job cost"),
    ("CC24_326d", "environment_energy", "Increase fossil fuel production"),
    ("CC24_326e", "environment_energy", "Halt new federal oil and gas leases"),
    ("CC24_326f", "environment_energy", "Prevent bans on gas stoves"),
    ("CC24_328a", "housing", "Relax zoning for apartments and condos"),
    ("CC24_328b", "housing", "Tax incentives for low-income housing"),
    ("CC24_328c", "health_care", "Medicaid work requirement"),
    ("CC24_328d", "health_care", "Repeal the Affordable Care Act"),
    ("CC24_328e", "health_care", "Expand Medicaid eligibility"),
    ("CC24_341a", "taxes_spending", "Extend the 2017 tax cuts"),
    ("CC24_341b", "taxes_spending", "Raise the corporate tax rate to 28%"),
    ("CC24_341c", "taxes_spending", "Higher rates above $400,000"),
    ("CC24_341d", "taxes_spending", "$150bn a year on infrastructure"),
    ("CC24_323f", "taxes_spending", "Forgive up to $20,000 of student debt"),
    ("CC24_340c", "civil_rights_liberties", "Federal recognition of same-sex and interracial marriage (bill)"),
    ("CC24_340d", "civil_rights_liberties", "Ban TikTok unless sold (bill)"),
    ("CC24_340e", "civil_rights_liberties", "Renew post-9/11 surveillance programs (bill)"),
)

HOLDOUT_SHARE = 0.10
HOLDOUT_SEED = 20261116
K_RANGE = range(1, 7)


@dataclass(frozen=True)
class Survey:
    """The answers and the columns the fit needs, in file row order."""

    y: np.ndarray  # [respondent, item], 1 support, 0 oppose, NaN missing
    weight: np.ndarray
    district: tuple[str, ...]  # "state-district", "" when unknown


def _check_file(path: Path) -> None:
    if not path.exists():
        sys.exit(f"Missing {path}. Download it as described in this script's docstring.")
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != CSV_MD5:
        sys.exit(f"{path} does not match the recorded MD5 {CSV_MD5}.")


def load_survey(path: Path = CSV_PATH) -> Survey:
    """Read the 36 items, the common weight and the district of every row."""
    _check_file(path)
    code = {"1": 1.0, "2": 0.0}
    rows: list[list[float]] = []
    weights: list[float] = []
    districts: list[str] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            rows.append([code.get(row[item], np.nan) for item, _, _ in ITEMS])
            w = row["commonweight"]
            weights.append(float(w) if w not in ("", "NA") else np.nan)
            state, cd = row["inputstate"], row["cdid119"]
            districts.append(f"{state}-{cd}" if state not in ("", "NA") and cd not in ("", "NA") else "")
    return Survey(np.array(rows), np.array(weights), tuple(districts))


def _hidden(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mask = holdout_mask(y, HOLDOUT_SHARE, HOLDOUT_SEED)
    hidden = y.copy()
    hidden[mask] = np.nan
    return hidden, mask


def choose_k() -> None:
    """
    Held-out log score for K = 1..6 on every respondent: a seeded 10% of
    answered cells is hidden, items and positions are estimated from the
    rest, and each hidden answer is scored by its posterior predictive
    probability. The chosen K is the smallest within one paired standard
    error of the best.
    """
    survey = load_survey()
    hidden, mask = _hidden(survey.y)
    results: dict[int, dict[str, float]] = {}
    scores: dict[int, np.ndarray] = {}
    for k in K_RANGE:
        started = time.time()
        items, factors, _ = estimate_items(hidden, k)
        positions = sample_positions(hidden, items, PositionConfig(seed=k))
        cell = holdout_log_scores(survey.y, mask, items, positions)
        scores[k] = cell
        results[k] = {
            "mean_log_score": float(cell.mean()),
            "tetrachoric_rmsr": factors.rmsr,
            "capped_items": len(factors.capped),
            "seconds": round(time.time() - started, 1),
        }
        print(k, results[k], flush=True)
    best = max(scores, key=lambda k: float(scores[k].mean()))
    respondent = np.nonzero(mask)[0]
    for k in K_RANGE:
        diff = scores[best] - scores[k]
        results[k]["diff_from_best"] = float(diff.mean())
        results[k]["se_diff"] = float(diff.std(ddof=1) / np.sqrt(diff.size))
        # Reported only: cells from one respondent are not independent, so
        # a standard error clustered by respondent is the more honest one
        totals = np.bincount(respondent, weights=diff)
        counts = np.bincount(respondent)
        used = counts > 0
        resid = totals[used] - counts[used] * diff.mean()
        m = int(used.sum())
        results[k]["se_diff_clustered"] = float(
            np.sqrt(m / (m - 1) * (resid**2).sum()) / diff.size
        )
    chosen = min(
        k for k in K_RANGE if results[k]["diff_from_best"] <= results[k]["se_diff"]
    )
    summary = {
        "holdout_share": HOLDOUT_SHARE,
        "holdout_seed": HOLDOUT_SEED,
        "heldout_cells": int(mask.sum()),
        "rule": "smallest K within one paired standard error of the best",
        "best_k": best,
        "chosen_k": chosen,
        "by_k": {str(k): v for k, v in results.items()},
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "choose_k.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"best_k": best, "chosen_k": chosen}))


def _topic_distributions(items: ItemParameters) -> tuple[dict[str, object], float]:
    """
    Per-topic normal distributions over (a, b) for drawing new questions.

    Each topic's covariance is shrunk toward the covariance pooled within
    all topics: (n_t S_t + kappa S_pool) / (n_t + kappa), with kappa the
    length of the (a, b) vector, so a topic with two items leans mostly on
    the pooled spread.
    """
    params = np.column_stack([items.loadings, items.intercepts])
    topics = sorted({topic for _, topic, _ in ITEMS})
    index = {
        t: [i for i, (_, topic, _) in enumerate(ITEMS) if topic == t] for t in topics
    }
    deviations = np.vstack(
        [params[rows] - params[rows].mean(axis=0) for rows in index.values()]
    )
    pooled = deviations.T @ deviations / (len(ITEMS) - len(topics))
    kappa = float(params.shape[1])
    out: dict[str, object] = {}
    for t, rows in index.items():
        block = params[rows]
        n = len(rows)
        centred = block - block.mean(axis=0)
        sample = centred.T @ centred / n
        cov = (n * sample + kappa * pooled) / (n + kappa)
        out[t] = {
            "items": [ITEMS[i][0] for i in rows],
            "mean": block.mean(axis=0).tolist(),
            "cov": cov.tolist(),
        }
    return out, kappa


def _districts(
    positions: np.ndarray, weight: np.ndarray, district: Sequence[str]
) -> dict[str, object]:
    """
    District means of theta, shrunk toward the national mean (empirical
    Bayes), and the pooled within-district covariance, from posterior draws
    of every respondent's position (plausible values), weighted by
    commonweight. Respondents without a district or weight are left out.
    """
    keys = np.array(district)
    usable = (keys != "") & np.isfinite(weight) & (weight > 0)
    keys, w = keys[usable], weight[usable]
    # Kept in float32; each district's slice is widened as it is used
    draws = positions[:, usable, :]
    names = sorted(set(keys.tolist()))
    k = draws.shape[2]
    national = np.zeros(k)
    for d in range(draws.shape[0]):
        national += w @ draws[d].astype(np.float64)
    national /= w.sum() * draws.shape[0]
    raw = np.zeros((len(names), k))
    posterior_var = np.zeros((len(names), k, k))
    within = np.zeros((k, k))
    n_eff = np.zeros(len(names))
    counts = np.zeros(len(names), dtype=int)
    for gi, g in enumerate(names):
        rows = np.flatnonzero(keys == g)
        wg = w[rows]
        block = draws[:, rows, :].astype(np.float64)
        per_draw = np.einsum("n,dnk->dk", wg, block) / wg.sum()
        raw[gi] = per_draw.mean(axis=0)
        posterior_var[gi] = np.atleast_2d(np.cov(per_draw.T, ddof=1)) / draws.shape[0]
        centred = block - per_draw[:, None, :]
        within += np.einsum("n,dni,dnj->ij", wg, centred, centred) / draws.shape[0]
        n_eff[gi] = wg.sum() ** 2 / (wg**2).sum()
        counts[gi] = rows.size
    within /= w.sum()
    # Sampling covariance of each raw district mean: respondents drawn from
    # the district, plus the Monte Carlo error of averaging the draws
    sampling = within[None, :, :] / n_eff[:, None, None] + posterior_var
    spread = np.atleast_2d(np.cov((raw - national).T, ddof=1))
    between = spread - sampling.mean(axis=0)
    values, vectors = np.linalg.eigh(between)
    between = vectors @ np.diag(np.maximum(values, 0.0)) @ vectors.T
    out_districts: dict[str, object] = {}
    for gi, g in enumerate(names):
        gain = between @ np.linalg.inv(between + sampling[gi])
        shrunk = national + gain @ (raw[gi] - national)
        out_districts[g] = {
            "respondents": int(counts[gi]),
            "effective_respondents": round(float(n_eff[gi]), 1),
            "mean": [round(float(x), 6) for x in shrunk],
        }
    return {
        "national_mean": national.tolist(),
        "within_cov": within.tolist(),
        "between_cov": between.tolist(),
        "districts": out_districts,
    }


def fit(k: int) -> None:
    """The final fit at K, written to the beliefs JSON."""
    survey = load_survey()
    started = time.time()
    items, factors, observed_corr = estimate_items(survey.y, k)
    chains = [
        sample_positions(survey.y, items, PositionConfig(seed=100 + c)) for c in (1, 2)
    ]
    rng = np.random.default_rng(np.random.SeedSequence([HOLDOUT_SEED, 3]))
    probe = rng.choice(survey.y.shape[0], size=2000, replace=False)
    rhat = split_rhat(
        np.stack([c[:, probe, :] for c in chains]).astype(np.float64)
    ).ravel()
    positions = np.concatenate(chains, axis=0)
    topics, kappa = _topic_distributions(items)
    population = _districts(positions, survey.weight, survey.district)
    implied = implied_correlation(items.loadings)
    upper = np.triu_indices(len(ITEMS), 1)
    observed_rate = np.nanmean(survey.y, axis=0)
    choose_path = OUT_DIR / "choose_k.json"
    choose = json.loads(choose_path.read_text()) if choose_path.exists() else None
    out = {
        "version": "beliefs.ces2024.v1",
        "model": (
            "multidimensional probit item response: support when "
            "a.theta + b + e > 0, theta ~ N(0, I), e ~ N(0, 1)"
        ),
        "estimation": {
            "items": (
                "tetrachoric correlations + unweighted least squares factor "
                "fit, converted to (a, b)"
            ),
            "positions": "Gibbs sampling with items fixed",
            "position_sampler": {
                "iterations": 1200,
                "burn_in": 200,
                "thin": 5,
                "chains": 2,
                "seeds": [101, 102],
            },
            "item_weights": "unweighted",
            "population_weights": "commonweight",
        },
        "source": SOURCE,
        "dimensions": k,
        "choose_k": choose,
        "fit_checks": {
            "tetrachoric_rmsr": factors.rmsr,
            "max_abs_tetrachoric_residual": float(
                np.abs((observed_corr - implied)[upper]).max()
            ),
            "capped_items": [ITEMS[i][0] for i in factors.capped],
            "max_abs_support_rate_error": float(
                np.abs(
                    support_rates(items.loadings, items.intercepts) - observed_rate
                ).max()
            ),
            "position_rhat": {
                "median": float(np.median(rhat)),
                "p99": float(np.quantile(rhat, 0.99)),
                "max": float(rhat.max()),
                "probe_respondents": int(probe.size),
            },
        },
        "items": [
            {
                "id": item,
                "topic": topic,
                "label": label,
                "a": [round(float(x), 6) for x in items.loadings[i]],
                "b": round(float(items.intercepts[i]), 6),
                "observed_support": round(float(observed_rate[i]), 6),
            }
            for i, (item, topic, label) in enumerate(ITEMS)
        ],
        "topics": topics,
        "topic_shrinkage_kappa": kappa,
        "population": population,
    }
    BELIEFS_PATH.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out["fit_checks"], indent=2))
    print(f"wrote {BELIEFS_PATH.relative_to(ROOT)} in {time.time() - started:.0f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("choose-k")
    fit_parser = sub.add_parser("fit")
    fit_parser.add_argument("--k", type=int, required=True)
    args = parser.parse_args()
    if args.command == "choose-k":
        choose_k()
    else:
        fit(args.k)


if __name__ == "__main__":
    main()


