"""
Core types for the delegation package (demo 5: liquid democracy).

Vocabulary (see prompts/demo-5-liquid-democracy.md):

  - A *person* is a member of the network. Residence decides which ballot
    papers they originate a vote on; anyone can be handed a vote to resolve.
  - A *category* is voter-written text describing the decisions a voter hands
    over. Two voters share a category only when the text is identical after
    normalising case and whitespace.
  - A *delegation* hands one category from one person to another.
  - A *ballot paper* is the list of questions put to one jurisdiction. It is
    not `voting.types.Ballot`, which is one voter's cast vote on one question.
  - A *judgment* is the decision model's probability that a question is
    primarily about a category. This package only reads judgments; producing
    them is a later build step.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from voting.types import Candidate, VoterId

# A person's id is the voter id that appears on the ballots cast for them.
PersonId = VoterId
CategoryId = str
QuestionId = str
JurisdictionId = str

# (question, category) -> probability that the question is primarily about
# the category. A missing key means the router has no judgment for that pair.
Judgments = Mapping[tuple[QuestionId, CategoryId], float]

# A category is one sentence, so it stays a description and not a prompt.
MAX_CATEGORY_LENGTH = 200


class InvalidCategoryError(ValueError):
    """Raised when category text is empty or too long."""


class InvalidNetworkError(ValueError):
    """Raised when persons, categories and delegations do not fit together."""


class InvalidBallotPaperError(ValueError):
    """Raised when a ballot paper's questions are invalid."""


class InvalidJudgmentError(ValueError):
    """Raised when a judgment is not a probability."""


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def normalize_category_text(text: str) -> str:
    """
    Reduce category text to the form that decides its identity.

    Whitespace is collapsed and case is folded, so "All things  taxes" and
    "all things taxes" are the same category. Nothing else is normalised:
    differently worded categories are different categories.

    Raises:
        InvalidCategoryError: If the text is empty or longer than
            MAX_CATEGORY_LENGTH characters once whitespace is collapsed
    """
    collapsed = _collapse_whitespace(text)
    if not collapsed:
        raise InvalidCategoryError("Category text is empty")
    if len(collapsed) > MAX_CATEGORY_LENGTH:
        raise InvalidCategoryError(
            f"Category text is {len(collapsed)} characters; "
            f"the limit is {MAX_CATEGORY_LENGTH}"
        )
    return collapsed.casefold()


@dataclass(frozen=True)
class Category:
    """
    A voter-written category.

    Build one with create_category, which derives the id from the text;
    constructing the dataclass directly skips that.
    """

    # Stable id derived from the normalised text
    id: CategoryId
    # The text as written, with whitespace collapsed
    text: str


def create_category(text: str) -> Category:
    """
    Create a category from voter-written text.

    Raises:
        InvalidCategoryError: If the text is empty or too long
    """
    normalized = normalize_category_text(text)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return Category(id=f"cat_{digest[:12]}", text=_collapse_whitespace(text))


@dataclass(frozen=True)
class Person:
    """A member of the network."""

    id: PersonId
    # Jurisdictions this person lives in. They originate one vote per
    # question on any ballot paper issued to one of these.
    residences: frozenset[JurisdictionId] = frozenset()


@dataclass(frozen=True)
class Delegation:
    """One person handing one category of decisions to another."""

    delegator: PersonId
    category: CategoryId
    delegate: PersonId


