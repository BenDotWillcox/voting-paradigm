"""
Atlas: who each method elects as one voter cloud slides across the plane.

Ka-Ping Yee's spatial diagrams (2005), for seven methods. Candidates stay
put; every cell of a square grid holds the same voter cloud centered there,
and each method's map colors the cell by its winner.

Every cell is counted by the reference methods, exactly as the instrument
counts a profile (voting.spatial.counting). Neighboring cells mostly cast
identical ballots, so each distinct set of ballots is counted once per
method.

Three reference maps sit beside the methods:
- the Condorcet winner of the sincere rankings, where there is one
- the utilitarian winner: the least total raw distance, so a welfare
  benchmark on distances rather than on each voter's rescaled utilities
- disagreement: how many different winners the seven methods produce
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from ..ballot_models import SINCERE_V1, BallotModel
from ..search.outcomes import SearchMethod
from ..types import DEFAULT_TIEBREAK_SEED, CandidateId
from .counting import COUNTED_METHODS, ProfileCounter
from .electorate import (
    DEFAULT_CLOUD,
    Point,
    VoterCloud,
    check_layout,
    cloud_distances,
    cloud_utilities,
)

ATLAS_METHODS: tuple[SearchMethod, ...] = COUNTED_METHODS
DEFAULT_GRID = 64


@dataclass(frozen=True)
class MethodMap:
    """One method's winner in every cell, row-major from the top left."""
    # Index into the atlas's candidates
    winners: tuple[int, ...]
    # False where a tiebreak decided the winner
    decisive: tuple[bool, ...]


@dataclass(frozen=True)
class Atlas:
    """Winner maps for a candidate layout, and the reference maps."""
    candidates: tuple[CandidateId, ...]
    positions: tuple[Point, ...]
    # Cells per side; cell (row, col) is centered at ((col + 0.5) / size, (row + 0.5) / size)
    size: int
    cloud: VoterCloud
    ballot_model: str
    tiebreak_seed: int
    maps: Mapping[SearchMethod, MethodMap]
    # Index of the Condorcet winner, or -1 where the majority relation has none
    condorcet: tuple[int, ...]
    # Index of the candidate with the least total distance; ties go to the first
    utilitarian: tuple[int, ...]
    # Number of different winners among the methods
    disagreement: tuple[int, ...]


def cell_center(cell: int, size: int) -> Point:
    """The center of a row-major cell in the unit square."""
    row, col = divmod(cell, size)
    return ((col + 0.5) / size, (row + 0.5) / size)


def compute_atlas(
    candidates: Sequence[CandidateId],
    positions: Sequence[Point],
    size: int = DEFAULT_GRID,
    cloud: VoterCloud = DEFAULT_CLOUD,
    tiebreak_seed: int = DEFAULT_TIEBREAK_SEED,
    model: BallotModel = SINCERE_V1,
) -> Atlas:
    """
    Count every cell of the grid under every method.

    Raises:
        InvalidLayoutError: If candidates and positions do not match
    """
    check_layout(candidates, positions)
    if size < 1:
        raise ValueError("The grid needs at least one cell")
    ids = tuple(candidates)
    cells = size * size
    centers = np.array([cell_center(cell, size) for cell in range(cells)], dtype=np.float64)
    distances = cloud_distances(centers, positions, cloud)
    utilities = cloud_utilities(distances)
    totals = distances.sum(axis=1)

    counter = ProfileCounter(ids, tiebreak_seed, model)
    winners: dict[SearchMethod, list[int]] = {m: [] for m in ATLAS_METHODS}
    decisive: dict[SearchMethod, list[bool]] = {m: [] for m in ATLAS_METHODS}
    condorcet: list[int] = []
    disagreement: list[int] = []

    for cell in range(cells):
        count = counter.count([(cloud.voters_per_type, row) for row in utilities[cell].tolist()])
        for method in ATLAS_METHODS:
            winners[method].append(count.winners[method])
            decisive[method].append(count.decisive[method])
        disagreement.append(len(set(count.winners.values())))
        condorcet.append(count.condorcet)

    return Atlas(
        candidates=ids,
        positions=tuple((float(x), float(y)) for x, y in positions),
        size=size,
        cloud=cloud,
        ballot_model=model.model_id,
        tiebreak_seed=tiebreak_seed,
        maps={m: MethodMap(tuple(winners[m]), tuple(decisive[m])) for m in ATLAS_METHODS},
        condorcet=tuple(condorcet),
        utilitarian=tuple(int(i) for i in totals.argmin(axis=1)),
        disagreement=tuple(disagreement),
    )
