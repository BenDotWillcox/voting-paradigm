"""
Delegation domain package (demo 5: liquid democracy).

A voter hands a category of decisions to another person. When a ballot paper
arrives, each question is routed per voter: to the delegate for the voter's
best-matching category, or kept. Delegation is transitive, and every vote
ends at exactly one resolver.

This package is the pure core: the routing rule, the loop checks, per-question
resolution, election processing through voting/, and metrics. It reads
judgments (probabilities per question and category) but does not produce
them. Design: prompts/demo-5-liquid-democracy.md.

Boundary rules (per CLAUDE.md):
  - Pure Python; no DB writes, no HTTP, no I/O at import time.
  - May import from the foundational primitive voting/.
    Does NOT import from preferences/, districting/, or other demo packages.
"""

from .election import (
    QuestionTally,
    delegated_ballots,
    direct_ballots,
    eligible_voters,
    resolve_ballot_paper,
    tally_question,
)
from .graph import (
    DelegationLoopError,
    KeepReason,
    QuestionResolution,
    VoteTrace,
    add_delegation,
    closing_chain,
    loop_warnings,
    remove_delegation,
    resolve_question,
)
from .metrics import (
    chain_length_counts,
    delegated_share,
    largest_share,
    weight_gini,
    winners_differ,
)
from .routing import (
    DEFAULT_THRESHOLD,
    CategoryScore,
    RouteOutcome,
    RoutingDecision,
    route,
)
from .types import (
    MAX_CATEGORY_LENGTH,
    BallotPaper,
    Category,
    CategoryId,
    Delegation,
    InvalidBallotPaperError,
    InvalidCategoryError,
    InvalidJudgmentError,
    InvalidNetworkError,
    Judgments,
    JurisdictionId,
    Network,
    Person,
    PersonId,
    Question,
    QuestionId,
    create_ballot_paper,
    create_category,
    create_network,
    normalize_category_text,
)

__all__ = [
    # Types
    "PersonId",
    "CategoryId",
    "QuestionId",
    "JurisdictionId",
    "Judgments",
    "Person",
    "Category",
    "Delegation",
    "Network",
    "Question",
    "BallotPaper",
    "MAX_CATEGORY_LENGTH",
    "create_category",
    "create_network",
    "create_ballot_paper",
    "normalize_category_text",
    "InvalidCategoryError",
    "InvalidNetworkError",
    "InvalidBallotPaperError",
    "InvalidJudgmentError",
    # Routing rule
    "DEFAULT_THRESHOLD",
    "RouteOutcome",
    "CategoryScore",
    "RoutingDecision",
    "route",
    # Loop checks when a delegation is created
    "DelegationLoopError",
    "closing_chain",
    "add_delegation",
    "remove_delegation",
    "loop_warnings",
    # Resolving a question
    "KeepReason",
    "VoteTrace",
    "QuestionResolution",
    "resolve_question",
    # Election processing
    "eligible_voters",
    "resolve_ballot_paper",
    "delegated_ballots",
    "direct_ballots",
    "QuestionTally",
    "tally_question",
    # Metrics
    "delegated_share",
    "largest_share",
    "weight_gini",
    "chain_length_counts",
    "winners_differ",
]
