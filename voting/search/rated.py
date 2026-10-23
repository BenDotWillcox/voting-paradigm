"""
Exhaustive search for the smallest specimens of rated methods failing a
criterion, under a ballot model.

Rated methods read ballots that depend on how strongly voters prefer each
candidate, so this search walks utility profiles, not rankings. A voter type
is a ranking of three candidates plus where the middle candidate sits
between the favorite (100) and the least favorite (0): 25, 50 or 75. The
sincere model ignores rescaling, so these 18 types stand for every voter
whose middle candidate sits at one of those three points.

Approval, score and quadratic voting each total every candidate's ballot
values and elect the unique highest total. So each voter type's ballots are
built once by the ballot model, whole batches of profiles are totaled as
matrix products, and the reference methods certify every specimen found
(specimens.certify). Criteria are judged on the voters' sincere rankings.

What each search covers, for profiles of up to `max_voters` voters:
- majority, Condorcet winner, Condorcet loser: every profile
- monotonicity: every profile, moving any number of one type's voters to a
  type whose utilities are a rescaling of theirs with the winner raised
  (utility_transformations.is_raise)
- participation: every profile plus any number of new voters of one type
- consistency: every pair of profiles
- independence of irrelevant alternatives: every profile, removing each
  losing candidate
- independence of clones: every profile, adding an exact clone of each
  candidate as a fourth candidate
"""

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import numpy.typing as npt

from ..ballot_models import SINCERE_V1, BallotModel, UtilityProfile
from ..ballot_models.utility_profile import create_utility_profile
from ..criteria.utility_transformations import add_clone, is_raise, remove_candidate
from ..types import CandidateId
from .enumeration import rankings
from .outcomes import RatedMethod
from .specimens import (
    AddClone,
    AddUtilityVoters,
    Combine,
    Criterion,
    RaiseUtility,
    RemoveCandidate,
    Specimen,
    SpecimenProfile,
)

DEFAULT_MIDDLES: tuple[int, ...] = (25, 50, 75)
CLONE = "D"

IntArray = npt.NDArray[np.int64]
# Profiles as rows of voter-type counts; small enough for int16
CountArray = npt.NDArray[np.int16]

# Profile pairs or moves checked per array chunk
_CHUNK = 1 << 19


def voter_types(
    candidates: Sequence[CandidateId],
    middles: Sequence[int] = DEFAULT_MIDDLES,
) -> tuple[tuple[int, ...], ...]:
    """Every ranking of three candidates with each middle placement, in order."""
    if len(candidates) != 3:
        raise ValueError("Voter types are defined for three candidates")
    types: list[tuple[int, ...]] = []
    for ranking in rankings(candidates):
        for middle in middles:
            values = {ranking[0]: 100, ranking[1]: middle, ranking[2]: 0}
            types.append(tuple(values[c] for c in candidates))
    return tuple(types)


@dataclass(frozen=True)
class TypeBallots:
    """Each voter type's ballots in every rated format, as matrices."""
    candidates: tuple[CandidateId, ...]
    approval: IntArray
    score: IntArray
    quadratic: IntArray
    # first[t][c] = 1 if type t ranks c first
    first: IntArray
    # prefers[t][a][b] = 1 if type t ranks a above b
    prefers: IntArray

    def matrix(self, method: RatedMethod) -> IntArray:
        return {"approval": self.approval, "score": self.score, "quadratic": self.quadratic}[method]


def type_ballots(
    candidates: Sequence[CandidateId],
    types: Sequence[tuple[int, ...]],
    model: BallotModel = SINCERE_V1,
) -> TypeBallots:
    """Cast every voter type with the ballot model."""
    k = len(candidates)
    t = len(types)
    approval = np.zeros((t, k), dtype=np.int64)
    score = np.zeros((t, k), dtype=np.int64)
    quadratic = np.zeros((t, k), dtype=np.int64)
    first = np.zeros((t, k), dtype=np.int64)
    prefers = np.zeros((t, k, k), dtype=np.int64)
    index = {c: i for i, c in enumerate(candidates)}
    for row, utilities in enumerate(types):
        ballots = model.cast(candidates, utilities)
        for c in ballots.approvals:
            approval[row, index[c]] = 1
        for c, value in ballots.scores.items():
            score[row, index[c]] = value
        for c, votes in ballots.allocations.items():
            quadratic[row, index[c]] = votes
        first[row, index[ballots.choice]] = 1
        for i, above in enumerate(ballots.ranking):
            for below in ballots.ranking[i + 1:]:
                prefers[row, index[above], index[below]] = 1
    return TypeBallots(tuple(candidates), approval, score, quadratic, first, prefers)


