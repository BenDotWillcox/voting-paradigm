"""
The curated scenario: a category pool, ballot papers, and their recorded
judgments.

Everything the demo routes with by default is in one tracked file,
delegation/data/scenario_v1.json, so it runs without an API key and gives
the same answers every time. The file is built from the router evaluation's
recorded answers by scripts/build_delegation_scenario.py; nothing in it was
judged separately.

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
    Question,
    QuestionId,
    create_ballot_paper,
    create_category,
    validate_probability,
)

SCENARIO_SCHEMA = "delegation_scenario.v1"
SCENARIO_PATH = Path(__file__).resolve().parent / "data" / "scenario_v1.json"

# Every question in the scenario is a yes/no measure.
YES_NO = (Candidate("yes", "Yes"), Candidate("no", "No"))

# The synthetic population the scenario runs on. The delegations to the
# viewer are authored so that the viewer answers for other people on both
# ballot papers, including the one issued to a district the viewer does not
# live in.
SCENARIO_SIMULATION = SimulationConfig(
    viewer_inbound=(
        (1, "public schools and education"),
        (1, "housing and land use"),
        (2, "transportation and roads"),
        (2, "parks and recreation"),
        (3, "the environment and conservation"),
        (3, "all things taxes"),
    )
)


class InvalidScenarioError(ValueError):
    """Raised when the scenario file does not hold together."""


@dataclass(frozen=True)
class ScenarioPaper:
    """A curated ballot paper with the name shown for it."""

    id: str
    title: str
    paper: BallotPaper


@dataclass(frozen=True)
class Scenario:
    """The curated pool, ballot papers and recorded judgments."""

    # The pinned model the judgments came from, and the thresholds they were
    # evaluated with
    model: str
    threshold: float
    nesting_threshold: float
    categories: tuple[Category, ...]
    # (narrow, broad) pairs of pool categories
    nesting: frozenset[NestingPair]
    papers: tuple[ScenarioPaper, ...]
    # One recorded judgment per scenario question and pool category
    judgments: Mapping[tuple[QuestionId, CategoryId], float]

    @property
    def questions(self) -> tuple[Question, ...]:
        """Every question on every ballot paper, in order."""
        return tuple(
            question for entry in self.papers for question in entry.paper.questions
        )

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
            match its text, a question id repeats, the nesting names an
            unknown category, or a judgment is missing
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
    for item in raw["ballot_papers"]:
        questions = [
            Question(question["id"], question["title"], question["summary"], YES_NO)
            for question in item["questions"]
        ]
        for question in questions:
            if question.id in seen:
                raise InvalidScenarioError(f"Question {question.id!r} appears twice")
            seen.add(question.id)
        papers.append(
            ScenarioPaper(
                item["id"],
                item["title"],
                create_ballot_paper(item["jurisdiction"], questions),
            )
        )
    if len({entry.id for entry in papers}) != len(papers):
        raise InvalidScenarioError("A ballot paper id appears twice")

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
        judgments=judgments,
    )
