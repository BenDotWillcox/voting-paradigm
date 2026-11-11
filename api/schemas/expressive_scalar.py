"""Explicit contracts for scalar expressive-ballot previews."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from api.schemas.expressive import Score, StrictSchema

PolicyValue = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False, strict=True)]
HalfWidth = Annotated[float, Field(gt=0, le=100, allow_inf_nan=False, strict=True)]


class ScalarPreviewRequest(StrictSchema):
    ideal: PolicyValue
    lower_half_width: HalfWidth = Field(
        description="Percentage-point departure below the ideal that halves the unclipped score.",
    )
    upper_half_width: HalfWidth = Field(
        description="Percentage-point departure above the ideal that halves the unclipped score.",
    )
    approval_min: PolicyValue = Field(description="Inclusive lower approval bound.")
    approval_max: PolicyValue = Field(description="Inclusive upper approval bound.")
    probe: PolicyValue

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{
                "ideal": 4.55,
                "lower_half_width": 2,
                "upper_half_width": 2,
                "approval_min": 0,
                "approval_max": 100,
                "probe": 4.55,
            }],
        },
    )

    @model_validator(mode="after")
    def check_approval_order(self) -> Self:
        if not self.approval_min <= self.ideal <= self.approval_max:
            raise ValueError("Approval bounds must contain the ideal rate.")
        return self


class ScalarCurvePointSchema(StrictSchema):
    value: PolicyValue
    unclipped_score: Score


class ScalarProbeSchema(StrictSchema):
    value: PolicyValue
    score: Score
    approved: bool


class ScalarPreviewResponse(StrictSchema):
    model: Literal["clipped-asymmetric-gaussian-v2"]
    points: list[ScalarCurvePointSchema]
    probe: ScalarProbeSchema


class ScalarErrorDetail(StrictSchema):
    code: Literal["invalid_scalar_ballot"]
    message: str


class ScalarErrorResponse(StrictSchema):
    detail: ScalarErrorDetail
