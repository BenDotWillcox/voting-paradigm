"""
Specimens: concrete profiles that show a method failing a criterion.

A specimen holds every profile involved (one for single-profile criteria,
two or three for the rest), the winner in each, and the transformation that
links them. certify() re-resolves every profile with fresh ballots and checks
that the recorded winners, the transformation, and the violation all hold.

Ranked methods' specimens are ranked profiles. Rated methods' specimens are
utility profiles whose ballots come from the sincere ballot model; their
criteria are judged on the voters' sincere rankings.
"""

from dataclasses import dataclass
from typing import Literal, Union, cast

from ..ballot_models import SINCERE_V1, rankings_of
from ..ballot_models.utility_profile import UtilityProfile, create_utility_profile
from ..ballots.ranked_profile import RankedProfile, create_ranked_profile, profile_ballots
from ..criteria import utility_transformations as ut
from ..criteria.single_profile import condorcet_loser, condorcet_winner, majority_winner
from ..criteria.transformations import (
    are_clones,
    combine,
    raise_candidate,
    remove_candidate,
)
from ..types import CandidateId
from .outcomes import (
    RANKED_METHODS,
    RATED_METHODS,
    SearchMethod,
    is_decisive,
    resolve_profile,
    resolve_rated,
)

Criterion = Literal[
    "majority",
    "condorcet_winner",
    "condorcet_loser",
    "monotonicity",
    "participation",
    "consistency",
    "iia",
    "clones",
]

CRITERIA: tuple[Criterion, ...] = (
    "majority",
    "condorcet_winner",
    "condorcet_loser",
    "monotonicity",
    "participation",
    "consistency",
    "iia",
    "clones",
)

Role = Literal["profile", "before", "after", "first", "second", "combined"]

Profile = Union[RankedProfile, UtilityProfile]


class SpecimenError(ValueError):
    """Raised when a specimen does not demonstrate what it claims."""
    pass


@dataclass(frozen=True)
class SpecimenProfile:
    """One profile in a specimen and its decisive winner."""
    role: Role
    profile: Profile
    winner: CandidateId


@dataclass(frozen=True)
class Raise:
    """Some voters with one ranking move a candidate up."""
    candidate: CandidateId
    ranking: tuple[CandidateId, ...]
    position: int
    voters: int
    kind: Literal["raise"] = "raise"


@dataclass(frozen=True)
class RaiseUtility:
    """Some voters raise a candidate's utility and keep the rest."""
    candidate: CandidateId
    before: tuple[int, ...]
    after: tuple[int, ...]
    voters: int
    kind: Literal["raise_utility"] = "raise_utility"


@dataclass(frozen=True)
class AddVoters:
    """New voters who all cast the same ranking join the electorate."""
    ranking: tuple[CandidateId, ...]
    voters: int
    kind: Literal["add_voters"] = "add_voters"


@dataclass(frozen=True)
class AddUtilityVoters:
    """New voters who all hold the same utilities join the electorate."""
    utilities: tuple[int, ...]
    voters: int
    kind: Literal["add_utility_voters"] = "add_utility_voters"


@dataclass(frozen=True)
class Combine:
    """Two electorates are pooled."""
    kind: Literal["combine"] = "combine"


@dataclass(frozen=True)
class RemoveCandidate:
    """A losing candidate withdraws."""
    candidate: CandidateId
    kind: Literal["remove_candidate"] = "remove_candidate"


@dataclass(frozen=True)
class AddClone:
    """A clone joins, ranked next to the original by every voter."""
    candidate: CandidateId
    clone: CandidateId
    kind: Literal["add_clone"] = "add_clone"


Transformation = Union[Raise, RaiseUtility, AddVoters, AddUtilityVoters, Combine, RemoveCandidate, AddClone]


