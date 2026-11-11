"""Explicit HTTP contracts for the expressive-budget preview demo."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from expressive import CategoryId, get_funding_issues

Share = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False, strict=True)]
Width = Annotated[float, Field(gt=0, le=100, allow_inf_nan=False, strict=True)]
Score = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False, strict=True)]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AllocationSchema(StrictSchema):
    roads: Share
    sidewalks: Share
    crossings: Share
    trees: Share
    parks: Share
    facilities: Share

    def as_mapping(self) -> dict[CategoryId, float]:
        return {
            "roads": self.roads,
            "sidewalks": self.sidewalks,
            "crossings": self.crossings,
            "trees": self.trees,
            "parks": self.parks,
            "facilities": self.facilities,
        }

    @model_validator(mode="after")
    def check_total(self) -> Self:
        if not math.isclose(math.fsum(self.as_mapping().values()), 100, rel_tol=0, abs_tol=1e-6):
            raise ValueError("Budget shares must total 100 percent.")
        return self


class DirectionalFlexibilitySchema(StrictSchema):
    decrease: Width = Field(description="Gaussian decrease half-score width; only feasible funding levels are scored.")
    increase: Width = Field(description="Gaussian increase half-score width; only feasible funding levels are scored.")


class FlexibilitySchema(StrictSchema):
    roads: DirectionalFlexibilitySchema
    sidewalks: DirectionalFlexibilitySchema
    crossings: DirectionalFlexibilitySchema
    trees: DirectionalFlexibilitySchema
    parks: DirectionalFlexibilitySchema
    facilities: DirectionalFlexibilitySchema

    def as_mapping(self) -> dict[CategoryId, DirectionalFlexibilitySchema]:
        return {
            "roads": self.roads,
            "sidewalks": self.sidewalks,
            "crossings": self.crossings,
            "trees": self.trees,
            "parks": self.parks,
            "facilities": self.facilities,
        }


class TransferSchema(StrictSchema):
    source: CategoryId
    target: CategoryId
    amount: Width = Field(description="Budget share to transfer, in percentage points.")

    @model_validator(mode="after")
    def check_distinct_categories(self) -> Self:
        if self.source == self.target:
            raise ValueError("A transfer needs different source and target categories.")
        return self


class BudgetPreviewRequest(StrictSchema):
    ideal: AllocationSchema
    flexibility: FlexibilitySchema
    transfers: list[TransferSchema] = Field(min_length=1, max_length=12)

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{
                "ideal": {"roads": 25, "sidewalks": 20, "crossings": 15, "trees": 15, "parks": 15, "facilities": 10},
                "flexibility": {
                    "roads": {"decrease": 6, "increase": 12},
                    "sidewalks": {"decrease": 5, "increase": 12},
                    "crossings": {"decrease": 8, "increase": 8},
                    "trees": {"decrease": 6, "increase": 16},
                    "parks": {"decrease": 12, "increase": 12},
                    "facilities": {"decrease": 8, "increase": 8},
                },
                "transfers": [
                    {"source": "roads", "target": "trees", "amount": 5},
                    {"source": "crossings", "target": "sidewalks", "amount": 5},
                    {"source": "crossings", "target": "sidewalks", "amount": 15},
                ],
            }],
        },
    )

    @model_validator(mode="after")
    def check_available_shares(self) -> Self:
        shares = self.ideal.as_mapping()
        issues = get_funding_issues(shares)
        if issues:
            categories = ", ".join(issue.category for issue in issues)
            raise ValueError(f"Fixed projects must receive zero or their complete cost: {categories}.")
        for transfer in self.transfers:
            if transfer.amount > shares[transfer.source]:
                raise ValueError("Transfer amount exceeds its source's available share.")
        return self


class CategoryScoresSchema(StrictSchema):
    roads: Score
    sidewalks: Score
    crossings: Score
    trees: Score
    parks: Score
    facilities: Score


class FundingIssueSchema(StrictSchema):
    category: CategoryId
    kind: Literal["below_threshold", "above_cost"]
    required_share: Share
    actual_share: Share


class TransferPreviewSchema(TransferSchema):
    allocation: AllocationSchema
    feasible: Annotated[bool, Field(strict=True)]
    funding_issues: list[FundingIssueSchema]
    score: Score | None
    category_scores: CategoryScoresSchema | None

    @model_validator(mode="after")
    def check_score_feasibility(self) -> Self:
        if self.feasible:
            if self.funding_issues or self.score is None or self.category_scores is None:
                raise ValueError("Feasible previews require scores and no funding issues.")
        elif not self.funding_issues or self.score is not None or self.category_scores is not None:
            raise ValueError("Infeasible previews require funding issues and null scores.")
        return self


class BudgetPreviewResponse(StrictSchema):
    model: Literal["neighborhood-budget-v2"]
    fund_id: Literal["chicago-neighborhood-fund-v1"]
    fund_total: Literal[1000000]
    previews: list[TransferPreviewSchema]


class BudgetErrorDetail(StrictSchema):
    code: Literal["invalid_budget"]
    message: str


class BudgetErrorResponse(StrictSchema):
    detail: BudgetErrorDetail


class BudgetValidationIssue(StrictSchema):
    loc: list[str | int]
    msg: str
    type: str


class BudgetValidationResponse(StrictSchema):
    detail: list[BudgetValidationIssue]
