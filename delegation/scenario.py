"""
The curated scenario: a city, a category pool, a timeline of ballot papers,
the viewer's account and its past, and the recorded judgments.

Everything the demo routes with by default is in one tracked file,
delegation/data/scenario_v3.json, so it runs without an API key and gives
the same answers every time. scripts/build_delegation_scenario.py builds it
from two sources: the hand-written measures in delegation/data/measures_v3.json
and the recorded judgments.

A measure is a question with what a real ballot paper prints around it: the
official wording, a fiscal note, who placed it, and an argument each way.
Only its title, summary and option names are judged. Most measures are
yes/no; a few are a ranked choice or an approval vote among several options.

Time is relative. Each ballot paper says how many days from "today" it opens
and closes: a paper that closed has a negative closing day and is part of
everyone's history; one still open has a positive closing day. Nothing
stores a calendar date, so the scenario reads the same whenever it is opened.

The viewer starts with an account that is already in use: delegations they
made and changed on earlier days, and a past in which they voted on some
closed questions themself and missed others.

Reading the file is the only I/O here, and it happens when load_scenario is
called, not at import.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from voting.types import Candidate, CandidateId

from .ballots import BALLOT_TYPES, BallotType
from .nesting import NestingPair
from .simulate import DelegationChange, OptionSupport, SimulationConfig, Support
from .types import (
    BallotPaper,
    Category,
    CategoryId,
    JurisdictionId,
    PersonId,
    Question,
    QuestionId,
    create_ballot_paper,
    create_category,
    validate_probability,
)

SCENARIO_SCHEMA = "delegation_scenario.v3"
MEASURES_SCHEMA = "delegation_measures.v3"
DATA = Path(__file__).resolve().parent / "data"
SCENARIO_PATH = DATA / "scenario_v3.json"
MEASURES_PATH = DATA / "measures_v3.json"

# The options of a measure that lists none of its own.
YES_NO = (Candidate("yes", "Yes"), Candidate("no", "No"))

# How long a ballot paper is open before it closes, when it does not say
DEFAULT_OPEN_DAYS = 21

# The synthetic population the scenario runs on.
#
# The delegations to the viewer are authored, in categories the viewer does
# not hand on, so that the viewer answers for other people, including on
# ballot papers issued to districts the viewer does not live in.
#
# The districts differ a little on the three issue dimensions (public
# spending, growth and building, reform and regulation): Northside is the
# older, home-owning district, Harbor the dense downtown one, Eastgate the
# industrial east. Northside is the north half of the unit square, Harbor
# the south-west and Eastgate the south-east.
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
    ),
    district_leans=(
        (-0.15, -0.25, -0.10),
        (0.25, 0.30, 0.25),
        (0.10, 0.00, -0.15),
    ),
    district_areas=(
        (0.0, 0.5, 1.0, 1.0),
        (0.0, 0.0, 0.55, 0.5),
        (0.55, 0.0, 1.0, 0.5),
    ),
)


class InvalidScenarioError(ValueError):
    """Raised when the scenario file does not hold together."""


@dataclass(frozen=True)
class Measure:
    """A question and what the ballot paper prints around it."""

    question: Question
    # Its name on the paper, such as "Measure C"
    label: str
    # What sort of measure it is, such as "Bond" or "Charter amendment"
    kind: str
    ballot_type: BallotType
    # The official wording put to voters
    wording: str
    fiscal: str
    placed_by: str
    # One argument each way; empty for a choice among several options
    argument_for: str
    argument_against: str
    # A line about each option, where the measure gives one
    option_notes: Mapping[CandidateId, str]
    # How the toy population divides on it
    support: Support

    @property
    def site(self) -> tuple[float, float] | None:
        """Where the measure would be built, when it has one place."""
        sites = [
            drawn.site for drawn in self.support.options.values() if drawn.site is not None
        ]
        return sites[0] if len(sites) == 1 else None


@dataclass(frozen=True)
class ScenarioPaper:
    """A curated ballot paper, the name shown for it, and when it is open."""

    id: str
    title: str
    paper: BallotPaper
    # Days from today until the paper closes; negative when it already has
    closes_in_days: int
    # Days from today until it opens; negative once it has
    opens_in_days: int
    measures: tuple[Measure, ...]

    @property
    def is_open(self) -> bool:
        return self.closes_in_days > 0


@dataclass(frozen=True)
class ScenarioViewer:
    """The account the viewer starts with, and how it came to be."""

    # Category text and delegate today, in the viewer's category list order
    delegations: tuple[tuple[str, PersonId], ...]
    # Dated changes that led to those delegations; categories are by text
    changes: tuple[tuple[int, str, PersonId | None, PersonId | None], ...]
    # Where the viewer sits on the issue dimensions, for their past votes only
    position: tuple[float, ...]
    # Closed questions the viewer held and did not vote on
    missed: frozenset[QuestionId]
    # Closed questions the viewer voted on themself despite a delegation
    voted_directly: frozenset[QuestionId]

    def delegations_on(self, day: int) -> tuple[tuple[str, PersonId], ...]:
        """The viewer's delegations as they stood at the end of a day."""
        current = list(self.delegations)
        for changed, category, before, _after in sorted(
            self.changes, key=lambda change: -change[0]
        ):
            if changed <= day:
                continue
            index = next(
                (i for i, (text, _) in enumerate(current) if text == category), None
            )
            if before is None:
                if index is not None:
                    del current[index]
            elif index is None:
                current.append((category, before))
            else:
                current[index] = (category, before)
        return tuple(current)


