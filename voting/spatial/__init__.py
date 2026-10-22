"""
Spatial electorates and the atlas: voters and candidates in a plane, and who
each method elects as a voter cloud slides across it.
"""

from .atlas import ATLAS_METHODS, DEFAULT_GRID, Atlas, MethodMap, cell_center, compute_atlas
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
    sunflower_cloud,
)

__all__ = [
    "ATLAS_METHODS",
    "DEFAULT_GRID",
    "Atlas",
    "MethodMap",
    "cell_center",
    "compute_atlas",
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
    "sunflower_cloud",
]
