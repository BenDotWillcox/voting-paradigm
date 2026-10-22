"""
Electoral criteria as checks on profiles.

Criteria judge methods; they never resolve elections themselves.
"""

from .single_profile import (
    condorcet_loser,
    condorcet_winner,
    majority_winner,
    pairwise_counts,
)
from .transformations import (
    add_voters,
    are_clones,
    combine,
    raise_candidate,
    remove_candidate,
)

__all__ = [
    "condorcet_loser",
    "condorcet_winner",
    "majority_winner",
    "pairwise_counts",
    "add_voters",
    "are_clones",
    "combine",
    "raise_candidate",
    "remove_candidate",
]