def winners(totals: IntArray) -> IntArray:
    """Index of each row's unique highest total, or -1 when it ties."""
    top = totals.max(axis=1)
    unique = (totals == top[:, None]).sum(axis=1) == 1
    return np.where(unique, totals.argmax(axis=1), -1)


@lru_cache(maxsize=None)
def count_vectors(total: int, parts: int) -> CountArray:
    """
    Every count vector over `parts` types summing to `total`, in canonical
    order. Sixteen-bit counts keep the largest sizes in memory; products
    with the int64 ballot matrices widen automatically.
    """
    if parts == 1:
        return np.array([[total]], dtype=np.int16)
    blocks = []
    for first in range(total, -1, -1):
        rest = count_vectors(total - first, parts - 1)
        blocks.append(np.hstack([np.full((len(rest), 1), first, dtype=np.int16), rest]))
    return np.vstack(blocks)


# --- Search ----------------------------------------------------------------

@dataclass(frozen=True)
class _Space:
    candidates: tuple[CandidateId, ...]
    types: tuple[tuple[int, ...], ...]
    ballots: TypeBallots

    def profile(self, counts: Sequence[int]) -> UtilityProfile:
        return create_utility_profile(
            self.candidates,
            [
                (int(count), dict(zip(self.candidates, self.types[t])))
                for t, count in enumerate(counts)
                if count
            ],
        )


def search_rated(
    method: RatedMethod,
    criterion: Criterion,
    max_voters: int,
    candidates: Sequence[CandidateId] = ("A", "B", "C"),
    middles: Sequence[int] = DEFAULT_MIDDLES,
) -> Specimen | None:
    """The smallest specimen of `method` failing `criterion`, if any."""
    types = voter_types(candidates, middles)
    space = _Space(tuple(candidates), types, type_ballots(candidates, types))
    finder = {
        "majority": _single_profile,
        "condorcet_winner": _single_profile,
        "condorcet_loser": _single_profile,
        "monotonicity": _monotonicity,
        "participation": _participation,
        "consistency": _consistency,
        "iia": _iia,
        "clones": _clones,
    }[criterion]
    return finder(space, method, criterion, max_voters)


def _focus(space: _Space, criterion: Criterion, counts: CountArray) -> IntArray:
    """Each profile's majority winner, Condorcet winner or Condorcet loser, or -1."""
    n = counts.sum(axis=1)
    k = len(space.candidates)
    if criterion == "majority":
        first = counts @ space.ballots.first
        majority = 2 * first > n[:, None]
        return np.where(majority.any(axis=1), majority.argmax(axis=1), -1)
    pairwise = np.einsum("pt,tab->pab", counts, space.ballots.prefers)
    beats = pairwise > pairwise.transpose(0, 2, 1)
    off_diagonal = ~np.eye(k, dtype=bool)
    if criterion == "condorcet_winner":
        wins_all = (beats | ~off_diagonal).all(axis=2)
    else:
        loses = pairwise < pairwise.transpose(0, 2, 1)
        wins_all = (loses | ~off_diagonal).all(axis=2)
    return np.where(wins_all.any(axis=1), wins_all.argmax(axis=1), -1)


def _single_profile(space: _Space, method: RatedMethod, criterion: Criterion, max_voters: int) -> Specimen | None:
    matrix = space.ballots.matrix(method)
    for n in range(1, max_voters + 1):
        counts = count_vectors(n, len(space.types))
        won = winners(counts @ matrix)
        focus = _focus(space, criterion, counts)
        if criterion == "condorcet_loser":
            bad = (focus >= 0) & (won == focus)
        else:
            bad = (focus >= 0) & (won >= 0) & (won != focus)
        hits = np.flatnonzero(bad)
        if len(hits):
            i = int(hits[0])
            return Specimen(
                method=method,
                criterion=criterion,
                profiles=(SpecimenProfile("profile", space.profile(counts[i]), space.candidates[won[i]]),),
                transformation=None,
                focus=space.candidates[focus[i]],
                voters=n,
            )
    return None