@dataclass(frozen=True)
class Specimen:
    """Profiles showing `method` failing `criterion`."""
    method: SearchMethod
    criterion: Criterion
    profiles: tuple[SpecimenProfile, ...]
    # How the profiles relate; None for single-profile criteria
    transformation: Transformation | None
    # The candidate a single-profile criterion singles out (majority winner,
    # Condorcet winner or Condorcet loser); None otherwise
    focus: CandidateId | None
    # The size minimality is measured by: voters in the largest profile
    voters: int

    @property
    def id(self) -> str:
        candidates = max(len(sp.profile.candidates) for sp in self.profiles)
        return f"{self.method}-{self.criterion}-{candidates}c"

    @property
    def ballot_model(self) -> str | None:
        """The model that turned utilities into ballots; None for ranked methods."""
        return SINCERE_V1.model_id if self.method in RATED_METHODS else None

    def profile(self, role: Role) -> SpecimenProfile:
        return next(sp for sp in self.profiles if sp.role == role)


def certify(specimen: Specimen) -> None:
    """
    Check a specimen against the reference methods.

    Every profile is resolved again from fresh ballots and must be decisive
    and elect the recorded winner; the transformation must turn the first
    profile(s) into the next; and the criterion must actually be violated.

    Raises:
        SpecimenError: If any of those checks fails
    """
    for sp in specimen.profiles:
        profile = sp.profile
        if specimen.method in RATED_METHODS:
            if not isinstance(profile, UtilityProfile):
                raise SpecimenError(f"{specimen.id}: rated specimens need utility profiles")
            result = resolve_rated(specimen.method, profile)
        else:
            if not isinstance(profile, RankedProfile):
                raise SpecimenError(f"{specimen.id}: ranked specimens need ranked profiles")
            result = resolve_profile(specimen.method, profile, profile_ballots(profile))  # type: ignore[arg-type]
        if not is_decisive(result):
            raise SpecimenError(f"{specimen.id}: the {sp.role} profile needs a tiebreak")
        if result.winners != [sp.winner]:
            raise SpecimenError(
                f"{specimen.id}: the {sp.role} profile elects {result.winners}, "
                f"not {sp.winner}"
            )
    _check_transformation(specimen)
    if not violates(specimen):
        raise SpecimenError(f"{specimen.id}: no violation of {specimen.criterion}")
    expected_voters = max(sp.profile.total_voters for sp in specimen.profiles)
    if specimen.voters != expected_voters:
        raise SpecimenError(f"{specimen.id}: records {specimen.voters} voters")


def violates(specimen: Specimen) -> bool:
    """Whether the recorded winners violate the specimen's criterion."""
    criterion = specimen.criterion
    t = specimen.transformation

    if criterion in ("majority", "condorcet_winner", "condorcet_loser"):
        single = specimen.profile("profile")
        focus = criterion_focus(criterion, single.profile)
        if focus is None or focus != specimen.focus:
            return False
        if criterion == "condorcet_loser":
            return single.winner == focus
        return single.winner != focus

    if criterion == "consistency":
        first = specimen.profile("first").winner
        return first == specimen.profile("second").winner != specimen.profile("combined").winner

    before = specimen.profile("before").winner
    after = specimen.profile("after").winner
    if criterion == "monotonicity" and isinstance(t, (Raise, RaiseUtility)):
        return before == t.candidate and after != before
    if criterion == "participation" and isinstance(t, AddVoters):
        # The newcomers prefer the old winner to the new one
        return after != before and t.ranking.index(before) < t.ranking.index(after)
    if criterion == "participation" and isinstance(t, AddUtilityVoters):
        candidates = specimen.profile("before").profile.candidates
        ranking = SINCERE_V1.cast(candidates, t.utilities).ranking
        return after != before and ranking.index(before) < ranking.index(after)
    if criterion == "iia" and isinstance(t, RemoveCandidate):
        return t.candidate != before and after != before
    if criterion == "clones" and isinstance(t, AddClone):
        if before == t.candidate:
            return after not in (t.candidate, t.clone)
        return after != before
    return False


def criterion_focus(criterion: Criterion, profile: Profile) -> CandidateId | None:
    """The candidate a single-profile criterion singles out, on sincere rankings."""
    rankings = profile if isinstance(profile, RankedProfile) else rankings_of(profile, SINCERE_V1)
    if criterion == "majority":
        return majority_winner(rankings)
    if criterion == "condorcet_winner":
        return condorcet_winner(rankings)
    return condorcet_loser(rankings)


