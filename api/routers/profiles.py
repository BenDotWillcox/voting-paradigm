"""
HTTP router for resolving anonymous voter profiles (the methods instrument).

HTTP only: request and response validation, error mapping. Resolution lives
in api.services.profile_resolution and the voting package. The older
/api/elections routes serve the methods lab until the instrument replaces it.
"""

from fastapi import APIRouter, HTTPException

from voting.ballots.ranked_choice import InvalidRankingError
from voting.ballots.ranked_profile import InvalidProfileError

from ..schemas.voting import ErrorResponse, ProfileResolveRequest, ProfileResolveResponse
from ..services.profile_resolution import resolve_profile_request

router = APIRouter(prefix="/api/voting", tags=["voting"])


@router.post(
    "/profile/resolve",
    response_model=ProfileResolveResponse,
    summary="Resolve a profile under every ranked method",
    description=(
        "Takes an anonymous profile (how many voters cast each complete "
        "ranking) and returns, for plurality, IRV, Borda and Ranked Pairs, the "
        "winner, whether the ballots alone decided it, every tie the seeded "
        "tiebreak settled, and the method's count. Also returns the head-to-head "
        "matrix and the candidates the majority, Condorcet winner and Condorcet "
        "loser criteria single out. Deterministic: the same profile and seed "
        "always give the same response."
    ),
    responses={422: {"model": ErrorResponse, "description": "Invalid profile"}},
)
def resolve_profile(request: ProfileResolveRequest) -> ProfileResolveResponse:
    try:
        return resolve_profile_request(request)
    except (InvalidProfileError, InvalidRankingError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