def _monotonicity(space: _Space, method: RatedMethod, criterion: Criterion, max_voters: int) -> Specimen | None:
    matrix = space.ballots.matrix(method)
    t = len(space.types)
    k = len(space.candidates)
    raises = [
        [(a, b) for a in range(t) for b in range(t) if a != b and is_raise(space.types[a], space.types[b], w)]
        for w in range(k)
    ]
    for n in range(1, max_voters + 1):
        counts = count_vectors(n, t)
        won = winners(counts @ matrix)
        best: tuple[int, int, int, int] | None = None
        for w in range(k):
            rows = np.flatnonzero(won == w)
            if len(rows) == 0:
                continue
            for a, b in raises[w]:
                for moved in range(1, n + 1):
                    eligible = rows[counts[rows, a] >= moved]
                    if len(eligible) == 0:
                        break
                    if best is not None and eligible[0] > best[0]:
                        continue
                    after = counts[eligible].copy()
                    after[:, a] -= moved
                    after[:, b] += moved
                    new = winners(after @ matrix)
                    hits = np.flatnonzero((new >= 0) & (new != w))
                    if len(hits):
                        candidate = (int(eligible[hits[0]]), a, b, moved)
                        if best is None or candidate < best:
                            best = candidate
        if best is not None:
            i, a, b, moved = best
            before = space.profile(counts[i])
            after_counts = counts[i].copy()
            after_counts[a] -= moved
            after_counts[b] += moved
            w = int(won[i])
            new_winner = int(winners((after_counts @ matrix)[None, :])[0])
            return Specimen(
                method=method,
                criterion=criterion,
                profiles=(
                    SpecimenProfile("before", before, space.candidates[w]),
                    SpecimenProfile("after", space.profile(after_counts), space.candidates[new_winner]),
                ),
                transformation=RaiseUtility(space.candidates[w], space.types[a], space.types[b], moved),
                focus=None,
                voters=n,
            )
    return None


def _participation(space: _Space, method: RatedMethod, criterion: Criterion, max_voters: int) -> Specimen | None:
    matrix = space.ballots.matrix(method)
    t = len(space.types)
    prefers = space.ballots.prefers
    for total in range(2, max_voters + 1):
        for added in range(1, total):
            counts = count_vectors(total - added, t)
            totals = counts @ matrix
            won = winners(totals)
            for kind in range(t):
                new = winners(totals + added * matrix[kind])
                prefers_old = prefers[kind][np.maximum(won, 0), np.maximum(new, 0)] == 1
                hits = np.flatnonzero((won >= 0) & (new >= 0) & (new != won) & prefers_old)
                if len(hits):
                    i = int(hits[0])
                    after_counts = counts[i].copy()
                    after_counts[kind] += added
                    return Specimen(
                        method=method,
                        criterion=criterion,
                        profiles=(
                            SpecimenProfile("before", space.profile(counts[i]), space.candidates[won[i]]),
                            SpecimenProfile("after", space.profile(after_counts), space.candidates[new[i]]),
                        ),
                        transformation=AddUtilityVoters(space.types[kind], added),
                        focus=None,
                        voters=total,
                    )
    return None


