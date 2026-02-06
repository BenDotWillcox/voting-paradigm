"""
Core types for the voting mechanisms package.
"""

import random
from dataclasses import dataclass
from typing import Callable

# Type aliases for clarity
CandidateId = str
VoterId = str

# Vote counts: maps candidate ID to their vote count
VoteCounts = dict[CandidateId, int]


@dataclass
class Candidate:
    """A candidate or option that can be voted for."""
    id: CandidateId
    name: str


@dataclass
class Ballot:
    """Base class for all ballot types."""
    voter_id: VoterId


@dataclass
class ElectionResult:
    """Result of an election."""
    # The winning candidate(s). Multiple only if method allows co-winners.
    winners: list[CandidateId]
    # Vote counts for all candidates
    vote_counts: VoteCounts
    # Total number of ballots cast
    total_ballots: int
    # Number of ballots with no vote (abstentions)
    abstentions: int
    # Whether a tiebreaker was used to determine the winner
    tiebreak_applied: bool


# Function signature for resolving ties
TiebreakFunction = Callable[[list[CandidateId]], CandidateId]


def random_tiebreak(tied: list[CandidateId]) -> CandidateId:
    """Default random tiebreaker - selects uniformly at random."""
    return random.choice(tied)
