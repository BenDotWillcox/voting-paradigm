"""
Atlas: who each method elects as one voter cloud slides across the plane.

Ka-Ping Yee's spatial diagrams (2005), for seven methods. Candidates stay
put; every cell of a square grid holds the same voter cloud centered there,
and each method's map colors the cell by its winner.

Every cell is counted by the reference methods, exactly as the instrument
counts a profile (api/services/profile_resolution.py): the sincere ballot
model casts the ballots, and each method gets a fresh tiebreak seeded with
the atlas's seed. Neighboring cells mostly cast identical ballots, so each
distinct set of ballots is counted once per method, and Ranked Pairs reads
its pairwise matrix from the aggregated rankings rather than ballot by
ballot.

Three reference maps sit beside the methods:
- the Condorcet winner of the sincere rankings, where there is one
- the utilitarian winner: the least total raw distance, so a welfare
  benchmark on distances rather than on each voter's rescaled utilities
- disagreement: how many different winners the seven methods produce
"""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import TypeVar

import numpy as np

from ..ballot_models import SINCERE_V1, BallotModel, VoterBallots
from ..ballots.approval import ApprovalBallot, create_approval_ballot
from ..ballots.quadratic import QuadraticBallot, create_quadratic_ballot
from ..ballots.ranked_choice import RankedChoiceBallot, create_ranked_choice_ballot
from ..ballots.ranked_profile import RankedProfile, create_ranked_profile
from ..ballots.score import ScoreBallot, create_score_ballot
from ..ballots.single_choice import SingleChoiceBallot, create_single_choice_ballot
from ..criteria import condorcet_winner, pairwise_counts
from ..methods.approval import resolve_approval
from ..methods.borda import resolve_borda
from ..methods.irv import resolve_irv
from ..methods.plurality import resolve_plurality
from ..methods.quadratic import resolve_quadratic
from ..methods.ranked_pairs import resolve_ranked_pairs
from ..methods.score import resolve_score
from ..search.outcomes import RANKED_METHODS, RATED_METHODS, SearchMethod, is_decisive
from ..types import DEFAULT_TIEBREAK_SEED, Candidate, CandidateId, ElectionResult, random_tiebreak
from .electorate import (
    DEFAULT_CLOUD,
    Point,
    VoterCloud,
    check_layout,
    cloud_distances,
    cloud_utilities,
)

ATLAS_METHODS: tuple[SearchMethod, ...] = RANKED_METHODS + RATED_METHODS
DEFAULT_GRID = 64

# A distinct set of ballots: each ballot (in some hashable form) and its count
BallotKey = tuple[tuple[object, int], ...]

K = TypeVar("K")


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

    @lru_cache(maxsize=None)
    def cast(row: tuple[int, ...]) -> VoterBallots:
        return model.cast(ids, row)

    counter = _Counter(ids, tiebreak_seed)
    winners: dict[SearchMethod, list[int]] = {m: [] for m in ATLAS_METHODS}
    decisive: dict[SearchMethod, list[bool]] = {m: [] for m in ATLAS_METHODS}
    condorcet: list[int] = []
    disagreement: list[int] = []
    count = cloud.voters_per_type

    for cell in range(cells):
        ballots = [cast(tuple(row)) for row in utilities[cell].tolist()]
        rankings = counter.rankings(_key(ballots, count, lambda b: b.ranking))
        keys: dict[SearchMethod, object] = {
            "approval": _key(ballots, count, lambda b: b.approvals),
            "score": _key(ballots, count, lambda b: tuple(b.scores[c] for c in ids)),
            "quadratic": _key(
                ballots, count, lambda b: (tuple(sorted(b.allocations.items())), b.credit_budget)
            ),
        }
        cell_winners: set[int] = set()
        for method in ATLAS_METHODS:
            winner, was_decisive = counter.outcome(method, rankings if method in RANKED_METHODS else keys[method])
            winners[method].append(winner)
            decisive[method].append(was_decisive)
            cell_winners.add(winner)
        disagreement.append(len(cell_winners))
        found = counter.condorcet(rankings)
        condorcet.append(ids.index(found) if found is not None else -1)

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


