"""Precompute planning for balanced-power district maps.

The redistricting algorithm is deterministic once the population units, seat
count, and seed are fixed, but full state plans are too expensive to run during
ordinary page navigation. This module defines the cache key and the first set of
state/cap jobs the UI and API can agree on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

CAP_ANCHORS: tuple[int, ...] = (435, 574, 692, 1000, 11037)

# States likely to be inspected during demos because they are large,
# politically salient, or useful edge cases for expanded apportionment.
POPULAR_STATE_FIPS: tuple[str, ...] = (
    "20",  # Kansas, first tract-level balanced-power artifact
    "06",  # California
    "48",  # Texas
    "12",  # Florida
    "36",  # New York
    "42",  # Pennsylvania
    "17",  # Illinois
    "39",  # Ohio
    "13",  # Georgia
    "37",  # North Carolina
)

CACHE_VERSION = "bpd-v1"


@dataclass(frozen=True)
class PrecomputeJob:
    state_fips: str
    cap: int
    seats: int
    cache_key: str
    compute_tier: str


def district_plan_cache_key(
    state_fips: str,
    cap: int,
    seats: int,
    *,
    version: str = CACHE_VERSION,
) -> str:
    """Stable cache key for a precomputed state district plan artifact."""
    return f"{version}/state-{state_fips}/cap-{cap}/seats-{seats}.json"


def compute_tier(seats: int) -> str:
    """Classify a job by expected cost."""
    if seats <= 20:
        return "interactive-preview"
    if seats <= 120:
        return "batch-cache"
    return "offline-heavy"


def build_precompute_manifest(
    apportionment_fn: Callable[[int], Mapping[str, int]],
    *,
    caps: tuple[int, ...] = CAP_ANCHORS,
    states: tuple[str, ...] = POPULAR_STATE_FIPS,
) -> list[PrecomputeJob]:
    """Build cache jobs for chosen House-size anchors and popular states."""
    jobs: list[PrecomputeJob] = []
    for cap in caps:
        apportioned = apportionment_fn(cap)
        for state_fips in states:
            seats = int(apportioned[state_fips])
            jobs.append(
                PrecomputeJob(
                    state_fips=state_fips,
                    cap=cap,
                    seats=seats,
                    cache_key=district_plan_cache_key(state_fips, cap, seats),
                    compute_tier=compute_tier(seats),
                )
            )
    return jobs
