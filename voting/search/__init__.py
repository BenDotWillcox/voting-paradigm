"""
Paradox search: the smallest profiles on which a method fails a criterion.

The search proposes; the reference methods certify. Every outcome comes from
voting.methods, and certify() re-resolves each specimen from fresh ballots.
"""

from .enumeration import profile_count, profiles, rankings
from .outcomes import (
    RANKED_METHODS,
    RATED_METHODS,
    Outcome,
    RankedMethod,
    RatedMethod,
    SearchMethod,
    is_decisive,
    outcome,
    resolve_profile,
    resolve_rated,
)
from .paradoxes import DEFAULT_CANDIDATES, SearchResult, find_disagreement_cycle, search
from .specimens import (
    CRITERIA,
    AddClone,
    AddUtilityVoters,
    AddVoters,
    Combine,
    Criterion,
    Raise,
    RaiseUtility,
    RemoveCandidate,
    Specimen,
    SpecimenError,
    SpecimenProfile,
    Transformation,
    certify,
    criterion_focus,
    specimen_from_json,
    specimen_to_json,
    violates,
)

__all__ = [
    "profile_count",
    "profiles",
    "rankings",
    "RANKED_METHODS",
    "RATED_METHODS",
    "Outcome",
    "RankedMethod",
    "RatedMethod",
    "SearchMethod",
    "resolve_rated",
    "is_decisive",
    "outcome",
    "resolve_profile",
    "DEFAULT_CANDIDATES",
    "SearchResult",
    "find_disagreement_cycle",
    "search",
    "CRITERIA",
    "AddClone",
    "AddUtilityVoters",
    "AddVoters",
    "Combine",
    "Criterion",
    "Raise",
    "RaiseUtility",
    "RemoveCandidate",
    "Specimen",
    "SpecimenError",
    "SpecimenProfile",
    "Transformation",
    "certify",
    "criterion_focus",
    "specimen_from_json",
    "specimen_to_json",
    "violates",
]