def _key(
    ballots: Sequence[VoterBallots],
    count: int,
    part: Callable[[VoterBallots], K],
) -> tuple[tuple[K, int], ...]:
    """One ballot format's ballots as a canonical multiset."""
    tally: Counter[K] = Counter()
    for ballot in ballots:
        tally[part(ballot)] += count
    return tuple(sorted(tally.items(), key=repr))


class _Counter:
    """Resolves each distinct set of ballots once per method."""

    def __init__(self, ids: tuple[CandidateId, ...], seed: int) -> None:
        self.ids = ids
        self.seed = seed
        self.candidates = [Candidate(id=c, name=c) for c in ids]
        self._outcomes: dict[tuple[SearchMethod, object], tuple[int, bool]] = {}
        self._profiles: dict[object, RankedProfile] = {}
        self._condorcet: dict[RankedProfile, CandidateId | None] = {}

    def rankings(self, key: tuple[tuple[tuple[CandidateId, ...], int], ...]) -> RankedProfile:
        profile = self._profiles.get(key)
        if profile is None:
            profile = create_ranked_profile(self.ids, [(n, list(r)) for r, n in key])
            self._profiles[key] = profile
        return profile

    def condorcet(self, profile: RankedProfile) -> CandidateId | None:
        if profile not in self._condorcet:
            self._condorcet[profile] = condorcet_winner(profile)
        return self._condorcet[profile]

    def outcome(self, method: SearchMethod, ballots: object) -> tuple[int, bool]:
        cached = self._outcomes.get((method, ballots))
        if cached is None:
            result = self._resolve(method, ballots)
            cached = (self.ids.index(result.winners[0]), is_decisive(result))
            self._outcomes[(method, ballots)] = cached
        return cached

    def _resolve(self, method: SearchMethod, ballots: object) -> ElectionResult:
        # A fresh tiebreak per count, as the profile endpoint gives each method
        tiebreak = random_tiebreak(self.seed)
        if isinstance(ballots, RankedProfile):
            ranked = _ranked_ballots(ballots)
            if method == "plurality":
                return resolve_plurality(self.candidates, _first_choices(ballots), tiebreak)
            if method == "irv":
                return resolve_irv(self.candidates, ranked, tiebreak)
            if method == "borda":
                return resolve_borda(self.candidates, ranked, tiebreak)
            return resolve_ranked_pairs(
                self.candidates,
                ranked,
                tiebreak,
                pairwise_matrix=pairwise_counts(ballots),
                include_pairwise_matrix=False,
            )
        key = ballots
        assert isinstance(key, tuple)
        if method == "approval":
            approvals: list[ApprovalBallot] = []
            for approved, n in key:
                approvals += [create_approval_ballot("v", list(approved))] * n
            return resolve_approval(self.candidates, approvals, tiebreak)
        if method == "score":
            scores: list[ScoreBallot] = []
            for values, n in key:
                scores += [create_score_ballot("v", dict(zip(self.ids, values)))] * n
            return resolve_score(self.candidates, scores, tiebreak)
        quadratic: list[QuadraticBallot] = []
        for (allocations, budget), n in key:
            quadratic += [create_quadratic_ballot("v", dict(allocations), credit_budget=budget)] * n
        return resolve_quadratic(self.candidates, quadratic, tiebreak)


def _ranked_ballots(profile: RankedProfile) -> list[RankedChoiceBallot]:
    """One shared, read-only ballot per ranking, repeated per voter."""
    ballots: list[RankedChoiceBallot] = []
    for count, ranking in profile.rows:
        ballot = create_ranked_choice_ballot("v", list(ranking), list(profile.candidates))
        ballots += [ballot] * count
    return ballots


def _first_choices(profile: RankedProfile) -> list[SingleChoiceBallot]:
    ballots: list[SingleChoiceBallot] = []
    for count, ranking in profile.rows:
        ballots += [create_single_choice_ballot("v", ranking[0])] * count
    return ballots
