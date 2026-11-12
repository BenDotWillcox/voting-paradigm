"""
The curated scenario: a category pool, a timeline of ballot papers, the
viewer's starting account, and the recorded judgments.

Everything the demo routes with by default is in one tracked file,
delegation/data/scenario_v2.json, so it runs without an API key and gives
the same answers every time. The file is built from the router evaluation's
recorded answers by scripts/build_delegation_scenario.py; nothing in it was
judged separately.

Time is relative. Each ballot paper says how many days from "today" it
closes: a negative number is a closed paper, part of everyone's history, and
a positive one is still open. Nothing stores a calendar date, so the
scenario reads the same on whatever day it is opened.

The viewer starts with an account that is already in use: delegations they
made earlier, and a past in which they voted on some closed questions
themself and missed others.

Reading the file is the only I/O here, and it happens when load_scenario is
called, not at import.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from voting.types import Candidate

from .nesting import NestingPair
from .simulate import SimulationConfig
from .types import (
    BallotPaper,
    Category,
    CategoryId,
    PersonId,
    Question,
    QuestionId,
    create_ballot_paper,
    create_category,
    validate_probability,
)

SCENARIO_SCHEMA = "delegation_scenario.v2"
SCENARIO_PATH = Path(__file__).resolve().parent / "data" / "scenario_v2.json"

# Every question in the scenario is a yes/no measure.
YES_NO = (Candidate("yes", "Yes"), Candidate("no", "No"))

# The synthetic population the scenario runs on. The delegations to the
# viewer are authored, in categories the viewer does not hand on, so that the
# viewer answers for other people, including on ballot papers issued to
# districts the viewer does not live in.
SCENARIO_SIMULATION = SimulationConfig(
    viewer_inbound=(
        (1, "the city budget and spending"),
        (1, "public libraries"),
        (2, "transportation and roads"),
        (2, "parks and recreation"),
        (2, "public libraries"),
        (2, "noise rules and nightlife"),
        (3, "water and sewer systems"),
        (3, "wages and working conditions"),
        (3, "public health and health care"),
    )
)


class InvalidScenarioError(ValueError):
    """Raised when the scenario file does not hold together."""


@dataclass(frozen=True)
class ScenarioPaper:
    """A curated ballot paper, the name shown for it, and when it closes."""

    id: str
    title: str
    paper: BallotPaper
    # Days from today until the paper closes; negative when it already has
    closes_in_days: int

    @property
    def is_open(self) -> bool:
        return self.closes_in_days > 0


@dataclass(frozen=True)
class ScenarioViewer:
    """The account the viewer starts with."""

    # Category text and delegate, in the viewer's category list order
    delegations: tuple[tuple[str, PersonId], ...]
    # Where the viewer sits in the spatial model, for their past votes only
    position: float
    # Closed questions the viewer held and did not vote on
    missed: frozenset[QuestionId]
    # Closed questions the viewer voted on themself despite a delegation
    voted_directly: frozenset[QuestionId]


@dataclass(frozen=True)
class Scenario:
    """The curated pool, ballot papers, viewer account and recorded judgments."""

    # The pinned model the judgments came from, and the thresholds they were
    # evaluated with
    model: str
    threshold: float
    nesting_threshold: float
    categories: tuple[Category, ...]
    # (narrow, broad) pairs of pool categories
    nesting: frozenset[NestingPair]
    # Oldest first
    papers: tuple[ScenarioPaper, ...]
    viewer: ScenarioViewer
    # One recorded judgment per scenario question and pool category
    judgments: Mapping[tuple[QuestionId, CategoryId], float]

    @property
    def questions(self) -> tuple[Question, ...]:
        """Every question on every ballot paper, in order."""
        return tuple(
            question for entry in self.papers for question in entry.paper.questions
        )

    @property
    def open_papers(self) -> tuple[ScenarioPaper, ...]:
        """The papers still open, soonest to close first."""
        return tuple(
            sorted(
                (entry for entry in self.papers if entry.is_open),
                key=lambda entry: entry.closes_in_days,
            )
        )

    @property
    def closed_papers(self) -> tuple[ScenarioPaper, ...]:
        """The papers that have closed, oldest first."""
        return tuple(entry for entry in self.papers if not entry.is_open)

    def paper(self, paper_id: str) -> ScenarioPaper:
        """The ballot paper with this id (KeyError when there is none)."""
        for entry in self.papers:
            if entry.id == paper_id:
                return entry
        raise KeyError(paper_id)

    def category(self, category_id: CategoryId) -> Category | None:
        """The pool category with this id, if it is in the pool."""
        for category in self.categories:
            if category.id == category_id:
                return category
        return None


def load_scenario(path: Path = SCENARIO_PATH) -> Scenario:
    """
    Load and check the curated scenario.

    Raises:
        InvalidScenarioError: If the schema is wrong, a category id does not
            match its text, a question or paper id repeats, a paper closes
            today, the papers are out of order, the nesting or the viewer's
            account names something unknown, or a judgment is missing
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != SCENARIO_SCHEMA:
        raise InvalidScenarioError(f"Expected schema {SCENARIO_SCHEMA!r}")

    categories: list[Category] = []
    for item in raw["categories"]:
        category = create_category(item["text"])
        if category.id != item["id"]:
            raise InvalidScenarioError(
                f"Category id {item['id']!r} does not match its text"
            )
        categories.append(category)
    known = {category.id for category in categories}
    if len(known) != len(categories):
        raise InvalidScenarioError("A category appears twice")

    nesting = frozenset((narrow, broad) for narrow, broad in raw["nesting"])
    for narrow, broad in nesting:
        if narrow not in known or broad not in known:
            raise InvalidScenarioError("The nesting names a category outside the pool")

    papers: list[ScenarioPaper] = []
    seen: set[QuestionId] = set()
    closed: set[QuestionId] = set()
    for item in raw["ballot_papers"]:
        questions = [
            Question(question["id"], question["title"], question["summary"], YES_NO)
            for question in item["questions"]
        ]
        closes = item["closes_in_days"]
        if not isinstance(closes, int) or isinstance(closes, bool) or closes == 0:
            raise InvalidScenarioError(
                f"Ballot paper {item['id']!r} needs a whole, non-zero closes_in_days"
            )
        for question in questions:
            if question.id in seen:
                raise InvalidScenarioError(f"Question {question.id!r} appears twice")
            seen.add(question.id)
            if closes < 0:
                closed.add(question.id)
        papers.append(
            ScenarioPaper(
                item["id"],
                item["title"],
                create_ballot_paper(item["jurisdiction"], questions),
                closes,
            )
        )
    if len({entry.id for entry in papers}) != len(papers):
        raise InvalidScenarioError("A ballot paper id appears twice")
    if [entry.closes_in_days for entry in papers] != sorted(
        entry.closes_in_days for entry in papers
    ):
        raise InvalidScenarioError("The ballot papers are not in closing order")

    judgments: dict[tuple[QuestionId, CategoryId], float] = {}
    for question_id in seen:
        scores = raw["judgments"].get(question_id, {})
        for category_id in known:
            if category_id not in scores:
                raise InvalidScenarioError(
                    f"No judgment for question {question_id!r} and {category_id!r}"
                )
            judgments[(question_id, category_id)] = validate_probability(
                scores[category_id], f"Judgment for {question_id!r}"
            )

    return Scenario(
        model=raw["model"],
        threshold=validate_probability(raw["threshold"], "Threshold"),
        nesting_threshold=validate_probability(
            raw["nesting_threshold"], "Nesting threshold"
        ),
        categories=tuple(categories),
        nesting=nesting,
        papers=tuple(papers),
        viewer=_viewer(raw["viewer"], known, closed),
        judgments=judgments,
    )