def _check_transformation(specimen: Specimen) -> None:
    t = specimen.transformation
    criterion = specimen.criterion
    if criterion in ("majority", "condorcet_winner", "condorcet_loser"):
        if t is not None:
            raise SpecimenError(f"{specimen.id}: single-profile specimens have no transformation")
        return
    if specimen.method in RATED_METHODS:
        _check_utility_transformation(specimen)
        return

    expected: RankedProfile
    if criterion == "consistency":
        expected = combine(_ranked(specimen, "first"), _ranked(specimen, "second"))
        actual = _ranked(specimen, "combined")
    else:
        before = _ranked(specimen, "before")
        actual = _ranked(specimen, "after")
        if isinstance(t, Raise):
            expected = raise_candidate(before, t.ranking, t.candidate, t.position, t.voters)
        elif isinstance(t, AddVoters):
            newcomers = create_ranked_profile(before.candidates, [(t.voters, t.ranking)])
            expected = combine(before, newcomers)
        elif isinstance(t, RemoveCandidate):
            expected = remove_candidate(before, t.candidate)
        elif isinstance(t, AddClone):
            if not are_clones(actual, t.candidate, t.clone):
                raise SpecimenError(f"{specimen.id}: {t.clone} is not a clone of {t.candidate}")
            expected = before
            actual = remove_candidate(actual, t.clone)
        else:
            raise SpecimenError(f"{specimen.id}: missing transformation")
    if expected != actual:
        raise SpecimenError(f"{specimen.id}: the transformation does not produce the next profile")


def _check_utility_transformation(specimen: Specimen) -> None:
    t = specimen.transformation
    if specimen.criterion == "consistency":
        expected = ut.combine(_utility(specimen, "first"), _utility(specimen, "second"))
        actual = _utility(specimen, "combined")
    else:
        before = _utility(specimen, "before")
        actual = _utility(specimen, "after")
        if isinstance(t, RaiseUtility):
            index = before.candidates.index(t.candidate)
            if not ut.is_raise(t.before, t.after, index):
                raise SpecimenError(f"{specimen.id}: the move does not raise {t.candidate}")
            expected = ut.move_voters(before, t.before, t.after, t.voters)
        elif isinstance(t, AddUtilityVoters):
            expected = ut.add_voters(before, t.utilities, t.voters)
        elif isinstance(t, RemoveCandidate):
            expected = ut.remove_candidate(before, t.candidate)
        elif isinstance(t, AddClone):
            expected = ut.add_clone(before, t.candidate, t.clone)
        else:
            raise SpecimenError(f"{specimen.id}: missing transformation")
    if expected.candidates != actual.candidates or ut.utility_counts(expected) != ut.utility_counts(actual):
        raise SpecimenError(f"{specimen.id}: the transformation does not produce the next profile")


def _ranked(specimen: Specimen, role: Role) -> RankedProfile:
    profile = specimen.profile(role).profile
    if not isinstance(profile, RankedProfile):
        raise SpecimenError(f"{specimen.id}: expected a ranked profile")
    return profile


def _utility(specimen: Specimen, role: Role) -> UtilityProfile:
    profile = specimen.profile(role).profile
    if not isinstance(profile, UtilityProfile):
        raise SpecimenError(f"{specimen.id}: expected a utility profile")
    return profile


# --- JSON ---------------------------------------------------------------

JsonObject = dict[str, object]


def specimen_to_json(specimen: Specimen) -> JsonObject:
    """A plain-JSON record of a specimen."""
    return {
        "id": specimen.id,
        "method": specimen.method,
        "criterion": specimen.criterion,
        "ballot_model": specimen.ballot_model,
        "voters": specimen.voters,
        "focus": specimen.focus,
        "transformation": _transformation_to_json(specimen.transformation),
        "profiles": [_profile_to_json(sp) for sp in specimen.profiles],
    }


def _profile_to_json(sp: SpecimenProfile) -> JsonObject:
    profile = sp.profile
    if isinstance(profile, UtilityProfile):
        rows: list[list[object]] = [[count, list(utilities)] for count, utilities in profile.rows]
        ballot_type = "utility"
    else:
        rows = [[count, list(ranking)] for count, ranking in profile.rows]
        ballot_type = "ranked"
    return {
        "role": sp.role,
        "ballot_type": ballot_type,
        "candidates": list(profile.candidates),
        "rows": rows,
        "winner": sp.winner,
    }