@dataclass(frozen=True)
class Network:
    """
    Persons, the categories they wrote, and who delegates what to whom.

    The order of `delegations` matters: a person's delegations, read in that
    order, are their category list, which breaks exact score ties when a
    question is routed.

    Construction validates that the parts fit together. It does not reject
    delegation loops; graph.add_delegation does that when a delegation is
    created, and graph.resolve_question handles any loop that remains.

    Raises:
        InvalidNetworkError: If an id is inconsistent, a delegation names an
            unknown person or category, a person delegates to themself, or a
            person delegates the same category twice
    """

    persons: Mapping[PersonId, Person]
    categories: Mapping[CategoryId, Category]
    delegations: tuple[Delegation, ...] = ()
    _by_delegator: Mapping[PersonId, tuple[Delegation, ...]] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        persons = dict(self.persons)
        categories = dict(self.categories)
        delegations = tuple(self.delegations)

        for person_id, person in persons.items():
            if person.id != person_id:
                raise InvalidNetworkError(
                    f"Person {person.id!r} is stored under id {person_id!r}"
                )
        for category_id, category in categories.items():
            if category.id != category_id:
                raise InvalidNetworkError(
                    f"Category {category.id!r} is stored under id {category_id!r}"
                )

        by_delegator: dict[PersonId, list[Delegation]] = {}
        seen: set[tuple[PersonId, CategoryId]] = set()
        for delegation in delegations:
            if delegation.delegator not in persons:
                raise InvalidNetworkError(f"Unknown delegator {delegation.delegator!r}")
            if delegation.delegate not in persons:
                raise InvalidNetworkError(f"Unknown delegate {delegation.delegate!r}")
            if delegation.category not in categories:
                raise InvalidNetworkError(f"Unknown category {delegation.category!r}")
            if delegation.delegator == delegation.delegate:
                raise InvalidNetworkError(
                    f"{delegation.delegator!r} cannot delegate to themself"
                )
            key = (delegation.delegator, delegation.category)
            if key in seen:
                raise InvalidNetworkError(
                    f"{delegation.delegator!r} already delegates "
                    f"category {delegation.category!r}"
                )
            seen.add(key)
            by_delegator.setdefault(delegation.delegator, []).append(delegation)

        object.__setattr__(self, "persons", persons)
        object.__setattr__(self, "categories", categories)
        object.__setattr__(self, "delegations", delegations)
        object.__setattr__(
            self,
            "_by_delegator",
            {person: tuple(items) for person, items in by_delegator.items()},
        )

    def delegations_of(self, person: PersonId) -> tuple[Delegation, ...]:
        """This person's delegations, in their category list order."""
        return self._by_delegator.get(person, ())

    def delegate_for(self, person: PersonId, category: CategoryId) -> PersonId | None:
        """Who this person delegates the category to, if anyone."""
        for delegation in self.delegations_of(person):
            if delegation.category == category:
                return delegation.delegate
        return None


def create_network(
    persons: Iterable[Person],
    categories: Iterable[Category] = (),
    delegations: Iterable[Delegation] = (),
) -> Network:
    """
    Create a network from its parts.

    Raises:
        InvalidNetworkError: If a person or category id repeats, or the parts
            do not fit together (see Network)
    """
    person_map: dict[PersonId, Person] = {}
    for person in persons:
        if person.id in person_map:
            raise InvalidNetworkError(f"Person {person.id!r} appears twice")
        person_map[person.id] = person

    category_map: dict[CategoryId, Category] = {}
    for category in categories:
        # The same text written twice is one category; the first wording stays.
        category_map.setdefault(category.id, category)

    return Network(
        persons=person_map,
        categories=category_map,
        delegations=tuple(delegations),
    )


@dataclass(frozen=True)
class Question:
    """One question on a ballot paper: a measure and its options."""

    id: QuestionId
    title: str
    summary: str
    options: tuple[Candidate, ...]


@dataclass(frozen=True)
class BallotPaper:
    """
    The questions put to one jurisdiction.

    Build one with create_ballot_paper, which checks the question ids;
    constructing the dataclass directly skips that.
    """

    jurisdiction: JurisdictionId
    questions: tuple[Question, ...]


def create_ballot_paper(
    jurisdiction: JurisdictionId, questions: Iterable[Question]
) -> BallotPaper:
    """
    Create a ballot paper.

    Raises:
        InvalidBallotPaperError: If there are no questions or a question id
            repeats
    """
    ordered = tuple(questions)
    if not ordered:
        raise InvalidBallotPaperError("A ballot paper needs at least one question")
    ids = [question.id for question in ordered]
    if len(ids) != len(set(ids)):
        raise InvalidBallotPaperError("Question ids repeat on the ballot paper")
    return BallotPaper(jurisdiction=jurisdiction, questions=ordered)


def validate_probability(value: float, what: str) -> float:
    """
    Check that a value is a probability.

    Raises:
        InvalidJudgmentError: If the value is not a finite number in [0, 1]
    """
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise InvalidJudgmentError(f"{what} must be between 0 and 1, got {value!r}")
    return value
