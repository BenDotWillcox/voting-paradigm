"""
Districting domain package.

Algorithmic redistricting (demo 3): how to draw districts within a state
given its seat count, using balanced power diagrams (Cohen-Addad / Klein /
Young, arXiv 1710.03358). Seat counts per state come from the separate
apportionment/ package (demo 4); precompute planning takes the apportionment
function as a parameter rather than importing it.

Boundary rules (per CLAUDE.md):
  - Pure Python; no DB writes, no HTTP, no I/O at import time.
  - May import from the foundational primitives voting/ and apportionment/
    (precompute derives its House-size anchors from apportionment/).
    Does NOT import from preferences/, delegation/, or other demo packages.
"""

from .algorithm import (
    DistrictCenter,
    DistrictingError,
    DistrictingResult,
    Unit,
    balanced_power_diagram,
)
from .precompute import (
    CAP_ANCHORS,
    CACHE_VERSION,
    POPULAR_STATE_FIPS,
    PrecomputeJob,
    build_precompute_manifest,
    compute_tier,
    district_plan_cache_key,
)

__all__ = [
    # Districting algorithm
    "balanced_power_diagram",
    "Unit",
    "DistrictCenter",
    "DistrictingResult",
    "DistrictingError",
    # Precompute planning
    "CAP_ANCHORS",
    "CACHE_VERSION",
    "POPULAR_STATE_FIPS",
    "PrecomputeJob",
    "build_precompute_manifest",
    "compute_tier",
    "district_plan_cache_key",
]
