"""
Election processing: from a ballot paper to tallies.

Each question is processed on its own:

  1. Issue    Persons who live in the ballot paper's jurisdiction each
              originate exactly one vote on the question.
  2. Route    Whoever holds a vote applies their own routing rule.
  3. Resolve  Hops are followed until someone keeps the vote.
  4. Cast     Each resolver casts one ballot, which applies to every vote
              they hold on the question.
  5. Tally    Each voter's ballot is a copy of their resolver's ballot under
              the voter's own id, and the copies go to a voting/ method.

Eligibility decides where votes originate, not who resolves them: a person
outside the jurisdiction has no vote of their own but answers for whatever
was handed to them.

Copying a resolver's ballot is equivalent to weighting it for any anonymous
method, so voting/ is used unchanged and every ballot type works. A resolver
who casts nothing turns every vote they hold into an abstention.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Mapping, Set
from dataclasses import dataclass, replace
from typing import Generic, TypeVar

from voting.types import Ballot, Candidate

from .graph import QuestionResolution, resolve_question
from .routing import DEFAULT_THRESHOLD
from .types import (
    BallotPaper,
    Judgments,
    JurisdictionId,
    Network,
    PersonId,
    Question,
    QuestionId,
)

B = TypeVar("B", bound=Ballot)
R = TypeVar("R")


def eligible_voters(
    network: Network, jurisdiction: JurisdictionId
) -> tuple[PersonId, ...]:
    """The persons who live in a jurisdiction, in sorted order."""
    return tuple(
        sorted(
            person.id
            for person in network.persons.values()
            if jurisdiction in person.residences
        )
    )


def resolve_ballot_paper(
    network: Network,
    paper: BallotPaper,
    judgments: Judgments,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    direct_voters: Mapping[QuestionId, Set[PersonId]] | None = None,
) -> dict[QuestionId, QuestionResolution]:
    """
    Resolve every question on a ballot paper.

    One voter's questions can end with different resolvers, because each
    question is routed separately.

    Args:
        network: The delegation network
        paper: The ballot paper
        judgments: Probabilities per (question, category)
        threshold: The routing threshold
        direct_voters: Per question, the persons who cast their own vote

    Returns:
        One resolution per question, in ballot paper order.
    """
    voters = eligible_voters(network, paper.jurisdiction)
    direct = direct_voters or {}
    return {
        question.id: resolve_question(
            network,
            question.id,
            voters,
            judgments,
            threshold=threshold,
            direct_voters=direct.get(question.id, frozenset()),
        )
        for question in paper.questions
    }


def _copy_for(ballot: B, voter: PersonId) -> B:
    """An independent copy of a ballot, cast under another voter's id."""
    return replace(copy.deepcopy(ballot), voter_id=voter)


def delegated_ballots(
    resolution: QuestionResolution,
    cast: Mapping[PersonId, B],
    abstention: Callable[[PersonId], B],
) -> list[B]:
    """
    One ballot per voter: a copy of their resolver's ballot.

    Args:
        resolution: The question's resolution
        cast: The ballot each person cast on the question. Only resolvers'
            ballots are read.
        abstention: Builds an abstention ballot for a voter, used when their
            resolver cast nothing

    Returns:
        Ballots in sorted voter order, each under its voter's own id.
    """
    ballots: list[B] = []
    for voter, trace in resolution.traces.items():
        source = cast.get(trace.resolver)
        ballots.append(
            abstention(voter) if source is None else _copy_for(source, voter)
        )
    return ballots


def direct_ballots(
    voters: Iterable[PersonId],
    cast: Mapping[PersonId, B],
    abstention: Callable[[PersonId], B],
) -> list[B]:
    """
    The direct-voting baseline: every voter's own ballot.

    Args:
        voters: The persons who originate a vote
        cast: The ballot each person would cast themself
        abstention: Builds an abstention ballot for a voter with no ballot

    Returns:
        Ballots in sorted voter order.
    """
    ballots: list[B] = []
    for voter in sorted(set(voters)):
        own = cast.get(voter)
        ballots.append(abstention(voter) if own is None else _copy_for(own, voter))
    return ballots


@dataclass(frozen=True)
class QuestionTally(Generic[B, R]):
    """The ballots a question was tallied from, and the method's result."""

    question: QuestionId
    # One ballot per voter, in sorted voter order
    ballots: tuple[B, ...]
    result: R


def tally_question(
    question: Question,
    resolution: QuestionResolution,
    cast: Mapping[PersonId, B],
    *,
    abstention: Callable[[PersonId], B],
    method: Callable[[list[Candidate], list[B]], R],
) -> QuestionTally[B, R]:
    """
    Tally one question under delegation.

    Args:
        question: The question and its options
        resolution: The question's resolution
        cast: The ballot each resolver cast on the question
        abstention: Builds an abstention ballot for a voter
        method: A voting/ resolution method taking (candidates, ballots).
            Give it a fresh seeded tiebreak per question, for example
            `lambda c, b: resolve_plurality(c, b, random_tiebreak(seed))`.
            A tiebreak object carries its own random stream, so one shared
            between tallies makes each result depend on the ones before it.

    Raises:
        ValueError: If the resolution is for a different question
    """
    if resolution.question != question.id:
        raise ValueError(
            f"Resolution is for question {resolution.question!r}, "
            f"not {question.id!r}"
        )
    ballots = delegated_ballots(resolution, cast, abstention)
    result = method(list(question.options), ballots)
    return QuestionTally(question=question.id, ballots=tuple(ballots), result=result)
