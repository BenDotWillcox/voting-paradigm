"""
Delegation loops: the checks when a delegation is created, and the rule
when a question is resolved.

Routing is per voter and categories are voter-written, so whether two
delegations are both active depends on the question. Loops are therefore
handled in two layers:

  1. When a delegation is created, it is rejected if it would close a loop
     through delegations of the identical category (add_delegation). A loop
     that depends on the question can only be warned about, by trying the
     delegation against reference questions (loop_warnings).

  2. When a question is resolved, everyone on a loop keeps the decision
     (resolve_question). All loop members are treated identically and no
     tiebreak is needed. Voters upstream of the loop still reach the loop
     member their chain leads to, and that member resolves for them.

For one question each person has at most one next hop, so every vote ends
at exactly one resolver.

Alternatives not taken: dropping votes that reach a loop (LiquidFeedback;
Brill et al. treat such voters as isolated) silently discards upstream
delegators, and voiding a single delegation in the loop (MinSum-style rules)
needs a tiebreak that hands one member the whole loop's weight.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Set
from dataclasses import dataclass
from enum import Enum

from .routing import DEFAULT_THRESHOLD, RouteOutcome, RoutingDecision, route
from .types import (
    Category,
    CategoryId,
    Delegation,
    InvalidNetworkError,
    Judgments,
    Network,
    PersonId,
    QuestionId,
)

# ---------------------------------------------------------------------------
# Layer 1: checks when a delegation is created
# ---------------------------------------------------------------------------


class DelegationLoopError(InvalidNetworkError):
    """Raised when a new delegation would close an identical-category loop."""

    def __init__(self, chain: tuple[PersonId, ...], category: CategoryId) -> None:
        self.chain = chain
        self.category = category
        super().__init__(
            f"Delegating category {category!r} would close a loop: "
            + " -> ".join(chain)
        )


def closing_chain(
    network: Network,
    delegator: PersonId,
    category: CategoryId,
    delegate: PersonId,
) -> tuple[PersonId, ...] | None:
    """
    Find the loop a new delegation would close, if any.

    Follows delegations of the identical category from the proposed delegate.
    Each person has at most one delegate per category, so this is one walk.

    Returns:
        The chain from the delegator back to the delegator, or None when the
        walk ends without reaching them.
    """
    chain = [delegator]
    walked: set[PersonId] = set()
    current: PersonId | None = delegate
    while current is not None:
        if current == delegator:
            return tuple(chain) + (delegator,)
        if current in walked:
            # An existing loop that does not pass through the delegator.
            return None
        walked.add(current)
        chain.append(current)
        current = network.delegate_for(current, category)
    return None


def add_delegation(
    network: Network,
    delegator: PersonId,
    category: Category,
    delegate: PersonId,
) -> Network:
    """
    Return the network with one more delegation, appended to the delegator's
    category list.

    The category is registered if nobody has used it before.

    Raises:
        DelegationLoopError: If the delegation would close a loop through
            delegations of the identical category
        InvalidNetworkError: If a person is unknown, the delegator names
            themself, or they already delegate this category
    """
    for person in (delegator, delegate):
        if person not in network.persons:
            raise InvalidNetworkError(f"Unknown person {person!r}")
    if delegator == delegate:
        raise InvalidNetworkError(f"{delegator!r} cannot delegate to themself")
    if network.delegate_for(delegator, category.id) is not None:
        raise InvalidNetworkError(
            f"{delegator!r} already delegates category {category.id!r}"
        )

    chain = closing_chain(network, delegator, category.id, delegate)
    if chain is not None:
        raise DelegationLoopError(chain, category.id)

    categories = dict(network.categories)
    categories.setdefault(category.id, category)
    return Network(
        persons=network.persons,
        categories=categories,
        delegations=network.delegations
        + (Delegation(delegator, category.id, delegate),),
        nesting=network.nesting,
    )


def remove_delegation(
    network: Network, delegator: PersonId, category: CategoryId
) -> Network:
    """
    Return the network without the delegator's delegation of a category.

    Raises:
        InvalidNetworkError: If there is no such delegation
    """
    if network.delegate_for(delegator, category) is None:
        raise InvalidNetworkError(
            f"{delegator!r} does not delegate category {category!r}"
        )
    return Network(
        persons=network.persons,
        categories=network.categories,
        delegations=tuple(
            delegation
            for delegation in network.delegations
            if (delegation.delegator, delegation.category) != (delegator, category)
        ),
        nesting=network.nesting,
    )


# ---------------------------------------------------------------------------
# Layer 2: resolving one question
# ---------------------------------------------------------------------------


class KeepReason(Enum):
    """Why a resolver holds a decision and does not pass it on."""

    DIRECT_VOTE = "direct_vote"
    NO_DELEGATIONS = "no_delegations"
    ROUTER_UNAVAILABLE = "router_unavailable"
    NONE_AVAILABLE = "none_available"
    # The chain came back, so everyone on the loop keeps the decision
    LOOP = "loop"


_KEEP_REASONS: dict[RouteOutcome, KeepReason] = {
    RouteOutcome.DIRECT_VOTE: KeepReason.DIRECT_VOTE,
    RouteOutcome.NO_DELEGATIONS: KeepReason.NO_DELEGATIONS,
    RouteOutcome.ROUTER_UNAVAILABLE: KeepReason.ROUTER_UNAVAILABLE,
    RouteOutcome.NONE_AVAILABLE: KeepReason.NONE_AVAILABLE,
}


@dataclass(frozen=True)
class VoteTrace:
    """Where one voter's vote on one question ended up, and how."""

    voter: PersonId
    # From the voter to the resolver, both included
    chain: tuple[PersonId, ...]
    resolver: PersonId
    kept_because: KeepReason
    # The loop the resolver is on, when the chain reached one
    loop: tuple[PersonId, ...] | None = None

    @property
    def hops(self) -> int:
        """How many times the vote was passed on."""
        return len(self.chain) - 1

    @property
    def delegated(self) -> bool:
        """Whether someone other than the voter resolves this vote."""
        return self.resolver != self.voter


