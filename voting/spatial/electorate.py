"""
Spatial electorates: voters and candidates at points in a two-dimensional
issue space, each voter's utility falling linearly with distance.

Used by: the atlas (voting.spatial.atlas), which slides one voter cloud
across the plane, and the profile it hands the instrument for a single cell;
and the sampler (voting.spatial.sampling), which draws whole elections.

Coordinates are in the unit square, y growing downward as on screen. Both
callers turn distances into utilities with cloud_utilities, so a cell's
electorate is exactly the one its map counted.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ..ballot_models import UTILITY_SCALE, UtilityProfile, create_utility_profile
from ..types import CandidateId

Point = tuple[float, float]

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]

GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))

DEFAULT_VOTER_TYPES = 19
DEFAULT_VOTERS_PER_TYPE = 5
# Standard deviation of the Gaussian the cloud approximates, in map units
DEFAULT_SPREAD = 0.16


class InvalidLayoutError(ValueError):
    """Raised when candidates and positions do not describe a layout."""
    pass


@dataclass(frozen=True)
class VoterCloud:
    """Voter types at fixed offsets from the cloud's center, equally many voters each."""
    offsets: tuple[Point, ...]
    voters_per_type: int
    spread: float

    @property
    def total_voters(self) -> int:
        return len(self.offsets) * self.voters_per_type


def sunflower_cloud(
    types: int = DEFAULT_VOTER_TYPES,
    spread: float = DEFAULT_SPREAD,
    voters_per_type: int = DEFAULT_VOTERS_PER_TYPE,
) -> VoterCloud:
    """
    A sunflower (Vogel) spiral approximating a circular Gaussian.

    Type i sits at the golden angle times i, at the radius below which a
    fraction (i + 0.5) / types of the Gaussian's mass lies, so equal counts
    approximate its density. Unlike a lattice, no two types share an x or a
    y, so as the cloud slides they cross a boundary one at a time.
    """
    if types < 1 or voters_per_type < 1 or spread <= 0:
        raise InvalidLayoutError("A cloud needs voters and a positive spread")
    offsets: list[Point] = []
    for i in range(types):
        radius = spread * math.sqrt(-2 * math.log(1 - (i + 0.5) / types))
        angle = i * GOLDEN_ANGLE
        offsets.append((radius * math.cos(angle), radius * math.sin(angle)))
    return VoterCloud(tuple(offsets), voters_per_type, spread)


DEFAULT_CLOUD = sunflower_cloud()


def cloud_distances(
    centers: FloatArray,
    positions: Sequence[Point],
    cloud: VoterCloud,
) -> FloatArray:
    """
    Distance from every voter type to every candidate, for a cloud at each
    center: an array of shape (centers, voter types, candidates).
    """
    voters = centers[:, None, :] + np.asarray(cloud.offsets, dtype=np.float64)[None, :, :]
    return point_distances(voters, positions)


def point_distances(voters: FloatArray, positions: Sequence[Point]) -> FloatArray:
    """
    Euclidean distance from voters, an array of points of any leading shape,
    to every candidate: shape (..., candidates).
    """
    candidates = np.asarray(positions, dtype=np.float64)
    dx = voters[..., None, 0] - candidates[:, 0]
    dy = voters[..., None, 1] - candidates[:, 1]
    distances: FloatArray = np.sqrt(dx * dx + dy * dy)
    return distances


def cloud_utilities(distances: FloatArray) -> IntArray:
    """
    Linear utilities from distances, along the last axis: each voter's nearest
    candidate gets UTILITY_SCALE and farthest 0, rounded half up. A voter
    equally far from every candidate is indifferent and rates all of them at
    half the scale.
    """
    nearest = distances.min(axis=-1, keepdims=True)
    farthest = distances.max(axis=-1, keepdims=True)
    span = farthest - nearest
    safe = np.where(span > 0, span, 1.0)
    scaled = np.floor((farthest - distances) / safe * UTILITY_SCALE + 0.5)
    utilities: IntArray = np.where(span > 0, scaled, UTILITY_SCALE // 2).astype(np.int64)
    return utilities


def electorate_at(
    center: Point,
    candidates: Sequence[CandidateId],
    positions: Sequence[Point],
    cloud: VoterCloud,
) -> UtilityProfile:
    """
    The cloud centered at one point, as voter types in cloud order.

    Raises:
        InvalidLayoutError: If candidates and positions do not match
    """
    check_layout(candidates, positions)
    distances = cloud_distances(np.array([center], dtype=np.float64), positions, cloud)
    utilities = cloud_utilities(distances)[0]
    return create_utility_profile(
        candidates,
        [
            (cloud.voters_per_type, {c: int(u) for c, u in zip(candidates, row)})
            for row in utilities
        ],
    )


def check_layout(candidates: Sequence[CandidateId], positions: Sequence[Point]) -> None:
    """
    Raises:
        InvalidLayoutError: Unless there are at least two distinct
            candidates, each with one finite position
    """
    if len(candidates) < 2 or len(set(candidates)) != len(candidates):
        raise InvalidLayoutError("A layout needs at least two distinct candidates")
    if len(positions) != len(candidates):
        raise InvalidLayoutError("Give exactly one position per candidate")
    if not all(math.isfinite(x) and math.isfinite(y) for x, y in positions):
        raise InvalidLayoutError("Positions must be finite")
