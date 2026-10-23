"""
Spatial electorates: voters and candidates in a plane. The atlas maps who
each method elects as a voter cloud slides across it; the sampler draws whole
elections for simulation; the counter counts them as the instrument does.
"""

from .atlas import ATLAS_METHODS, DEFAULT_GRID, Atlas, MethodMap, cell_center, compute_atlas
from .counting import COUNTED_METHODS, Count, ProfileCounter
from .electorate import (
    DEFAULT_CLOUD,
    DEFAULT_SPREAD,
    DEFAULT_VOTER_TYPES,
    DEFAULT_VOTERS_PER_TYPE,
    InvalidLayoutError,
    Point,
    VoterCloud,
    check_layout,
    cloud_distances,
    cloud_utilities,
    electorate_at,
    point_distances,
    sunflower_cloud,
)
from .sampling import CANDIDATE_LETTERS, SpatialElection, sample_spatial_election

__all__ = [
    "ATLAS_METHODS",
    "DEFAULT_GRID",
    "Atlas",
    "MethodMap",
    "cell_center",
    "compute_atlas",
    "COUNTED_METHODS",
    "Count",
    "ProfileCounter",
    "DEFAULT_CLOUD",
    "DEFAULT_SPREAD",
    "DEFAULT_VOTER_TYPES",
    "DEFAULT_VOTERS_PER_TYPE",
    "InvalidLayoutError",
    "Point",
    "VoterCloud",
    "check_layout",
    "cloud_distances",
    "cloud_utilities",
    "electorate_at",
    "point_distances",
    "sunflower_cloud",
    "CANDIDATE_LETTERS",
    "SpatialElection",
    "sample_spatial_election",
]
