"""
Atlas maps and single cells.

Orchestration only: voting.spatial builds the electorates and counts the
maps, and a cell's electorate goes through the same resolution as any
profile (api.services.profile_resolution), so the instrument shows exactly
what the map counted.
"""

from voting.spatial import (
    DEFAULT_CLOUD,
    DEFAULT_GRID,
    Atlas,
    Point,
    cell_center,
    compute_atlas,
    electorate_at,
)

from ..schemas.atlas import (
    AtlasCandidateSchema,
    AtlasMapSchema,
    AtlasPointRequest,
    AtlasRequest,
    AtlasResponse,
    VoterCloudSchema,
)
from ..schemas.voting import (
    ProfileResolveRequest,
    ProfileResolveResponse,
    UtilityProfileSchema,
    UtilityRowSchema,
)
from .profile_resolution import resolve_profile_request


def atlas_response(request: AtlasRequest) -> AtlasResponse:
    """
    Every method's map for a layout.

    Raises:
        InvalidLayoutError: If the layout is invalid
    """
    ids, positions = _layout(request)
    atlas = compute_atlas(ids, positions, DEFAULT_GRID, DEFAULT_CLOUD, request.tiebreak_seed)
    return _schema(atlas)


def atlas_point_response(request: AtlasPointRequest) -> ProfileResolveResponse:
    """
    The electorate at one cell, resolved as /profile/resolve would.

    Raises:
        InvalidLayoutError: If the layout is invalid
    """
    ids, positions = _layout(request)
    profile = electorate_at(cell_center(request.cell, DEFAULT_GRID), ids, positions, DEFAULT_CLOUD)
    return resolve_profile_request(
        ProfileResolveRequest(
            profile=UtilityProfileSchema(
                ballot_type="utility",
                candidates=list(profile.candidates),
                rows=[
                    UtilityRowSchema(count=count, utilities=dict(zip(profile.candidates, row)))
                    for count, row in profile.rows
                ],
            ),
            tiebreak_seed=request.tiebreak_seed,
        )
    )


def _layout(request: AtlasRequest) -> tuple[list[str], list[Point]]:
    return (
        [c.id for c in request.candidates],
        [(c.x, c.y) for c in request.candidates],
    )


def _schema(atlas: Atlas) -> AtlasResponse:
    ids = atlas.candidates

    def letters(indices: tuple[int, ...]) -> str:
        return "".join(ids[i] if i >= 0 else "-" for i in indices)

    return AtlasResponse(
        candidates=[
            AtlasCandidateSchema(id=c, x=x, y=y) for c, (x, y) in zip(ids, atlas.positions)
        ],
        size=atlas.size,
        cloud=VoterCloudSchema(
            voters_per_type=atlas.cloud.voters_per_type,
            spread=atlas.cloud.spread,
            offsets=list(atlas.cloud.offsets),
        ),
        ballot_model=atlas.ballot_model,
        tiebreak_seed=atlas.tiebreak_seed,
        maps=[
            AtlasMapSchema(
                method=method,
                winners=letters(map_.winners),
                ties=[cell for cell, decisive in enumerate(map_.decisive) if not decisive],
            )
            for method, map_ in atlas.maps.items()
        ],
        condorcet=letters(atlas.condorcet),
        utilitarian=letters(atlas.utilitarian),
        disagreement="".join(str(n) for n in atlas.disagreement),
    )