def specimen_from_json(data: JsonObject) -> Specimen:
    """Rebuild a specimen from specimen_to_json output."""
    method = cast(str, data["method"])
    criterion = cast(str, data["criterion"])
    if (method not in RANKED_METHODS and method not in RATED_METHODS) or criterion not in CRITERIA:
        raise SpecimenError(f"Unknown method or criterion: {method}, {criterion}")
    profiles = tuple(
        SpecimenProfile(
            role=cast(Role, sp["role"]),
            profile=_profile_from_json(sp),
            winner=cast(CandidateId, sp["winner"]),
        )
        for sp in cast(list[dict[str, object]], data["profiles"])
    )
    return Specimen(
        method=method,
        criterion=criterion,
        profiles=profiles,
        transformation=_transformation_from_json(
            cast(dict[str, object] | None, data["transformation"])
        ),
        focus=cast(CandidateId | None, data["focus"]),
        voters=cast(int, data["voters"]),
    )


def _profile_from_json(sp: dict[str, object]) -> Profile:
    candidates = cast(list[CandidateId], sp["candidates"])
    if sp.get("ballot_type") == "utility":
        rows = cast(list[tuple[int, list[int]]], sp["rows"])
        return create_utility_profile(
            candidates, [(count, dict(zip(candidates, utilities))) for count, utilities in rows]
        )
    return create_ranked_profile(candidates, cast(list[tuple[int, list[CandidateId]]], sp["rows"]))


def _transformation_to_json(t: Transformation | None) -> JsonObject | None:
    if t is None:
        return None
    if isinstance(t, Raise):
        return {"kind": t.kind, "candidate": t.candidate, "ranking": list(t.ranking),
                "position": t.position, "voters": t.voters}
    if isinstance(t, RaiseUtility):
        return {"kind": t.kind, "candidate": t.candidate, "before": list(t.before),
                "after": list(t.after), "voters": t.voters}
    if isinstance(t, AddVoters):
        return {"kind": t.kind, "ranking": list(t.ranking), "voters": t.voters}
    if isinstance(t, AddUtilityVoters):
        return {"kind": t.kind, "utilities": list(t.utilities), "voters": t.voters}
    if isinstance(t, RemoveCandidate):
        return {"kind": t.kind, "candidate": t.candidate}
    if isinstance(t, AddClone):
        return {"kind": t.kind, "candidate": t.candidate, "clone": t.clone}
    return {"kind": t.kind}


def _transformation_from_json(data: dict[str, object] | None) -> Transformation | None:
    if data is None:
        return None
    kind = data["kind"]
    if kind == "raise":
        return Raise(
            candidate=cast(CandidateId, data["candidate"]),
            ranking=tuple(cast(list[CandidateId], data["ranking"])),
            position=cast(int, data["position"]),
            voters=cast(int, data["voters"]),
        )
    if kind == "raise_utility":
        return RaiseUtility(
            candidate=cast(CandidateId, data["candidate"]),
            before=tuple(cast(list[int], data["before"])),
            after=tuple(cast(list[int], data["after"])),
            voters=cast(int, data["voters"]),
        )
    if kind == "add_voters":
        return AddVoters(
            ranking=tuple(cast(list[CandidateId], data["ranking"])),
            voters=cast(int, data["voters"]),
        )
    if kind == "add_utility_voters":
        return AddUtilityVoters(
            utilities=tuple(cast(list[int], data["utilities"])),
            voters=cast(int, data["voters"]),
        )
    if kind == "combine":
        return Combine()
    if kind == "remove_candidate":
        return RemoveCandidate(candidate=cast(CandidateId, data["candidate"]))
    if kind == "add_clone":
        return AddClone(
            candidate=cast(CandidateId, data["candidate"]),
            clone=cast(CandidateId, data["clone"]),
        )
    raise SpecimenError(f"Unknown transformation kind: {kind}")