@dataclass(frozen=True)
class QuestionResolution:
    """Every voter's resolver for one question, with the audit trail."""

    question: QuestionId
    threshold: float
    # One trace per voter, keyed by voter id, in sorted order
    traces: Mapping[PersonId, VoteTrace]
    # The routing decision of every person the resolution consulted
    decisions: Mapping[PersonId, RoutingDecision]
    # Each loop found, once, starting from its smallest person id
    loops: tuple[tuple[PersonId, ...], ...]

    @property
    def voters(self) -> tuple[PersonId, ...]:
        """The voters whose votes were resolved, in sorted order."""
        return tuple(self.traces)

    def resolver_of(self, voter: PersonId) -> PersonId:
        """The person whose ballot is used for this voter."""
        return self.traces[voter].resolver

    def weights(self) -> dict[PersonId, int]:
        """How many voters each resolver answers for, keyed in sorted order."""
        counts = Counter(trace.resolver for trace in self.traces.values())
        return {person: counts[person] for person in sorted(counts)}


def _canonical_loop(members: list[PersonId]) -> tuple[PersonId, ...]:
    """Rotate a loop so it starts from its smallest id, keeping direction."""
    start = members.index(min(members))
    return tuple(members[start:] + members[:start])


def resolve_question(
    network: Network,
    question: QuestionId,
    voters: Iterable[PersonId],
    judgments: Judgments,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    direct_voters: Set[PersonId] = frozenset(),
) -> QuestionResolution:
    """
    Find the resolver of every voter's vote on one question.

    Each vote is passed along by the routing rule of whoever holds it until
    someone keeps it. If the chain comes back on itself, everyone on the
    loop keeps the decision and voters upstream resolve to the loop member
    their chain reaches.

    The result does not depend on the order the voters are given in.

    Args:
        network: The delegation network
        question: The question being resolved
        voters: The persons who originate a vote on this question
        judgments: Probabilities per (question, category)
        threshold: The routing threshold
        direct_voters: Persons who cast their own vote on this question.
            They keep the decision whatever they have delegated.

    Raises:
        InvalidNetworkError: If a voter is not in the network
        InvalidJudgmentError: If the threshold or a judgment is not a
            probability
    """
    voter_ids = sorted(set(voters))
    for voter in voter_ids:
        if voter not in network.persons:
            raise InvalidNetworkError(f"Unknown voter {voter!r}")

    decisions: dict[PersonId, RoutingDecision] = {}

    def next_hop(person: PersonId) -> PersonId | None:
        decision = decisions.get(person)
        if decision is None:
            decision = route(
                network,
                person,
                question,
                judgments,
                threshold=threshold,
                direct_vote=person in direct_voters,
            )
            decisions[person] = decision
        return decision.delegate

    resolver: dict[PersonId, PersonId] = {}
    loop_of: dict[PersonId, tuple[PersonId, ...]] = {}

    for start in voter_ids:
        path: list[PersonId] = []
        position: dict[PersonId, int] = {}
        current = start
        while True:
            if current in resolver:
                end = resolver[current]
                break
            if current in position:
                # The chain came back to `current`: everyone from there to
                # the end of the path is on the loop and keeps the decision.
                loop = _canonical_loop(path[position[current] :])
                for member in loop:
                    resolver[member] = member
                    loop_of[member] = loop
                del path[position[current] :]
                end = current
                break
            hop = next_hop(current)
            if hop is None:
                resolver[current] = current
                end = current
                break
            position[current] = len(path)
            path.append(current)
            current = hop
        for person in path:
            resolver[person] = end

    traces: dict[PersonId, VoteTrace] = {}
    for voter in voter_ids:
        end = resolver[voter]
        chain = [voter]
        while chain[-1] != end:
            hop = next_hop(chain[-1])
            if hop is None:
                raise AssertionError("A chain ended before reaching its resolver")
            chain.append(hop)
        loop_reached = loop_of.get(end)
        traces[voter] = VoteTrace(
            voter=voter,
            chain=tuple(chain),
            resolver=end,
            kept_because=(
                KeepReason.LOOP
                if loop_reached is not None
                else _KEEP_REASONS[decisions[end].outcome]
            ),
            loop=loop_reached,
        )

    return QuestionResolution(
        question=question,
        threshold=threshold,
        traces=traces,
        decisions={person: decisions[person] for person in sorted(decisions)},
        loops=tuple(sorted(set(loop_of.values()))),
    )


def loop_warnings(
    network: Network,
    delegator: PersonId,
    category: CategoryId,
    questions: Iterable[QuestionId],
    judgments: Judgments,
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[QuestionId, ...]:
    """
    Reference questions on which a delegation would come back to its author.

    Differently worded categories can both match the same question, which
    cannot be known from the text alone. This tries the delegator's
    delegation of `category` against reference questions and reports those
    where the vote is routed through that category and returns to the
    delegator. Such a delegation is allowed; on a real question the loop
    rule in resolve_question applies.

    Raises:
        InvalidNetworkError: If the delegator does not delegate the category
    """
    if network.delegate_for(delegator, category) is None:
        raise InvalidNetworkError(
            f"{delegator!r} does not delegate category {category!r}"
        )

    warned: list[QuestionId] = []
    for question in questions:
        resolution = resolve_question(
            network, question, [delegator], judgments, threshold=threshold
        )
        trace = resolution.traces[delegator]
        on_loop = trace.loop is not None and trace.resolver == delegator
        if on_loop and resolution.decisions[delegator].category == category:
            warned.append(question)
    return tuple(warned)
