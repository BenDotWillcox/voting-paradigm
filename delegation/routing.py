"""
The per-voter routing rule: which delegate, if any, gets one question.

The decision model makes the judgments; this module makes the decision:

  1. Every category the person has delegated is scored.
  2. Categories below the threshold drop out. If none are left, the person
     keeps the decision.
  3. A category gives way when a narrower category inside it is also still
     in. Specific overrules general.
  4. Of what remains, the highest score wins.

The rule never guesses. A person with a direct vote keeps the decision, and
so does a person for whom any judgment is missing.

Step 3 exists because scores alone do not prefer the narrow category. A
yes/no score measures whether a statement is true, and "this is about the
environment" is true of every question about tree frogs. In the router
evaluation the broad category took 10 of 28 questions that sat squarely
inside a narrow one, so a voter's carve-out lost to its own parent a third
of the time (eval/benchmarks/delegation_router_v1/). Which categories sit
inside which comes from the network's nesting; with none recorded, step 3
does nothing and the rule is plain highest-score-wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .types import (
    CategoryId,
    InvalidNetworkError,
    Judgments,
    Network,
    PersonId,
    QuestionId,
    validate_probability,
)

# TypeSafe's suggested starting point for a yes; tuned in the router evaluation.
DEFAULT_THRESHOLD = 0.7


class RouteOutcome(Enum):
    """What the routing rule decided, and why."""

    # The person cast their own vote on this question
    DIRECT_VOTE = "direct_vote"
    # The person has delegated no categories
    NO_DELEGATIONS = "no_delegations"
    # A judgment the rule needed is missing, so it did not run
    ROUTER_UNAVAILABLE = "router_unavailable"
    # No delegated category cleared the threshold
    NONE_AVAILABLE = "none_available"
    # The decision goes to the delegate for the winning category
    DELEGATED = "delegated"


@dataclass(frozen=True)
class CategoryScore:
    """One category's judgment for a question."""

    category: CategoryId
    probability: float


@dataclass(frozen=True)
class RoutingDecision:
    """The routing rule's answer for one person on one question."""

    person: PersonId
    question: QuestionId
    outcome: RouteOutcome
    threshold: float
    # The judgments that were available, in the person's category list
    # order. Empty when the person cast a direct vote or has no delegations.
    scores: tuple[CategoryScore, ...] = ()
    # The winning category and its delegate; set only when delegated
    category: CategoryId | None = None
    delegate: PersonId | None = None
    # Categories that cleared the threshold but gave way to a narrower
    # category inside them, in the person's category list order
    set_aside: tuple[CategoryId, ...] = ()

    @property
    def kept(self) -> bool:
        """Whether the decision stays with this person."""
        return self.outcome is not RouteOutcome.DELEGATED


def route(
    network: Network,
    person: PersonId,
    question: QuestionId,
    judgments: Judgments,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    direct_vote: bool = False,
) -> RoutingDecision:
    """
    Decide where one person's hold on one question goes.

    Args:
        network: The delegation network
        person: The person currently holding the decision
        question: The question being routed
        judgments: Probabilities per (question, category)
        threshold: The floor the winning category must reach (inclusive)
        direct_vote: Whether the person cast their own vote on the question

    Returns:
        The routing decision. A category that clears the threshold gives
        way to any narrower category inside it that also clears. Exact
        score ties among the rest go to the category that comes first in
        the person's category list.

    Raises:
        InvalidNetworkError: If the person is not in the network
        InvalidJudgmentError: If the threshold or a judgment is not a
            probability
    """
    if person not in network.persons:
        raise InvalidNetworkError(f"Unknown person {person!r}")
    validate_probability(threshold, "Threshold")

    if direct_vote:
        return RoutingDecision(person, question, RouteOutcome.DIRECT_VOTE, threshold)

    delegations = network.delegations_of(person)
    if not delegations:
        return RoutingDecision(person, question, RouteOutcome.NO_DELEGATIONS, threshold)

    scores: list[CategoryScore] = []
    for delegation in delegations:
        probability = judgments.get((question, delegation.category))
        if probability is None:
            continue
        validate_probability(
            probability, f"Judgment for {(question, delegation.category)!r}"
        )
        scores.append(CategoryScore(delegation.category, probability))

    if len(scores) < len(delegations):
        return RoutingDecision(
            person,
            question,
            RouteOutcome.ROUTER_UNAVAILABLE,
            threshold,
            scores=tuple(scores),
        )

    cleared = [score for score in scores if score.probability >= threshold]
    if not cleared:
        return RoutingDecision(
            person,
            question,
            RouteOutcome.NONE_AVAILABLE,
            threshold,
            scores=tuple(scores),
        )

    # Specific overrules general: a category gives way when a narrower
    # category inside it also cleared. Nesting cannot loop, so the narrowest
    # categories always remain.
    set_aside = tuple(
        score.category
        for score in cleared
        if any(network.is_inside(other.category, score.category) for other in cleared)
    )
    remaining = [score for score in cleared if score.category not in set_aside]

    # Strict comparison, so the first category in the list wins an exact tie.
    best = remaining[0]
    for score in remaining[1:]:
        if score.probability > best.probability:
            best = score

    return RoutingDecision(
        person,
        question,
        RouteOutcome.DELEGATED,
        threshold,
        scores=tuple(scores),
        category=best.category,
        delegate=network.delegate_for(person, best.category),
        set_aside=set_aside,
    )
