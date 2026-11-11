"""Map scalar preview contracts to independent expressive-domain computations."""

from api.schemas.expressive_scalar import (
    ScalarCurvePointSchema,
    ScalarPreviewRequest,
    ScalarPreviewResponse,
    ScalarProbeSchema,
)
from expressive.scalar import SCALAR_MODEL_VERSION, ScalarBallot, preview_scalar


def preview_scalar_ballot(request: ScalarPreviewRequest) -> ScalarPreviewResponse:
    ballot = ScalarBallot(
        ideal=request.ideal,
        lower_half_width=request.lower_half_width,
        upper_half_width=request.upper_half_width,
        approval_min=request.approval_min,
        approval_max=request.approval_max,
    )
    preview = preview_scalar(ballot, request.probe)
    return ScalarPreviewResponse(
        model=SCALAR_MODEL_VERSION,
        points=[
            ScalarCurvePointSchema(value=point.value, unclipped_score=point.unclipped_score)
            for point in preview.points
        ],
        probe=ScalarProbeSchema(
            value=preview.probe.value,
            score=preview.probe.score,
            approved=preview.probe.approved,
        ),
    )
