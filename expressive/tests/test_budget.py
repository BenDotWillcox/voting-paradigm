"""Funding feasibility and declared utility for the neighborhood budget demo."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import cast, get_args

import pytest

from expressive import (
    CATEGORIES, FUND_ID, FUND_TOTAL, PROJECT_COST_SHARES, BudgetBallot, CategoryId,
    Flexibility, InvalidBudgetError, Transfer, evaluate_budget, preview_transfer,
)


def ideal() -> dict[CategoryId, float]:
    return {"roads": 25, "sidewalks": 20, "crossings": 15, "trees": 15, "parks": 15, "facilities": 10}


def ballot() -> BudgetBallot:
    return BudgetBallot(ideal(), {category: Flexibility(10, 10) for category in CATEGORIES})


def test_shared_fund_metadata_matches_domain_contract() -> None:
    fund = json.loads(Path(__file__).parents[1].joinpath("neighborhood_fund.json").read_text(encoding="utf-8"))
    assert FUND_ID == fund["id"] == "chicago-neighborhood-fund-v1"
    assert FUND_TOTAL == fund["total_dollars"] == 1_000_000
    assert set(CATEGORIES) == set(get_args(CategoryId))
    assert PROJECT_COST_SHARES == {"crossings": 15, "parks": 15, "facilities": 10}
    assert {row["id"]: row["default_share"] for row in fund["categories"]} == ideal()


def test_ideal_is_peak_without_area_normalization() -> None:
    evaluation = evaluate_budget(ballot(), ideal())
    assert evaluation.feasible and evaluation.funding_issues == ()
    assert evaluation.score == 1
    assert evaluation.category_scores is not None
    assert all(score == 1 for score in evaluation.category_scores.values())
    narrow = BudgetBallot(ideal(), {category: Flexibility(1, 1) for category in CATEGORIES})
    assert evaluate_budget(narrow, ideal()).score == 1


def test_transfer_preserves_budget_and_combines_directional_half_scores() -> None:
    preview = preview_transfer(ballot(), Transfer("roads", "sidewalks", 10))
    assert preview.allocation == {**ideal(), "roads": 15, "sidewalks": 30}
    assert sum(preview.allocation.values()) == 100
    assert preview.evaluation.category_scores is not None
    assert preview.evaluation.category_scores["roads"] == pytest.approx(.5)
    assert preview.evaluation.category_scores["sidewalks"] == pytest.approx(.5)
    assert preview.evaluation.score == pytest.approx(.25)


def test_asymmetry_and_recipient_change_transfer_evaluation() -> None:
    widths = {category: Flexibility(10, 10) for category in CATEGORIES}
    widths["roads"] = Flexibility(decrease=5, increase=20)
    widths["trees"] = Flexibility(decrease=20, increase=2)
    declared = BudgetBallot(ideal(), widths)
    to_sidewalks = preview_transfer(declared, Transfer("roads", "sidewalks", 5)).evaluation.score
    to_trees = preview_transfer(declared, Transfer("roads", "trees", 5)).evaluation.score
    reverse = preview_transfer(declared, Transfer("sidewalks", "roads", 5)).evaluation.score
    assert to_sidewalks is not None and to_trees is not None and reverse is not None
    assert reverse > to_sidewalks > to_trees


@pytest.mark.parametrize("source,target,amount,category,kind,actual", [
    ("crossings", "roads", 5, "crossings", "below_threshold", 10),
    ("roads", "crossings", 5, "crossings", "above_cost", 20),
    ("parks", "trees", 14.999, "parks", "below_threshold", .001),
    ("trees", "facilities", .001, "facilities", "above_cost", 10.001),
])
def test_partial_or_excess_fixed_funding_is_unscored(
    source: CategoryId, target: CategoryId, amount: float, category: CategoryId, kind: str, actual: float,
) -> None:
    preview = preview_transfer(ballot(), Transfer(source, target, amount))
    evaluation = preview.evaluation
    assert not evaluation.feasible
    assert evaluation.score is None and evaluation.category_scores is None
    assert sum(preview.allocation.values()) == pytest.approx(100)
    assert len(evaluation.funding_issues) == 1
    issue = evaluation.funding_issues[0]
    assert (issue.category, issue.kind) == (category, kind)
    assert issue.required_share == PROJECT_COST_SHARES[category]
    assert issue.actual_share == pytest.approx(actual)


def test_one_transfer_can_violate_both_project_constraints() -> None:
    preview = preview_transfer(ballot(), Transfer("crossings", "facilities", 5))
    assert [(issue.category, issue.kind) for issue in preview.evaluation.funding_issues] == [
        ("crossings", "below_threshold"), ("facilities", "above_cost"),
    ]
    assert preview.evaluation.score is None


@pytest.mark.parametrize("category", ["crossings", "parks", "facilities"])
def test_complete_project_can_be_cancelled_or_funded(category: CategoryId) -> None:
    cost = PROJECT_COST_SHARES[category]
    cancelled = preview_transfer(ballot(), Transfer(category, "roads", cost))
    assert cancelled.allocation[category] == 0
    assert cancelled.evaluation.feasible
    assert cancelled.evaluation.category_scores is not None
    assert cancelled.evaluation.category_scores[category] == pytest.approx(2 ** -(cost / 10) ** 2)
    unfunded = BudgetBallot(cancelled.allocation, ballot().flexibility)
    restored = preview_transfer(unfunded, Transfer("roads", category, cost))
    assert restored.allocation == ideal()
    assert restored.evaluation.feasible
    assert restored.evaluation.score == pytest.approx(cancelled.evaluation.score)
    partial = preview_transfer(unfunded, Transfer("roads", category, cost / 2))
    assert not partial.evaluation.feasible
    assert partial.evaluation.funding_issues[0].kind == "below_threshold"


def test_fixed_project_uses_directional_width_for_other_feasible_state() -> None:
    widths = dict(ballot().flexibility)
    widths["crossings"] = Flexibility(decrease=15, increase=30)
    declared = BudgetBallot(ideal(), widths)
    cancelled = preview_transfer(declared, Transfer("crossings", "roads", 15))
    assert cancelled.evaluation.category_scores is not None
    assert cancelled.evaluation.category_scores["crossings"] == pytest.approx(.5)
    restored = preview_transfer(BudgetBallot(cancelled.allocation, widths), Transfer("roads", "crossings", 15))
    assert restored.evaluation.category_scores is not None
    assert restored.evaluation.category_scores["crossings"] == pytest.approx(2 ** -.25)


@pytest.mark.parametrize("share", [0, .123, 15.001, 100])
def test_scalable_program_has_no_project_threshold_or_cost_cap(share: float) -> None:
    values = {category: 0.0 for category in CATEGORIES}
    values["roads"], values["trees"] = share, 100 - share
    assert evaluate_budget(ballot(), values).feasible


@pytest.mark.parametrize("share", [0.001, 14.999, 15.001, 25])
def test_ideal_cannot_underfund_or_overfund_a_project(share: float) -> None:
    values = {**ideal(), "crossings": share, "roads": 40 - share}
    with pytest.raises(InvalidBudgetError, match="zero or their complete cost"):
        BudgetBallot(values, ballot().flexibility)


@pytest.mark.parametrize("share", [0, 5e-7, 15 - 5e-7, 15, 15 + 5e-7])
def test_funding_validation_allows_only_floating_point_tolerance(share: float) -> None:
    values = {**ideal(), "crossings": share, "roads": 40 - share}
    assert evaluate_budget(BudgetBallot(values, ballot().flexibility), values).feasible


def test_snapshots_and_previews_do_not_mutate_authored_ballot() -> None:
    shares = ideal()
    widths = {category: Flexibility(10, 10) for category in CATEGORIES}
    declared = BudgetBallot(shares, widths)
    shares["roads"] = 0
    widths["roads"] = Flexibility(1, 1)
    first = preview_transfer(declared, Transfer("roads", "sidewalks", 5))
    second = preview_transfer(declared, Transfer("roads", "trees", 5))
    assert declared.ideal == ideal()
    assert declared.flexibility["roads"].decrease == 10
    assert first.allocation["roads"] == second.allocation["roads"] == 20
    assert second.allocation["sidewalks"] == 20


def test_evaluation_depends_only_on_final_allocation() -> None:
    declared = ballot()
    direct = preview_transfer(declared, Transfer("roads", "sidewalks", 5))
    via_trees = ideal()
    via_trees["roads"] -= 5
    via_trees["trees"] += 5
    via_trees["trees"] -= 5
    via_trees["sidewalks"] += 5
    assert evaluate_budget(declared, via_trees) == direct.evaluation


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 101, True])
def test_invalid_shares_are_rejected(bad: float) -> None:
    values = ideal()
    values["roads"] = bad
    with pytest.raises(InvalidBudgetError):
        BudgetBallot(values, ballot().flexibility)


def test_invalid_total_and_category_sets_are_rejected() -> None:
    values = ideal()
    values["roads"] -= 1
    with pytest.raises(InvalidBudgetError):
        evaluate_budget(ballot(), values)
    values = ideal()
    del values["facilities"]
    with pytest.raises(InvalidBudgetError):
        BudgetBallot(values, ballot().flexibility)
    values = ideal()
    values[cast(CategoryId, "other")] = 0
    with pytest.raises(InvalidBudgetError):
        BudgetBallot(values, ballot().flexibility)
    widths = dict(ballot().flexibility)
    del widths["facilities"]
    with pytest.raises(InvalidBudgetError):
        BudgetBallot(ideal(), widths)


@pytest.mark.parametrize("bad", [0, -1, 101, float("nan"), float("inf"), True])
def test_invalid_flexibility_is_rejected(bad: float) -> None:
    with pytest.raises(InvalidBudgetError):
        Flexibility(decrease=bad, increase=10)
    with pytest.raises(InvalidBudgetError):
        Flexibility(decrease=10, increase=bad)


@pytest.mark.parametrize("bad", [0, -1, 101, float("nan"), float("inf"), True])
def test_invalid_transfer_amount_is_rejected(bad: float) -> None:
    with pytest.raises(InvalidBudgetError):
        Transfer("roads", "sidewalks", bad)


def test_transfer_requires_distinct_existing_categories_and_available_funds() -> None:
    with pytest.raises(InvalidBudgetError):
        Transfer("roads", "roads", 1)
    with pytest.raises(InvalidBudgetError):
        Transfer(cast(CategoryId, "missing"), "sidewalks", 1)
    with pytest.raises(InvalidBudgetError):
        preview_transfer(ballot(), Transfer("facilities", "roads", 11))


def test_very_small_positive_width_underflows_safely() -> None:
    declared = BudgetBallot(ideal(), {category: Flexibility(1e-300, 1e-300) for category in CATEGORIES})
    preview = preview_transfer(declared, Transfer("roads", "sidewalks", 1))
    assert preview.evaluation.score == 0
    assert math.isfinite(preview.evaluation.score)
