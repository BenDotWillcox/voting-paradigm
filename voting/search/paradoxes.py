"""
Exhaustive search for the smallest specimen of each criterion failure.

Each search walks profiles in order of size (the voter count a specimen is
measured by) and, within a size, in the canonical enumeration order, then
tries each transformation in a fixed order. The first decisive violation is
therefore minimal: no specimen with fewer voters exists among the profiles
and transformations searched. Finding none up to the bound shows only that,
never that the method satisfies the criterion.

What each search covers, for profiles of up to `max_voters` voters:
- majority, Condorcet winner, Condorcet loser: every profile
- monotonicity: every profile, raising the winner to any higher position for
  any number of the voters who cast one ranking
- participation: every profile plus any number of new voters with one
  ranking; size counts the newcomers
- consistency: every pair of profiles; size is their combined voters
- independence of irrelevant alternatives: every profile, removing each
  losing candidate
- independence of clones: every profile in which two candidates are ranked
  next to each other by every voter, against the profile without the later
  of the two
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from ..ballots.ranked_profile import RankedProfile
from ..criteria.single_profile import pairwise_counts
from ..criteria.transformations import are_clones, combine, raise_candidate, remove_candidate
from ..types import CandidateId
from .enumeration import profiles, rankings
from .outcomes import RANKED_METHODS, Outcome, RankedMethod, outcome
from .specimens import (
    AddClone,
    AddVoters,
    Combine,
    Criterion,
    Raise,
    RemoveCandidate,
    Specimen,
    SpecimenProfile,
    criterion_focus,
)
from .tables import NOT_DECISIVE, IntArray, WinnerTable, build_winner_table

DEFAULT_CANDIDATES: tuple[CandidateId, ...] = ("A", "B", "C")

# Profile pairs checked per array chunk in the consistency search
_CHUNK_PAIRS = 1 << 19


@dataclass(frozen=True)
class SearchResult:
    """The outcome of one exhaustive search."""
    method: RankedMethod
    criterion: Criterion
    candidates: tuple[CandidateId, ...]
    max_voters: int
    # The minimal specimen, or None if there is none up to max_voters
    specimen: Specimen | None


def search(
    method: RankedMethod,
    criterion: Criterion,
    max_voters: int,
    candidates: Sequence[CandidateId] = DEFAULT_CANDIDATES,
) -> SearchResult:
    """Find the smallest specimen of `method` failing `criterion`, if any."""
    candidate_tuple = tuple(candidates)
    finder = _FINDERS[criterion]
    specimen = finder(method, criterion, candidate_tuple, max_voters)
    return SearchResult(
        method=method,
        criterion=criterion,
        candidates=candidate_tuple,
        max_voters=max_voters,
        specimen=specimen,
    )


def find_disagreement_cycle(
    max_voters: int,
    candidates: Sequence[CandidateId] = DEFAULT_CANDIDATES,
) -> RankedProfile | None:
    """
    The smallest majority cycle on which the ranked methods elect the most
    different winners, all decisively.

    A majority cycle here has no Condorcet winner and no tied pair.
    """
    for n in range(1, max_voters + 1):
        for profile in profiles(candidates, n):
            if not _is_majority_cycle(profile):
                continue
            outcomes = [outcome(m, profile) for m in RANKED_METHODS]
            if not all(o.decisive for o in outcomes):
                continue
            if len({o.winner for o in outcomes}) == len(candidates):
                return profile
    return None


# --- Finders ------------------------------------------------------------

Finder = Callable[[RankedMethod, Criterion, tuple[CandidateId, ...], int], Specimen | None]


def _decisive(method: RankedMethod, profile: RankedProfile) -> Outcome | None:
    result = outcome(method, profile)
    return result if result.decisive else None


def _find_single_profile(
    method: RankedMethod,
    criterion: Criterion,
    candidates: tuple[CandidateId, ...],
    max_voters: int,
) -> Specimen | None:
    for n in range(1, max_voters + 1):
        for profile in profiles(candidates, n):
            focus = criterion_focus(criterion, profile)
            if focus is None:
                continue
            result = _decisive(method, profile)
            if result is None:
                continue
            failed = result.winner == focus if criterion == "condorcet_loser" else result.winner != focus
            if failed:
                return Specimen(
                    method=method,
                    criterion=criterion,
                    profiles=(SpecimenProfile("profile", profile, result.winner),),
                    transformation=None,
                    focus=focus,
                    voters=n,
                )
    return None


def _find_monotonicity(
    method: RankedMethod,
    criterion: Criterion,
    candidates: tuple[CandidateId, ...],
    max_voters: int,
) -> Specimen | None:
    for n in range(1, max_voters + 1):
        for before in profiles(candidates, n):
            first = _decisive(method, before)
            if first is None:
                continue
            winner = first.winner
            for count, ranking in before.rows:
                for position in range(ranking.index(winner)):
                    for voters in range(1, count + 1):
                        after = raise_candidate(before, ranking, winner, position, voters)
                        second = _decisive(method, after)
                        if second is not None and second.winner != winner:
                            return Specimen(
                                method=method,
                                criterion=criterion,
                                profiles=(
                                    SpecimenProfile("before", before, winner),
                                    SpecimenProfile("after", after, second.winner),
                                ),
                                transformation=Raise(winner, ranking, position, voters),
                                focus=None,
                                voters=n,
                            )
    return None


def _find_participation(
    method: RankedMethod,
    criterion: Criterion,
    candidates: tuple[CandidateId, ...],
    max_voters: int,
) -> Specimen | None:
    ballots = rankings(candidates)
    for total in range(2, max_voters + 1):
        for added in range(1, total):
            for before in profiles(candidates, total - added):
                first = _decisive(method, before)
                if first is None:
                    continue
                for ranking in ballots:
                    newcomers = RankedProfile(candidates, ((added, ranking),))
                    after = combine(before, newcomers)
                    second = _decisive(method, after)
                    if (
                        second is not None
                        and second.winner != first.winner
                        and ranking.index(first.winner) < ranking.index(second.winner)
                    ):
                        return Specimen(
                            method=method,
                            criterion=criterion,
                            profiles=(
                                SpecimenProfile("before", before, first.winner),
                                SpecimenProfile("after", after, second.winner),
                            ),
                            transformation=AddVoters(ranking, added),
                            focus=None,
                            voters=total,
                        )
    return None


def _find_consistency(
    method: RankedMethod,
    criterion: Criterion,
    candidates: tuple[CandidateId, ...],
    max_voters: int,
) -> Specimen | None:
    # Pairs are too many to resolve one by one, so every profile is resolved
    # once into a table and pairs are checked as array lookups
    table = build_winner_table(method, candidates, max_voters)
    types = rankings(candidates)
    for total in range(2, max_voters + 1):
        for small in range(1, total // 2 + 1):
            pair = _first_inconsistent_pair(table, small, total - small)
            if pair is None:
                continue
            i, j = pair
            first = _profile_from_counts(candidates, types, table.sizes[small].counts[i])
            second = _profile_from_counts(candidates, types, table.sizes[total - small].counts[j])
            combined = combine(first, second)
            winner = candidates[int(table.sizes[small].winners[i])]
            combined_outcome = outcome(method, combined)
            return Specimen(
                method=method,
                criterion=criterion,
                profiles=(
                    SpecimenProfile("first", first, winner),
                    SpecimenProfile("second", second, winner),
                    SpecimenProfile("combined", combined, combined_outcome.winner),
                ),
                transformation=Combine(),
                focus=None,
                voters=total,
            )
    return None


def _first_inconsistent_pair(table: WinnerTable, small: int, large: int) -> tuple[int, int] | None:
    """
    The first pair of decisive profiles with the same winner whose pooled
    profile decisively elects someone else.

    "First" is the smallest index of the smaller profile, then of the larger,
    in enumeration order. For equal sizes each unordered pair is taken once.
    """
    firsts_table = table.sizes[small]
    seconds_table = table.sizes[large]
    best: tuple[int, int] | None = None
    for w in range(len(table.candidates)):
        firsts = np.flatnonzero(firsts_table.winners == w)
        seconds = np.flatnonzero(seconds_table.winners == w)
        if len(firsts) == 0 or len(seconds) == 0:
            continue
        rows = max(1, _CHUNK_PAIRS // len(seconds))
        for start in range(0, len(firsts), rows):
            chunk = firsts[start:start + rows]
            if best is not None and chunk[0] > best[0]:
                break
            sums = firsts_table.counts[chunk][:, None, :] + seconds_table.counts[seconds][None, :, :]
            pooled = table.lookup(small + large, sums)
            inconsistent = (pooled != w) & (pooled != NOT_DECISIVE)
            if small == large:
                inconsistent &= seconds[None, :] > chunk[:, None]
            hits = np.argwhere(inconsistent)
            if len(hits):
                row, column = hits[0]
                pair = (int(chunk[row]), int(seconds[column]))
                if best is None or pair < best:
                    best = pair
                break
    return best


def _profile_from_counts(
    candidates: tuple[CandidateId, ...],
    types: tuple[tuple[CandidateId, ...], ...],
    counts: IntArray,
) -> RankedProfile:
    return RankedProfile(
        candidates=candidates,
        rows=tuple((int(count), ranking) for count, ranking in zip(counts, types) if count),
    )


def _find_iia(
    method: RankedMethod,
    criterion: Criterion,
    candidates: tuple[CandidateId, ...],
    max_voters: int,
) -> Specimen | None:
    for n in range(1, max_voters + 1):
        for before in profiles(candidates, n):
            first = _decisive(method, before)
            if first is None:
                continue
            for loser in candidates:
                if loser == first.winner:
                    continue
                after = remove_candidate(before, loser)
                second = _decisive(method, after)
                if second is not None and second.winner != first.winner:
                    return Specimen(
                        method=method,
                        criterion=criterion,
                        profiles=(
                            SpecimenProfile("before", before, first.winner),
                            SpecimenProfile("after", after, second.winner),
                        ),
                        transformation=RemoveCandidate(loser),
                        focus=None,
                        voters=n,
                    )
    return None


def _find_clones(
    method: RankedMethod,
    criterion: Criterion,
    candidates: tuple[CandidateId, ...],
    max_voters: int,
) -> Specimen | None:
    pairs = [
        (original, clone)
        for i, original in enumerate(candidates)
        for clone in candidates[i + 1:]
    ]
    for n in range(1, max_voters + 1):
        for after in profiles(candidates, n):
            for original, clone in pairs:
                if not are_clones(after, original, clone):
                    continue
                before = remove_candidate(after, clone)
                first = _decisive(method, before)
                second = _decisive(method, after)
                if first is None or second is None:
                    continue
                if first.winner == original:
                    failed = second.winner not in (original, clone)
                else:
                    failed = second.winner != first.winner
                if failed:
                    return Specimen(
                        method=method,
                        criterion=criterion,
                        profiles=(
                            SpecimenProfile("before", before, first.winner),
                            SpecimenProfile("after", after, second.winner),
                        ),
                        transformation=AddClone(original, clone),
                        focus=None,
                        voters=n,
                    )
    return None


_FINDERS: dict[Criterion, Finder] = {
    "majority": _find_single_profile,
    "condorcet_winner": _find_single_profile,
    "condorcet_loser": _find_single_profile,
    "monotonicity": _find_monotonicity,
    "participation": _find_participation,
    "consistency": _find_consistency,
    "iia": _find_iia,
    "clones": _find_clones,
}


def _is_majority_cycle(profile: RankedProfile) -> bool:
    matrix = pairwise_counts(profile)
    candidates = profile.candidates
    if any(
        matrix[a][b] == matrix[b][a]
        for i, a in enumerate(candidates)
        for b in candidates[i + 1:]
    ):
        return False
    return not any(
        all(matrix[a][b] > matrix[b][a] for b in candidates if b != a)
        for a in candidates
    )
