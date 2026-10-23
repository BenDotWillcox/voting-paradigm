"""
Counting voter types under all seven methods, exactly as the instrument does.

The sincere ballot model casts each type's ballots, and every method gets a
fresh tiebreak seeded with the counter's seed, as the profile endpoint gives
each method its own (api/services/profile_resolution.py). A ProfileCounter
resolves each distinct set of ballots once per method, so a caller counting
many similar electorates, such as the atlas's neighboring cells, pays once.

Used by: the atlas, and the methods simulation in eval/.
"""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeVar

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

COUNTED_METHODS: tuple[SearchMethod, ...] = RANKED_METHODS + RATED_METHODS

K = TypeVar("K")


@dataclass(frozen=True)
class Count:
    """Every method's winner on one electorate, and its Condorcet winner."""
    # Index into the counter's candidates
    winners: Mapping[SearchMethod, int]
    # False where a tiebreak decided the winner
    decisive: Mapping[SearchMethod, bool]
    # Index of the Condorcet winner of the sincere rankings, or -1
    condorcet: int


class ProfileCounter:
    """Counts electorates over a fixed set of candidates."""

    def __init__(
        self,
        candidates: Sequence[CandidateId],
        tiebreak_seed: int = DEFAULT_TIEBREAK_SEED,
        model: BallotModel = SINCERE_V1,
    ) -> None:
        self.ids = tuple(candidates)
        self.tiebreak_seed = tiebreak_seed
        self.model = model
        self._candidates = [Candidate(id=c, name=c) for c in self.ids]
        self._cast: dict[tuple[int, ...], VoterBallots] = {}
        self._outcomes: dict[tuple[SearchMethod, object], tuple[int, bool]] = {}
        self._profiles: dict[object, RankedProfile] = {}
        self._condorcet: dict[RankedProfile, int] = {}

    def count(self, rows: Sequence[tuple[int, Sequence[int]]]) -> Count:
        """
        Count voter types given as (voters, utilities in candidate order).

        Raises:
            InvalidProfileError: If a row's utilities do not fit the candidates
        """
        ballots = [(n, self._ballots(tuple(u))) for n, u in rows]
        rankings = self._rankings(_key(ballots, lambda b: b.ranking))
        keys: dict[SearchMethod, object] = {
            "approval": _key(ballots, lambda b: b.approvals),
            "score": _key(ballots, lambda b: tuple(b.scores[c] for c in self.ids)),
            "quadratic": _key(
                ballots, lambda b: (tuple(sorted(b.allocations.items())), b.credit_budget)
            ),
        }
        winners: dict[SearchMethod, int] = {}
        decisive: dict[SearchMethod, bool] = {}
        for method in COUNTED_METHODS:
            winners[method], decisive[method] = self._outcome(
                method, rankings if method in RANKED_METHODS else keys[method]
            )
        return Count(winners, decisive, self._condorcet_of(rankings))

    def _ballots(self, utilities: tuple[int, ...]) -> VoterBallots:
        cast = self._cast.get(utilities)
        if cast is None:
            cast = self.model.cast(self.ids, utilities)
            self._cast[utilities] = cast
        return cast

    def _rankings(self, key: tuple[tuple[tuple[CandidateId, ...], int], ...]) -> RankedProfile:
        profile = self._profiles.get(key)
        if profile is None:
            profile = create_ranked_profile(self.ids, [(n, list(r)) for r, n in key])
            self._profiles[key] = profile
        return profile

    def _condorcet_of(self, profile: RankedProfile) -> int:
        if profile not in self._condorcet:
            found = condorcet_winner(profile)
            self._condorcet[profile] = self.ids.index(found) if found is not None else -1
        return self._condorcet[profile]

    def _outcome(self, method: SearchMethod, ballots: object) -> tuple[int, bool]:
        cached = self._outcomes.get((method, ballots))
        if cached is None:
            result = self._resolve(method, ballots)
            cached = (self.ids.index(result.winners[0]), is_decisive(result))
            self._outcomes[(method, ballots)] = cached
        return cached

    def _resolve(self, method: SearchMethod, ballots: object) -> ElectionResult:
        # A fresh tiebreak per count, as the profile endpoint gives each method
        tiebreak = random_tiebreak(self.tiebreak_seed)
        if isinstance(ballots, RankedProfile):
            ranked = _ranked_ballots(ballots)
            if method == "plurality":
                return resolve_plurality(self._candidates, _first_choices(ballots), tiebreak)
            if method == "irv":
                return resolve_irv(self._candidates, ranked, tiebreak)
            if method == "borda":
                return resolve_borda(self._candidates, ranked, tiebreak)
            return resolve_ranked_pairs(
                self._candidates,
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
            return resolve_approval(self._candidates, approvals, tiebreak)
        if method == "score":
            scores: list[ScoreBallot] = []
            for values, n in key:
                scores += [create_score_ballot("v", dict(zip(self.ids, values)))] * n
            return resolve_score(self._candidates, scores, tiebreak)
        quadratic: list[QuadraticBallot] = []
        for (allocations, budget), n in key:
            quadratic += [create_quadratic_ballot("v", dict(allocations), credit_budget=budget)] * n
        return resolve_quadratic(self._candidates, quadratic, tiebreak)


def _key(
    ballots: Sequence[tuple[int, VoterBallots]],
    part: Callable[[VoterBallots], K],
) -> tuple[tuple[K, int], ...]:
    """One ballot format's ballots as a canonical multiset."""
    tally: Counter[K] = Counter()
    for n, ballot in ballots:
        tally[part(ballot)] += n
    return tuple(sorted(tally.items(), key=repr))


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
