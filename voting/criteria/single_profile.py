"""
Criteria that can be checked against a single profile.

Each function names the candidate a criterion singles out, or None when the
profile has no such candidate. Whether a method honors the criterion is then
a comparison with that method's winner:

- Majority: a candidate ranked first by more than half the voters must win.
- Condorcet winner: a candidate who beats every other head to head must win.
- Condorcet loser: a candidate who loses to every other head to head must
  not win.

Criteria that compare two profiles (monotonicity, participation, consistency,
independence of irrelevant alternatives, independence of clones) need a
transformation between profiles and are not checked here.
"""

from ..ballots.ranked_profile import RankedProfile
from ..methods.ranked_pairs import PairwiseMatrix
from ..types import CandidateId


def pairwise_counts(profile: RankedProfile) -> PairwiseMatrix:
    """
    Count head-to-head preferences.

    matrix[a][b] = number of voters who rank a above b
    """
    matrix: PairwiseMatrix = {
        a: {b: 0 for b in profile.candidates if b != a}
        for a in profile.candidates
    }
    for count, ranking in profile.rows:
        for i, above in enumerate(ranking):
            for below in ranking[i + 1:]:
                matrix[above][below] += count
    return matrix


def majority_winner(profile: RankedProfile) -> CandidateId | None:
    """The candidate ranked first by more than half the voters, if any."""
    first_choices: dict[CandidateId, int] = {}
    for count, ranking in profile.rows:
        first_choices[ranking[0]] = first_choices.get(ranking[0], 0) + count
    for candidate, votes in first_choices.items():
        if 2 * votes > profile.total_voters:
            return candidate
    return None


def condorcet_winner(profile: RankedProfile) -> CandidateId | None:
    """The candidate who beats every other head to head, if any."""
    matrix = pairwise_counts(profile)
    for candidate in profile.candidates:
        if all(
            matrix[candidate][other] > matrix[other][candidate]
            for other in profile.candidates
            if other != candidate
        ):
            return candidate
    return None


def condorcet_loser(profile: RankedProfile) -> CandidateId | None:
    """The candidate who loses to every other head to head, if any."""
    matrix = pairwise_counts(profile)
    for candidate in profile.candidates:
        if all(
            matrix[candidate][other] < matrix[other][candidate]
            for other in profile.candidates
            if other != candidate
        ):
            return candidate
    return None