def _viewer(
    raw: Mapping[str, object], pool: set[CategoryId], closed: set[QuestionId]
) -> ScenarioViewer:
    """The viewer's starting account, checked against the pool and the closed questions."""
    delegations: list[tuple[str, PersonId]] = []
    held: set[CategoryId] = set()
    entries = raw["delegations"]
    if not isinstance(entries, list):
        raise InvalidScenarioError("The viewer's delegations must be a list")
    for item in entries:
        category = create_category(item["category"])
        if category.id not in pool:
            raise InvalidScenarioError(
                f"The viewer starts with {item['category']!r}, which is not in the pool"
            )
        if category.id in held:
            raise InvalidScenarioError(
                f"The viewer starts with {item['category']!r} twice"
            )
        held.add(category.id)
        delegations.append((category.text, item["delegate"]))

    def question_ids(name: str) -> frozenset[QuestionId]:
        ids = raw[name]
        if not isinstance(ids, list):
            raise InvalidScenarioError(f"The viewer's {name} must be a list")
        unknown = sorted(set(ids) - closed)
        if unknown:
            raise InvalidScenarioError(
                f"The viewer's {name} name questions that have not closed: {unknown}"
            )
        return frozenset(ids)

    missed = question_ids("missed")
    voted_directly = question_ids("voted_directly")
    if missed & voted_directly:
        raise InvalidScenarioError("The viewer both missed and voted on a question")
    position = raw["position"]
    if not isinstance(position, (int, float)) or isinstance(position, bool):
        raise InvalidScenarioError("The viewer's position must be a number")
    return ScenarioViewer(
        delegations=tuple(delegations),
        position=float(position),
        missed=missed,
        voted_directly=voted_directly,
    )
