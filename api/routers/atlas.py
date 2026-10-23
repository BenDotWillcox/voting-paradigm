"""
HTTP router for the atlas: spatial winner maps for the methods instrument.

HTTP only: request and response validation, error mapping. The maps live in
api.services.atlas and voting.spatial.
"""

from fastapi import APIRouter, HTTPException

from voting.spatial import InvalidLayoutError

from ..schemas.atlas import AtlasPointRequest, AtlasRequest, AtlasResponse
from ..schemas.voting import ErrorResponse, ProfileResolveResponse
from ..services.atlas import atlas_point_response, atlas_response

router = APIRouter(prefix="/api/voting", tags=["voting"])


@router.post(
    "/atlas",
    response_model=AtlasResponse,
    summary="Map who each method elects across the plane",
    description=(
        "Takes three to five candidates at points in the unit square. Each "
        "cell of a 64 × 64 grid holds the same cloud of 95 voters (19 voter "
        "types) centered there, with utility falling linearly with distance; "
        "the sincere ballot model casts their ballots and the reference "
        "methods count every cell. Returns each method's winner per cell, the "
        "cells where a tiebreak decided, and the Condorcet, utilitarian and "
        "disagreement reference maps. Deterministic: the same layout and seed "
        "always give the same response."
    ),
    responses={422: {"model": ErrorResponse, "description": "Invalid layout"}},
)
def atlas(request: AtlasRequest) -> AtlasResponse:
    try:
        return atlas_response(request)
    except InvalidLayoutError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/atlas/point",
    response_model=ProfileResolveResponse,
    summary="Resolve the electorate at one atlas cell",
    description=(
        "Builds the voter cloud centered on one cell of the atlas grid and "
        "resolves it exactly as /profile/resolve does, so the instrument "
        "shows the electorate the map counted."
    ),
    responses={422: {"model": ErrorResponse, "description": "Invalid layout"}},
)
def atlas_point(request: AtlasPointRequest) -> ProfileResolveResponse:
    try:
        return atlas_point_response(request)
    except InvalidLayoutError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