@dataclass(frozen=True)
class Scenario:
    """The city, the pool, the ballot papers, the viewer and the judgments."""

    # The pinned model the judgments came from, and the thresholds they were
    # evaluated with
    model: str
    threshold: float
    nesting_threshold: float
    city: str
    # A name for each district, by jurisdiction id
    districts: Mapping[JurisdictionId, str]
    # Every category people in the network write: the pool, then the other
    # wordings of pool categories
    categories: tuple[Category, ...]
    # The other wordings some people use for a pool category, by its id
    wordings: Mapping[CategoryId, tuple[Category, ...]]
    # Categories the decision model judged to be the same thing, each
    # category in exactly one group
    groups: tuple[tuple[CategoryId, ...], ...]
    # (narrow, broad) pairs of categories
    nesting: frozenset[NestingPair]
    # Oldest first
    papers: tuple[ScenarioPaper, ...]
    viewer: ScenarioViewer
    # One recorded judgment per scenario question and pool category
    judgments: Mapping[tuple[QuestionId, CategoryId], float]
    # Questions whose judgments stand in for ones not yet recorded: they were
    # judged under earlier wording. Empty once the scenario is fully judged.
    provisional: frozenset[QuestionId]

    @property
    def pool(self) -> tuple[Category, ...]:
        """The categories people draw from, without their other wordings."""
        reworded = {
            wording.id for others in self.wordings.values() for wording in others
        }
        return tuple(
            category for category in self.categories if category.id not in reworded
        )

    def group_of(self, category_id: CategoryId) -> tuple[CategoryId, ...]:
        """The group a category is in; itself alone when it is not in the pool."""
        for group in self.groups:
            if category_id in group:
                return group
        return (category_id,)

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

    def measure(self, question_id: QuestionId) -> Measure:
        """The measure with this question id (KeyError when there is none)."""
        for entry in self.papers:
            for measure in entry.measures:
                if measure.question.id == question_id:
                    return measure
        raise KeyError(question_id)

    def category(self, category_id: CategoryId) -> Category | None:
        """The pool category with this id, if it is in the pool."""
        for category in self.categories:
            if category.id == category_id:
                return category
        return None

    def viewer_changes(self, viewer: PersonId) -> tuple[DelegationChange, ...]:
        """The viewer's dated changes, with categories by id, most recent first."""
        return tuple(
            DelegationChange(day, viewer, create_category(text).id, before, after)
            for day, text, before, after in sorted(
                self.viewer.changes, key=lambda change: -change[0]
            )
        )


