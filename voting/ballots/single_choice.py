"""
Single-choice ballot: voter selects zero or one candidate.

Used by: Plurality (FPTP)

A None choice represents an abstention - the voter participated
but chose not to select any candidate.
"""

from dataclasses import dataclass

from ..types import Ballot, CandidateId, VoterId


@dataclass
class SingleChoiceBallot(Ballot):
    """A ballot where the voter selects exactly one candidate or abstains."""
    # The selected candidate, or None for abstention
    choice: CandidateId | None


def create_single_choice_ballot(
    voter_id: VoterId,
    choice: CandidateId | None
) -> SingleChoiceBallot:
    """Create a single-choice ballot."""
    return SingleChoiceBallot(voter_id=voter_id, choice=choice)


def is_abstention(ballot: SingleChoiceBallot) -> bool:
    """Check if a ballot is an abstention."""
    return ballot.choice is None
