"""Utility evaluations for a Chicago-inspired neighborhood improvement fund.

A voter directly declares ideal shares and asymmetric per-category half-score
widths. This is not a probability distribution or inferred preference posterior.
Each category contributes 2 ** -(departure / directional_width) ** 2; the whole
budget's score is the product. Independent category penalties are an explicit
modeling assumption, not a claim that all real preferences are separable. Scores
refer to final allocations, never to the sequence of edits used to reach them.
Scalable programs accept any share. Fixed projects can receive zero or their
complete stated cost; infeasible allocations have no preference score. The
project costs and program classifications are illustrative demo assumptions.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping, cast

CategoryId = Literal["roads", "sidewalks", "crossings", "trees", "parks", "facilities"]
MODEL_VERSION: Literal["neighborhood-budget-v2"] = "neighborhood-budget-v2"
_FUND = json.loads(Path(__file__).with_name("neighborhood_fund.json").read_text(encoding="utf-8"))
FUND_ID: str = _FUND["id"]
FUND_TOTAL: int = _FUND["total_dollars"]
CATEGORIES: tuple[CategoryId, ...] = tuple(cast(CategoryId, category["id"]) for category in _FUND["categories"])
PROJECT_COST_SHARES: Mapping[CategoryId, float] = MappingProxyType({
    cast(CategoryId, category["id"]): 100 * category["cost_dollars"] / FUND_TOTAL
    for category in _FUND["categories"] if category["kind"] == "fixed"
})
_TOTAL_TOLERANCE = 1e-6


class InvalidBudgetError(ValueError):
    """An authored budget or transfer violates the demo's explicit contract."""


def _finite_number(value: float, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidBudgetError(f"{label} must be a finite number.")
    if not math.isfinite(value):
        raise InvalidBudgetError(f"{label} must be a finite number.")


def _validate_allocation(allocation: Mapping[CategoryId, float]) -> None:
    if set(allocation) != set(CATEGORIES):
        raise InvalidBudgetError("Budget must contain exactly the six neighborhood fund categories.")
    for category in CATEGORIES:
        value = allocation[category]
        _finite_number(value, f"{category} share")
        if not 0 <= value <= 100:
            raise InvalidBudgetError("Budget shares must lie between 0 and 100 percent.")
    if not math.isclose(math.fsum(allocation.values()), 100, rel_tol=0, abs_tol=_TOTAL_TOLERANCE):
        raise InvalidBudgetError("Budget shares must total 100 percent.")


@dataclass(frozen=True)
class FundingIssue:
    category: CategoryId
    kind: Literal["below_threshold", "above_cost"]
    required_share: float
    actual_share: float


def get_funding_issues(allocation: Mapping[CategoryId, float]) -> tuple[FundingIssue, ...]:
    """Separate physical project feasibility from the voter's declared utility."""
    _validate_allocation(allocation)
    issues = []
    for category, cost in PROJECT_COST_SHARES.items():
        actual = allocation[category]
        if math.isclose(actual, 0, rel_tol=0, abs_tol=_TOTAL_TOLERANCE) or math.isclose(
            actual, cost, rel_tol=0, abs_tol=_TOTAL_TOLERANCE
        ):
            continue
        issues.append(FundingIssue(
            category=category,
            kind="below_threshold" if actual < cost else "above_cost",
            required_share=cost,
            actual_share=actual,
        ))
    return tuple(issues)


@dataclass(frozen=True)
class Flexibility:
    """Gaussian half-score widths, evaluated only at feasible funding levels.

    For a fixed project, the relevant width scores switching between zero and
    its complete cost. A width does not make a partial project deliverable.
    """

    decrease: float
    increase: float

    def __post_init__(self) -> None:
        for name, value in (("decrease", self.decrease), ("increase", self.increase)):
            _finite_number(value, f"{name} flexibility")
            if not 0 < value <= 100:
                raise InvalidBudgetError("Flexibility must be greater than 0 and at most 100 percentage points.")


@dataclass(frozen=True)
class BudgetBallot:
    ideal: Mapping[CategoryId, float]
    flexibility: Mapping[CategoryId, Flexibility]

    def __post_init__(self) -> None:
        issues = get_funding_issues(self.ideal)
        if issues:
            categories = ", ".join(issue.category for issue in issues)
            raise InvalidBudgetError(f"Fixed projects must receive zero or their complete cost: {categories}.")
        if set(self.flexibility) != set(CATEGORIES):
            raise InvalidBudgetError("Flexibility must contain exactly the six neighborhood fund categories.")
        if any(not isinstance(value, Flexibility) for value in self.flexibility.values()):
            raise InvalidBudgetError("Each category requires decrease and increase flexibility.")
        # Snapshot caller-owned dictionaries so later editing cannot change a ballot.
        object.__setattr__(self, "ideal", MappingProxyType(dict(self.ideal)))
        object.__setattr__(self, "flexibility", MappingProxyType(dict(self.flexibility)))


@dataclass(frozen=True)
class Transfer:
    source: CategoryId
    target: CategoryId
    amount: float

    def __post_init__(self) -> None:
        if self.source not in CATEGORIES or self.target not in CATEGORIES:
            raise InvalidBudgetError("Transfers must use the demo's category identifiers.")
        if self.source == self.target:
            raise InvalidBudgetError("A transfer needs different source and target categories.")
        _finite_number(self.amount, "Transfer amount")
        if not 0 < self.amount <= 100:
            raise InvalidBudgetError("Transfer amount must be greater than 0 and at most 100 percentage points.")


@dataclass(frozen=True)
class BudgetEvaluation:
    feasible: bool
    funding_issues: tuple[FundingIssue, ...]
    score: float | None
    category_scores: Mapping[CategoryId, float] | None


@dataclass(frozen=True)
class TransferPreview:
    transfer: Transfer
    allocation: Mapping[CategoryId, float]
    evaluation: BudgetEvaluation


def evaluate_budget(ballot: BudgetBallot, allocation: Mapping[CategoryId, float]) -> BudgetEvaluation:
    """Score feasible allocations, leaving infeasible project funding unscored."""
    issues = get_funding_issues(allocation)
    if issues:
        return BudgetEvaluation(feasible=False, funding_issues=issues, score=None, category_scores=None)
    category_scores: dict[CategoryId, float] = {}
    for category in CATEGORIES:
        delta = allocation[category] - ballot.ideal[category]
        widths = ballot.flexibility[category]
        width = widths.decrease if delta < 0 else widths.increase
        ratio = abs(delta) / width
        # Beyond this distance the exponential underflows to zero anyway. The
        # explicit guard also avoids overflow for valid, extremely small widths.
        category_scores[category] = 0.0 if ratio > 40 else math.exp(-math.log(2) * ratio * ratio)
    return BudgetEvaluation(
        feasible=True,
        funding_issues=(),
        score=math.prod(category_scores.values()),
        category_scores=MappingProxyType(category_scores),
    )


def preview_transfer(ballot: BudgetBallot, transfer: Transfer) -> TransferPreview:
    """Apply one independently proposed transfer from the unchanged ideal."""
    if transfer.amount > ballot.ideal[transfer.source]:
        raise InvalidBudgetError("Transfer amount exceeds its source's available share.")
    allocation = dict(ballot.ideal)
    allocation[transfer.source] -= transfer.amount
    allocation[transfer.target] += transfer.amount
    return TransferPreview(
        transfer=transfer,
        allocation=MappingProxyType(allocation),
        evaluation=evaluate_budget(ballot, allocation),
    )