def _consistency(space: _Space, method: RatedMethod, criterion: Criterion, max_voters: int) -> Specimen | None:
    matrix = space.ballots.matrix(method)
    t = len(space.types)
    for total in range(2, max_voters + 1):
        for small in range(1, total // 2 + 1):
            firsts = count_vectors(small, t)
            seconds = count_vectors(total - small, t)
            first_totals = firsts @ matrix
            second_totals = seconds @ matrix
            first_won = winners(first_totals)
            second_won = winners(second_totals)
            rows = max(1, _CHUNK // len(seconds))
            for start in range(0, len(firsts), rows):
                chunk = np.arange(start, min(start + rows, len(firsts)))
                pooled = winners((first_totals[chunk][:, None, :] + second_totals[None, :, :]).reshape(-1, len(space.candidates)))
                pooled = pooled.reshape(len(chunk), len(seconds))
                same = (first_won[chunk][:, None] == second_won[None, :]) & (first_won[chunk][:, None] >= 0)
                bad = same & (pooled >= 0) & (pooled != first_won[chunk][:, None])
                if small == total - small:
                    bad &= np.arange(len(seconds))[None, :] > chunk[:, None]
                hits = np.argwhere(bad)
                if len(hits):
                    r, c = hits[0]
                    i, j = int(chunk[r]), int(c)
                    combined = firsts[i] + seconds[j]
                    w = space.candidates[first_won[i]]
                    return Specimen(
                        method=method,
                        criterion=criterion,
                        profiles=(
                            SpecimenProfile("first", space.profile(firsts[i]), w),
                            SpecimenProfile("second", space.profile(seconds[j]), w),
                            SpecimenProfile("combined", space.profile(combined), space.candidates[pooled[r, c]]),
                        ),
                        transformation=Combine(),
                        focus=None,
                        voters=total,
                    )
    return None


def _iia(space: _Space, method: RatedMethod, criterion: Criterion, max_voters: int) -> Specimen | None:
    matrix = space.ballots.matrix(method)
    reduced = []
    for loser in range(len(space.candidates)):
        keep = [i for i in range(len(space.candidates)) if i != loser]
        names = tuple(space.candidates[i] for i in keep)
        types = tuple(tuple(u[i] for i in keep) for u in space.types)
        reduced.append((loser, keep, names, type_ballots(names, types).matrix(method)))
    for n in range(1, max_voters + 1):
        counts = count_vectors(n, len(space.types))
        won = winners(counts @ matrix)
        best: tuple[int, int] | None = None
        for loser, keep, names, small in reduced:
            new = winners(counts @ small)
            mapped = np.where(new >= 0, np.array(keep)[np.maximum(new, 0)], -1)
            hits = np.flatnonzero((won >= 0) & (won != loser) & (mapped >= 0) & (mapped != won))
            if len(hits) and (best is None or (int(hits[0]), loser) < best):
                best = (int(hits[0]), loser)
        if best is not None:
            i, loser = best
            _, keep, names, small = reduced[loser]
            before = space.profile(counts[i])
            after = remove_candidate(before, space.candidates[loser])
            new_winner = names[int(winners((counts[i] @ small)[None, :])[0])]
            return Specimen(
                method=method,
                criterion=criterion,
                profiles=(
                    SpecimenProfile("before", before, space.candidates[won[i]]),
                    SpecimenProfile("after", after, new_winner),
                ),
                transformation=RemoveCandidate(space.candidates[loser]),
                focus=None,
                voters=n,
            )
    return None


def _clones(space: _Space, method: RatedMethod, criterion: Criterion, max_voters: int) -> Specimen | None:
    matrix = space.ballots.matrix(method)
    cloned = []
    for original in range(len(space.candidates)):
        names = space.candidates + (CLONE,)
        types = tuple(u + (u[original],) for u in space.types)
        cloned.append((original, type_ballots(names, types).matrix(method)))
    for n in range(1, max_voters + 1):
        counts = count_vectors(n, len(space.types))
        won = winners(counts @ matrix)
        best: tuple[int, int] | None = None
        for original, big in cloned:
            new = winners(counts @ big)
            clone_index = len(space.candidates)
            kept = (new == original) | (new == clone_index)
            bad = (won >= 0) & (new >= 0) & np.where(won == original, ~kept, new != won)
            hits = np.flatnonzero(bad)
            if len(hits) and (best is None or (int(hits[0]), original) < best):
                best = (int(hits[0]), original)
        if best is not None:
            i, original = best
            big = cloned[original][1]
            before = space.profile(counts[i])
            after = add_clone(before, space.candidates[original], CLONE)
            new_winner = (space.candidates + (CLONE,))[int(winners((counts[i] @ big)[None, :])[0])]
            return Specimen(
                method=method,
                criterion=criterion,
                profiles=(
                    SpecimenProfile("before", before, space.candidates[won[i]]),
                    SpecimenProfile("after", after, new_winner),
                ),
                transformation=AddClone(space.candidates[original], CLONE),
                focus=None,
                voters=n,
            )
    return None

