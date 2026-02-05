"""
Approval ballot: voter approves zero or more candidates.

Used by: Approval Tally

Voters can approve any number of candidates, from none (abstention)
to all candidates. There is no ranking — all approved candidates
are treated equally.
"""

from dataclasses import dataclass, field

from ..types import Ballot, CandidateId, VoterId


@dataclass
class ApprovalBallot(Ballot):
    """A ballot where the voter approves any number of candidates."""
    # Set of approved candidate IDs (empty set = abstention)
    approvals: set[CandidateId] = field(default_factory=set)


def create_approval_ballot(
    voter_id: VoterId,
    approvals: set[CandidateId] | list[CandidateId] | None = None
) -> ApprovalBallot:
    """
    Create an approval ballot.

    Args:
        voter_id: The voter's identifier
        approvals: Candidates to approve (set, list, or None for abstention)
    """
    if approvals is None:
        approval_set = set()
    elif isinstance(approvals, list):
        approval_set = set(approvals)
    else:
        approval_set = approvals

    return ApprovalBallot(voter_id=voter_id, approvals=approval_set)


def is_abstention(ballot: ApprovalBallot) -> bool:
    """Check if a ballot is an abstention (no approvals)."""
    return len(ballot.approvals) == 0


def approval_count(ballot: ApprovalBallot) -> int:
    """Return the number of candidates approved on this ballot."""
    return len(ballot.approvals)
