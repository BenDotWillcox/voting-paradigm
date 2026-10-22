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

# Seed used when a method is called without an explicit tiebreak
DEFAULT_TIEBREAK_SEED = 0


def random_tiebreak(seed: int = DEFAULT_TIEBREAK_SEED) -> TiebreakFunction:
    """
    Build a seeded tiebreaker that selects uniformly at random.

    Each call returns a tiebreaker with its own random stream, so the same
    seed always breaks the same sequence of ties the same way. Methods build
    a fresh one per resolution when no tiebreak is passed, which makes every
    default resolution reproducible. Simulations that need independent
    tiebreaks across elections pass a distinct seed per election.

    Tied candidates are sorted before the draw, so the choice never depends
    on the order the caller listed them in.
    """
    rng = random.Random(seed)

    def tiebreak(tied: list[CandidateId]) -> CandidateId:
        return rng.choice(sorted(tied))

    return tiebreak
