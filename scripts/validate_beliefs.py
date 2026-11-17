"""
Validation patterns for demo 5's belief model, declared in the research
protocol (prompts/demo-5-liquid-democracy.md, "Checks before the primary
run"). Each compares the fitted model with data:

  representative  How often CES 2024 respondents agree with their own House
                  member on the bills members actually voted on, against
                  how often the simulation's representative agrees with its
                  residents on the same items.
  districts       How much item support rates differ between real
                  congressional districts, against the same quantity in
                  samples of the same size drawn from the model.
  moderates       Ahler and Broockman's pattern: respondents moderate
                  overall who are consistent within topics but mixed across
                  them, in data and in the model.
  holdout         Correlations between CES 2022 items the model never saw,
                  against those of new questions drawn from its per-topic
                  distributions (development evidence).
  selection       With real respondents: a resolver chosen from answers to
                  35 items, scored on the held-out 36th
                  (scripts/validate_selection.py).

Reads cached files only (CES 2024, CES 2022, Voteview); writes a JSON
summary to .cache/ces/validation.json and prints it.

    python -m scripts.validate_beliefs [representative|districts|moderates|holdout|all]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy.special import ndtr

from delegation.comparison.beliefs import load_beliefs
from delegation.comparison.irt import tetrachoric_matrix
from scripts.fit_ces_beliefs import ITEMS, ROOT, load_survey

VOTEVIEW = ROOT / ".cache/voteview"
OUT = ROOT / ".cache/ces/validation.json"
SEED = 20261117

FIPS = {
    1: "AL", 2: "AK", 4: "AZ", 5: "AR", 6: "CA", 8: "CO", 9: "CT", 10: "DE",
    11: "DC", 12: "FL", 13: "GA", 15: "HI", 16: "ID", 17: "IL", 18: "IN",
    19: "IA", 20: "KS", 21: "KY", 22: "LA", 23: "ME", 24: "MD", 25: "MA",
    26: "MI", 27: "MN", 28: "MS", 29: "MO", 30: "MT", 31: "NE", 32: "NV",
    33: "NH", 34: "NJ", 35: "NM", 36: "NY", 37: "NC", 38: "ND", 39: "OH",
    40: "OK", 41: "OR", 42: "PA", 44: "RI", 45: "SC", 46: "SD", 47: "TN",
    48: "TX", 49: "UT", 50: "VT", 51: "VA", 53: "WA", 54: "WV", 55: "WI",
    56: "WY",
}

# CES 2024 bills that had a House roll call in the 118th Congress, matched
# by Voteview roll number. Support on the CES item is a yea.
BILLS = {
    "CC24_340d": (804, "H.R. 7521, TikTok divest-or-ban, suspension passage"),
    "CC24_340e": (837, "H.R. 7888, FISA section 702 reauthorization, passage"),
    "CC24_340f": (208, "H.R. 2, Secure the Border Act (asylum limits), passage"),
}


def _model_items() -> tuple[np.ndarray, np.ndarray]:
    raw = json.loads((ROOT / "delegation/data/beliefs_ces2024_v2.json").read_text())
    a = np.array([item["a"] for item in raw["items"]])
    b = np.array([item["b"] for item in raw["items"]])
    return a, b


def _district_mean(model, key: str, rng: np.random.Generator) -> np.ndarray:
    """A draw of one district's mean from its posterior, as the simulation does."""
    return np.asarray(
        rng.multivariate_normal(model.district_means[key], model.district_covs[key], method="eigh")
    )