# ---------------------------------------------------------------------------
# Reading measures (shared by the loader and the builder)
# ---------------------------------------------------------------------------


def _option_support(raw: Mapping[str, Any] | None) -> OptionSupport:
    raw = raw or {}
    site = raw.get("site")
    return OptionSupport(
        appeal=float(raw.get("appeal", 0.0)),
        lean=tuple(float(value) for value in raw.get("lean", ())),
        site=(float(site[0]), float(site[1])) if site is not None else None,
        local=float(raw.get("local", 0.0)),
    )


def label_for(index: int) -> str:
    """A measure's name on its paper: Measure A, B, ... by position."""
    letters = ""
    number = index
    while True:
        letters = chr(ord("A") + number % 26) + letters
        number = number // 26 - 1
        if number < 0:
            break
    return f"Measure {letters}"


def read_measure(raw: Mapping[str, Any], index: int) -> Measure:
    """
    One measure from its written form.

    Raises:
        InvalidScenarioError: If the ballot type is unknown, a choice among
            options lists fewer than two, or a yes/no measure lists options
    """
    ballot_type = raw.get("ballot_type", "single_choice")
    if ballot_type not in BALLOT_TYPES:
        raise InvalidScenarioError(
            f"Measure {raw['id']!r} has unknown ballot type {ballot_type!r}"
        )
    listed: Sequence[Mapping[str, Any]] = raw.get("options", ())
    notes: dict[CandidateId, str] = {}
    if listed:
        if len(listed) < 2:
            raise InvalidScenarioError(f"Measure {raw['id']!r} needs two options")
        options = tuple(Candidate(item["id"], item["name"]) for item in listed)
        notes = {item["id"]: item["note"] for item in listed if item.get("note")}
        support = {item["id"]: _option_support(item.get("support")) for item in listed}
    else:
        if ballot_type != "single_choice":
            raise InvalidScenarioError(
                f"Measure {raw['id']!r} is {ballot_type} but lists no options"
            )
        options = YES_NO
        support = {"yes": _option_support(raw.get("support"))}
    return Measure(
        question=Question(raw["id"], raw["title"], raw["summary"], options),
        label=raw.get("label") or label_for(index),
        kind=raw["kind"],
        ballot_type=ballot_type,
        wording=raw["wording"],
        fiscal=raw["fiscal"],
        placed_by=raw["placed_by"],
        argument_for=raw.get("for", ""),
        argument_against=raw.get("against", ""),
        option_notes=notes,
        support=Support(support, float(raw.get("salience", 1.0))),
    )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_scenario(path: Path = SCENARIO_PATH) -> Scenario:
    """
    Load and check the curated scenario.

    Raises:
        InvalidScenarioError: If the schema is wrong, a category id does not
            match its text, a question or paper id repeats, a paper closes
            today or opens after it closes, the papers are out of order, a
            measure is malformed, the nesting or the viewer's account names
            something unknown, or a judgment is missing
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

    by_id = {category.id: category for category in categories}
    wordings: dict[CategoryId, list[Category]] = {}
    for item in raw["categories"]:
        base = item.get("wording_of")
        if base is None:
            continue
        if base not in known or base == item["id"]:
            raise InvalidScenarioError(
                f"Category {item['id']!r} is a wording of nothing in the pool"
            )
        wordings.setdefault(base, []).append(by_id[item["id"]])
    if any(base in {w.id for ws in wordings.values() for w in ws} for base in wordings):
        raise InvalidScenarioError("A wording has wordings of its own")

    groups = tuple(tuple(group) for group in raw["groups"])
    grouped = [member for group in groups for member in group]
    if sorted(grouped) != sorted(known):
        raise InvalidScenarioError(
            "The groups do not hold every category exactly once"
        )

    nesting = frozenset((narrow, broad) for narrow, broad in raw["nesting"])
    for narrow, broad in nesting:
        if narrow not in known or broad not in known:
            raise InvalidScenarioError("The nesting names a category outside the pool")

    papers: list[ScenarioPaper] = []
    seen: set[QuestionId] = set()
    closed: set[QuestionId] = set()
    for item in raw["ballot_papers"]:
        measures = tuple(
            read_measure(measure, index)
            for index, measure in enumerate(item["measures"])
        )
        closes = item["closes_in_days"]
        if not isinstance(closes, int) or isinstance(closes, bool) or closes == 0:
            raise InvalidScenarioError(
                f"Ballot paper {item['id']!r} needs a whole, non-zero closes_in_days"
            )
        opens = item.get("opens_in_days", closes - DEFAULT_OPEN_DAYS)
        if not isinstance(opens, int) or isinstance(opens, bool) or opens >= closes:
            raise InvalidScenarioError(
                f"Ballot paper {item['id']!r} must open before it closes"
            )
        if closes > 0 and opens > 0:
            raise InvalidScenarioError(
                f"Ballot paper {item['id']!r} has not opened yet"
            )
        for measure in measures:
            question_id = measure.question.id
            if question_id in seen:
                raise InvalidScenarioError(f"Question {question_id!r} appears twice")
            seen.add(question_id)
            if closes < 0:
                closed.add(question_id)
        papers.append(
            ScenarioPaper(
                item["id"],
                item["title"],
                create_ballot_paper(
                    item["jurisdiction"], [measure.question for measure in measures]
                ),
                closes,
                opens,
                measures,
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

    provisional = frozenset(raw.get("provisional", ()))
    if provisional - seen:
        raise InvalidScenarioError("A provisional question is not in the scenario")

    return Scenario(
        model=raw["model"],
        threshold=validate_probability(raw["threshold"], "Threshold"),
        nesting_threshold=validate_probability(
            raw["nesting_threshold"], "Nesting threshold"
        ),
        city=raw["city"]["name"],
        districts=dict(raw["city"]["districts"]),
        categories=tuple(categories),
        wordings={base: tuple(others) for base, others in wordings.items()},
        groups=groups,
        nesting=nesting,
        papers=tuple(papers),
        viewer=read_viewer(raw["viewer"], known, closed),
        judgments=judgments,
        provisional=provisional,
    )


def read_viewer(
    raw: Mapping[str, Any], pool: set[CategoryId], closed: set[QuestionId]
) -> ScenarioViewer:
    """
    The viewer's account, checked against the pool and the closed questions.

    Raises:
        InvalidScenarioError: If a category is outside the pool or held
            twice, a change does not lead to today's delegations, or the
            missed and directly voted questions are not closed or overlap
    """
    delegations: list[tuple[str, PersonId]] = []
    held: dict[CategoryId, PersonId] = {}
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
        held[category.id] = item["delegate"]
        delegations.append((category.text, item["delegate"]))

    changes: list[tuple[int, str, PersonId | None, PersonId | None]] = []
    # Walking back from today, each change must start from what it left.
    standing = dict(held)
    for item in sorted(raw.get("changes", ()), key=lambda change: -change["day"]):
        category = create_category(item["category"])
        day, before, after = item["day"], item.get("before"), item.get("after")
        if not isinstance(day, int) or isinstance(day, bool) or day >= 0:
            raise InvalidScenarioError("A viewer change needs a whole day in the past")
        if category.id not in pool:
            raise InvalidScenarioError(
                f"A viewer change names {item['category']!r}, which is not in the pool"
            )
        if before == after or standing.get(category.id) != after:
            raise InvalidScenarioError(
                f"The viewer's change to {item['category']!r} on day {day} "
                "does not lead to what followed"
            )
        if before is None:
            standing.pop(category.id, None)
        else:
            standing[category.id] = before
        changes.append((day, category.text, before, after))

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
    if not isinstance(position, list) or not all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in position
    ):
        raise InvalidScenarioError("The viewer's position must be a list of numbers")
    return ScenarioViewer(
        delegations=tuple(delegations),
        changes=tuple(changes),
        position=tuple(float(value) for value in position),
        missed=missed,
        voted_directly=voted_directly,
    )
