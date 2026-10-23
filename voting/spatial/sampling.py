"""
Seeded spatial elections: candidates and voters drawn at random in a plane.

The standard spatial model of simulation studies (e.g. Merrill 1984):
candidates and voters are drawn independently from the same standard
bivariate Gaussian, and each voter's utility falls linearly with distance,
rescaled exactly as for the atlas (cloud_utilities).

Used by: the methods simulation in eval/. A future voting agent can use the
same sampler as its beliefs about the other voters: it takes the random
generator, so a caller controls and records every draw.
"""

from dataclasses import dataclass

import numpy as np

from ..ballot_models import UtilityProfile, create_utility_profile
from ..types import CandidateId
from .electorate import InvalidLayoutError, Point, cloud_utilities, point_distances

CANDIDATE_LETTERS = ("A", "B", "C", "D", "E")


@dataclass(frozen=True)
class SpatialElection:
    """One sampled election: where everyone stands, and the voters' utilities."""
    candidates: tuple[CandidateId, ...]
    candidate_positions: tuple[Point, ...]
    voter_positions: tuple[Point, ...]
    # One voter type per voter, in draw order
    profile: UtilityProfile


def sample_spatial_election(
    rng: np.random.Generator,
    voters: int,
    candidates: int,
) -> SpatialElection:
    """
    Draw the candidates, then the voters, from a standard bivariate Gaussian.

    Candidates are named A, B, C, ... in draw order.

    Raises:
        InvalidLayoutError: Unless there are 2 to 5 candidates and at least
            one voter
    """
    if not 2 <= candidates <= len(CANDIDATE_LETTERS) or voters < 1:
        raise InvalidLayoutError("An election needs 2 to 5 candidates and at least one voter")
    ids = CANDIDATE_LETTERS[:candidates]
    candidate_xy = rng.standard_normal((candidates, 2))
    voter_xy = rng.standard_normal((voters, 2))
    positions = [(float(x), float(y)) for x, y in candidate_xy]
    utilities = cloud_utilities(point_distances(voter_xy, positions))
    return SpatialElection(
        candidates=ids,
        candidate_positions=tuple(positions),
        voter_positions=tuple((float(x), float(y)) for x, y in voter_xy),
        profile=create_utility_profile(
            ids, [(1, dict(zip(ids, (int(u) for u in row)))) for row in utilities]
        ),
    )