def _member_votes() -> dict[int, dict[tuple[str, int], bool]]:
    """Roll number -> (state, district) -> voted yea, for yea or nay votes."""
    members: dict[str, tuple[str, int]] = {}
    with (VOTEVIEW / "H118_members.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["chamber"] == "House":
                members[row["icpsr"]] = (row["state_abbrev"], int(row["district_code"]))
    wanted = {roll for roll, _ in BILLS.values()}
    out: dict[int, dict[tuple[str, int], bool]] = {roll: {} for roll in wanted}
    with (VOTEVIEW / "H118_votes.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            roll = int(row["rollnumber"])
            code = int(float(row["cast_code"]))
            if roll in wanted and code in (1, 6) and row["icpsr"] in members:
                out[roll][members[row["icpsr"]]] = code == 1
    return out


def _district_of(key: str) -> tuple[str, int] | None:
    state, cd = key.split("-")
    abbrev = FIPS.get(int(state))
    return (abbrev, int(cd)) if abbrev else None


def _districts_118() -> list[str]:
    """
    Each respondent's district in the 118th Congress (`cdid118`), which is
    what the 118th-Congress roll calls must be joined to; the fit itself
    uses `cdid119`, the districts current when the survey was taken.
    1,973 of the 60,000 respondents have different numbers in the two.
    """
    keys: list[str] = []
    path = ROOT / ".cache/ces/2024/CCES24_Common_OUTPUT_vv_topost_final.csv"
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            state, cd = row["inputstate"], row["cdid118"]
            keys.append(f"{state}-{cd}" if state not in ("", "NA") and cd not in ("", "NA") else "")
    return keys


def representative() -> dict[str, object]:
    """
    Respondent-member agreement in data and in the model, per bill.

    A limited check: three bills on two topics, the only CES 2024 bills with
    a House roll call in the 118th Congress. The data side counts only
    respondents whose member cast a yea or nay. The model side runs a
    district election with turnout drawn as in the simulation (uniform
    between 0.3 and 0.9 per resident).
    """
    survey = load_survey()
    district_118 = _districts_118()
    votes = _member_votes()
    index = {item: i for i, (item, _, _) in enumerate(ITEMS)}
    model = load_beliefs()
    a, b = _model_items()
    rng = np.random.default_rng(SEED)
    chol = np.linalg.cholesky(model.within_cov)
    results: dict[str, object] = {}
    for item, (roll, label) in BILLS.items():
        j = index[item]
        agree = weight = 0.0
        for i, key in enumerate(district_118):
            answer = survey.y[i, j]
            w = survey.weight[i]
            if not key or np.isnan(answer) or not np.isfinite(w):
                continue
            district = _district_of(key)
            by_district = votes[roll]
            # At-large states are district 1 in CES and 1 or 0 in Voteview
            yea = by_district.get(district) if district else None
            if yea is None and district:
                yea = by_district.get((district[0], 0))
            if yea is None:
                continue
            agree += w * float((answer == 1.0) == yea)
            weight += w
        # The model: in every real district, 100 residents, three random
        # candidates, plurality on the closest platform among residents who
        # turn out, and the winner's sincere vote on this item
        sim_agree = sim_weight = 0.0
        for key, mean in model.district_means.items():
            n = model.district_respondents[key]
            for _ in range(5):
                centre = _district_mean(model, key, rng)
                theta = centre + rng.standard_normal((100, model.dimensions)) @ chol.T
                candidates = rng.choice(100, size=3, replace=False)
                distance = np.linalg.norm(
                    theta[:, None, :] - theta[candidates][None, :, :], axis=2
                )
                turns_out = rng.random(100) < rng.uniform(0.3, 0.9, size=100)
                tally = np.bincount(np.argmin(distance[turns_out], axis=1), minlength=3)
                rep = candidates[int(np.argmax(tally))]
                eta = theta @ a[j] + b[j]
                sincere = eta + rng.standard_normal(100) > 0
                rep_yes = sincere[rep]
                others = np.delete(np.arange(100), rep)
                sim_agree += n * float(np.mean(sincere[others] == rep_yes))
                sim_weight += n
        results[item] = {
            "bill": label,
            "voteview_roll": roll,
            "observed_agreement": round(agree / weight, 4),
            "model_agreement": round(sim_agree / sim_weight, 4),
        }
    return {
        "bills": results,
        "scope": "three bills on two topics; respondents whose member cast a yea or nay",
        "districts": "cdid118, matching the 118th-Congress roll calls",
    }


def districts() -> dict[str, object]:
    """
    Between-district standard deviation of item support rates: observed
    (unweighted support per district) against the model (the same district
    sizes, residents drawn from the fitted district means and within-district
    covariance). Both include sampling noise of the same size, so their
    ratio compares like with like.
    """
    survey = load_survey()
    model = load_beliefs()
    a, b = _model_items()
    keys = np.array(survey.district)
    rng = np.random.default_rng(SEED + 1)
    chol = np.linalg.cholesky(model.within_cov)
    names = [g for g in sorted(set(keys.tolist())) if g and g in model.district_means]
    observed = np.zeros((len(names), len(ITEMS)))
    simulated = np.zeros((len(names), len(ITEMS)))
    for gi, g in enumerate(names):
        rows = np.flatnonzero(keys == g)
        # Unweighted, as the hierarchical model is fitted: weighting adds
        # sampling noise to the observed side only and would inflate it
        observed[gi] = np.nanmean(survey.y[rows], axis=0)
        theta = _district_mean(model, g, rng) + rng.standard_normal((rows.size, model.dimensions)) @ chol.T
        eta = theta @ a.T + b
        simulated[gi] = ((eta + rng.standard_normal(eta.shape)) > 0).mean(axis=0)
    obs_sd = observed.std(axis=0, ddof=1)
    sim_sd = simulated.std(axis=0, ddof=1)
    ratio = sim_sd / obs_sd
    return {
        "districts": len(names),
        "median_ratio_model_to_observed": round(float(np.median(ratio)), 3),
        "ratio_range": [round(float(ratio.min()), 3), round(float(ratio.max()), 3)],
        "mean_observed_sd": round(float(obs_sd.mean()), 4),
        "mean_model_sd": round(float(sim_sd.mean()), 4),
        "by_item": {item: round(float(r), 3) for (item, _, _), r in zip(ITEMS, ratio)},
    }


def _liberal_direction(y: np.ndarray, pid7: np.ndarray) -> np.ndarray:
    """+1 where support goes with Democratic identification, else -1."""
    known = (pid7 >= 1) & (pid7 <= 7)
    signs = []
    for j in range(y.shape[1]):
        ok = known & ~np.isnan(y[:, j])
        signs.append(-1 if np.corrcoef(y[ok, j], pid7[ok])[0, 1] > 0 else 1)
    return np.array(signs)


def _mix(y: np.ndarray, direction: np.ndarray, topic: np.ndarray) -> dict[str, float]:
    """Overall liberal share, and how moderates vary between topics."""
    liberal = np.where(direction > 0, y, 1.0 - y)
    overall = np.nanmean(liberal, axis=1)
    moderate = (overall >= 0.4) & (overall <= 0.6)
    topic_share = np.stack(
        [np.nanmean(liberal[:, topic == t], axis=1) for t in np.unique(topic)], axis=1
    )
    spread = np.nanstd(topic_share, axis=1)
    return {
        "share_moderate": float(moderate.mean()),
        "moderates_between_topic_sd": float(np.nanmean(spread[moderate])),
        "deciles_of_liberal_share": [round(float(q), 3) for q in np.nanquantile(overall, np.linspace(0.1, 0.9, 9))],
    }


def moderates() -> dict[str, object]:
    """
    Ahler and Broockman: people who look moderate overall usually hold a mix
    of liberal and conservative positions, organised by issue, rather than
    centrist ones. On binary items the testable part is the organisation:
    how much a moderate's liberal share varies between topics, in data and
    in respondents drawn from the model, and how many people are moderate.
    """
    survey = load_survey()
    model = load_beliefs()
    a, b = _model_items()
    pid7 = np.full(survey.y.shape[0], np.nan)
    with (ROOT / ".cache/ces/2024/CCES24_Common_OUTPUT_vv_topost_final.csv").open(
        newline="", encoding="utf-8", errors="replace"
    ) as handle:
        for i, row in enumerate(csv.DictReader(handle)):
            if row["pid7"] in {"1", "2", "3", "4", "5", "6", "7"}:
                pid7[i] = float(row["pid7"])
    direction = _liberal_direction(survey.y, pid7)
    topics = sorted({t for _, t, _ in ITEMS})
    topic = np.array([topics.index(t) for _, t, _ in ITEMS])
    data = _mix(survey.y, direction, topic)
    rng = np.random.default_rng(SEED + 2)
    keys = [g for g in survey.district if g in model.district_means]
    chol = np.linalg.cholesky(model.within_cov)
    centres = {g: _district_mean(model, g, rng) for g in sorted(set(keys))}
    means = np.array([centres[g] for g in keys])
    theta = means + rng.standard_normal(means.shape) @ chol.T
    eta = theta @ a.T + b
    simulated = ((eta + rng.standard_normal(eta.shape)) > 0).astype(float)
    return {"data": data, "model": _mix(simulated, direction, topic)}


def pooling() -> dict[str, object]:
    """
    How much of the per-topic pooling strength reflects attendance. Delegate
    choice counts a candidate's skipped question as a miss, so a reliable
    attendee looks good on every topic. The strength is re-estimated from
    the same simulated histories counting only questions both voted on.
    History questions only; no evaluation outcome is read.
    """
    from delegation.comparison.beliefs import BeliefCityConfig, simulate_belief_city
    from delegation.comparison.choice import pooled_agreements

    model = load_beliefs()
    out = []
    for seed in range(1, 6):
        city = simulate_belief_city(model, BeliefCityConfig(seed=seed))
        votes, topic = city.history.own_votes, city.history.dimension
        with_absence = pooled_agreements(votes, topic, len(city.categories)).strength
        without = pooled_agreements(votes, topic, len(city.categories), absence_is_miss=False).strength
        out.append({"seed": seed, "strength_absence_as_miss": round(with_absence, 1),
                    "strength_both_voted_only": round(without, 1)})
    return {"cities": out, "note": "history only; pilot seeds 1-3 plus 4-5"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", nargs="?", default="all",
                        choices=["representative", "districts", "moderates", "holdout", "selection", "pooling", "all"])
    args = parser.parse_args()
    checks = {
        "representative": representative,
        "districts": districts,
        "moderates": moderates,
        "pooling": pooling,
    }
    if args.check in ("holdout", "all"):
        from scripts.validate_holdout import holdout

        checks["holdout"] = holdout
    if args.check in ("selection", "all"):
        from scripts.validate_selection import selection

        checks["selection"] = selection
    chosen = checks if args.check == "all" else {args.check: checks[args.check]}
    existing = json.loads(OUT.read_text()) if OUT.exists() else {}
    for name, check in chosen.items():
        existing[name] = check()
        print(name, json.dumps(existing[name], indent=2), flush=True)
    OUT.write_text(json.dumps(existing, indent=2))


if __name__ == "__main__":
    main()
