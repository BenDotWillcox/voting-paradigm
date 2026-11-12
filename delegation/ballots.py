"""
Ballot shapes a question can use, and the method that counts each.

Delegation does not care what a ballot looks like: a voter's ballot is a
copy of their resolver's, whatever its shape, and voting/ counts the copies.
This module is the small table that says, for each shape the demo uses, how
to build a ballot from a choice, how to read one back, how a person's
utilities become a sincere ballot, and which voting/ method counts them.

  single_choice   one option, counted by plurality (a yes/no measure)
  ranked          every option in order, counted by instant-runoff voting
  approval        any number of options, counted by approval voting

A choice travels as a list of option ids: one id for a single choice, the
full order for a ranking, the approved options for an approval ballot.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, cast, get_args

from voting import (
    ApprovalBallot,
    RankedChoiceBallot,
    SingleChoiceBallot,
    create_approval_ballot,
    create_ranked_choice_ballot,
    create_single_choice_ballot,
    resolve_approval,
    resolve_irv,
    resolve_plurality,
)
from voting.types import Ballot, Candidate, CandidateId, ElectionResult, TiebreakFunction

from .types import PersonId, Question

BallotType = Literal["single_choice", "ranked", "approval"]
BALLOT_TYPES: tuple[BallotType, ...] = get_args(BallotType)

# The voting/ method each ballot type is counted with
METHODS: Mapping[BallotType, str] = {
    "single_choice": "plurality",
    "ranked": "irv",
    "approval": "approval",
}


class InvalidChoiceError(ValueError):
    """Raised when a choice does not fit the question's options or ballot type."""


def ballot_for(
    ballot_type: BallotType,
    voter: PersonId,
    choice: Sequence[CandidateId] | None,
    question: Question,
) -> Ballot:
    """
    Build a voter's ballot from a choice; no choice is an abstention.

    Raises:
        InvalidChoiceError: If the choice names an unknown option or repeats
            one, a single choice is not exactly one option, a ranking leaves
            an option out, or an approval ballot approves nothing
    """
    if choice is None:
        if ballot_type == "single_choice":
            return create_single_choice_ballot(voter, None)
        if ballot_type == "ranked":
            return create_ranked_choice_ballot(voter, None)
        return create_approval_ballot(voter, None)

    options = [option.id for option in question.options]
    picked = list(choice)
    unknown = [option for option in picked if option not in options]
    if unknown:
        raise InvalidChoiceError(
            f"{unknown[0]!r} is not an option on question {question.id!r}"
        )
    if len(set(picked)) != len(picked):
        raise InvalidChoiceError(f"An option repeats on question {question.id!r}")

    if ballot_type == "single_choice":
        if len(picked) != 1:
            raise InvalidChoiceError(
                f"Question {question.id!r} takes exactly one option"
            )
        return create_single_choice_ballot(voter, picked[0])
    if ballot_type == "ranked":
        if len(picked) != len(options):
            raise InvalidChoiceError(
                f"Question {question.id!r} needs every option ranked"
            )
        return create_ranked_choice_ballot(voter, picked, options)
    if not picked:
        raise InvalidChoiceError(
            f"Question {question.id!r} needs at least one option approved"
        )
    return create_approval_ballot(voter, picked)


def choice_on(ballot: Ballot, question: Question) -> list[CandidateId] | None:
    """
    The choice a ballot carries, as a list of option ids; None for an
    abstention. Approved options come back in the question's option order.
    """
    if isinstance(ballot, SingleChoiceBallot):
        return None if ballot.choice is None else [ballot.choice]
    if isinstance(ballot, RankedChoiceBallot):
        return list(ballot.ranking) or None
    if isinstance(ballot, ApprovalBallot):
        approved = [o.id for o in question.options if o.id in ballot.approvals]
        return approved or None
    raise TypeError(f"Unsupported ballot {type(ballot).__name__}")


def sincere_choice_for(
    ballot_type: BallotType,
    utilities: Mapping[CandidateId, float],
    question: Question,
) -> list[CandidateId]:
    """
    The choice someone with these utilities would sincerely make.

    A single choice is the favourite. A ranking is every option from most to
    least wanted. An approval ballot approves every option wanted more than
    the average option, which always includes the favourite. Ties go to the
    earlier option.
    """
    order = sorted(
        range(len(question.options)),
        key=lambda index: (-utilities[question.options[index].id], index),
    )
    ranked = [question.options[index].id for index in order]
    if ballot_type == "single_choice":
        return ranked[:1]
    if ballot_type == "ranked":
        return ranked
    average = sum(utilities[option.id] for option in question.options) / len(
        question.options
    )
    approved = {option for option in ranked if utilities[option] > average}
    approved.add(ranked[0])
    return [option.id for option in question.options if option.id in approved]


def count(
    ballot_type: BallotType,
    candidates: Sequence[Candidate],
    ballots: Sequence[Ballot],
    tiebreak: TiebreakFunction,
) -> ElectionResult:
    """Count ballots of one type with that type's voting/ method."""
    options = list(candidates)
    if ballot_type == "single_choice":
        return resolve_plurality(
            options, cast(list[SingleChoiceBallot], list(ballots)), tiebreak
        )
    if ballot_type == "ranked":
        return resolve_irv(
            options, cast(list[RankedChoiceBallot], list(ballots)), tiebreak
        )
    return resolve_approval(
        options, cast(list[ApprovalBallot], list(ballots)), tiebreak
    )
