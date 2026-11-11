"""
The demo 5 router evaluation: does highest-score-wins routing send ballot
questions where a voter would want them to go?

The inputs are a category pool and labelled ballot questions
(eval/fixtures/delegation_router_v1.json) and recorded decision-model
judgments. Everything here is pure and deterministic; collecting judgments
from hosted Jev is the runner's job (eval/run_delegation_router_eval.py).

What is measured:

  - Routing errors. Seeded voter category lists are routed with the real
    rule (delegation.route). Sending a question to a category it is not
    about is a false delegation, the expensive error. Keeping a question the
    voter had an acceptable category for is a false keep, the cheap one.
    Both are reported against coverage across thresholds.
  - Nested categories. For every question that sits squarely inside a
    narrow category, who gets the vote when the voter also holds the broad
    category above it. A yes/no score measures whether a statement is true,
    and the broad statement is true whenever the narrow one is, so the broad
    category may win. This is the open question in the design doc.
  - The single-choice arm. The same voter lists asked as one choice question
    with a "none" option, scored the same way.
  - Repeat spread. How far the same judgment moves between calls.

Limits: the pool and questions are synthetic and labelled by one author, the
voter lists are sampled, and every number describes one pinned model.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from delegation import (
    DEFAULT_NESTING_THRESHOLD,
    DEFAULT_THRESHOLD,
    Category,
    CategoryId,
    Delegation,
    Judgments,
    Network,
    Person,
    Question,
    RouteOutcome,
    create_category,
    create_network,
    derive_nesting,
    route,
)
from delegation.judgments import category_instruction, question_state
from delegation.nesting import NESTING_STATE, NestingPair, nesting_instruction
from voting import Candidate

NO_NESTING: frozenset[NestingPair] = frozenset()

STUDY_ID = "delegation_router_v1"
FIXTURE_SCHEMA = "delegation_router_fixture.v1"
FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "delegation_router_v1.json"
)

# Every question in the fixture is a yes/no measure.
OPTIONS = (Candidate("yes", "Yes"), Candidate("no", "No"))

# The single-choice comparison arm
NONE_OPTION = "none of these"
CHOICE_INSTRUCTION = (
    "Which of these topics is this ballot question primarily about? "
    f"Answer '{NONE_OPTION}' if it is not primarily about any of them."
)

# TypeSafe's list price for Jev input tokens; output tokens are free.
USD_PER_MILLION_INPUT_TOKENS = 0.042

VOTER = "voter"


class InvalidFixtureError(ValueError):
    """Raised when the category pool or labelled questions are inconsistent."""


@dataclass(frozen=True)
class PoolCategory:
    """A category in the pool, with the broad category it sits inside, if any."""

    key: str
    category: Category
    parent: str | None


@dataclass(frozen=True)
class LabelledQuestion:
    """A ballot question and the pool categories it is about."""

    question: Question
    # Categories a voter would accept this question being routed to
    acceptable: frozenset[str]
    # Narrow categories the question sits squarely inside
    squarely_inside: frozenset[str]


@dataclass(frozen=True)
class RouterFixture:
    """The category pool and the labelled questions."""

    categories: tuple[PoolCategory, ...]
    questions: tuple[LabelledQuestion, ...]

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(entry.key for entry in self.categories)

    def entry(self, key: str) -> PoolCategory:
        for entry in self.categories:
            if entry.key == key:
                return entry
        raise KeyError(key)

    def key_of(self, category: CategoryId) -> str:
        for entry in self.categories:
            if entry.category.id == category:
                return entry.key
        raise KeyError(category)

    def labelled(self, question: str) -> LabelledQuestion:
        for labelled in self.questions:
            if labelled.question.id == question:
                return labelled
        raise KeyError(question)


def load_fixture(path: Path = FIXTURE_PATH) -> RouterFixture:
    """
    Load and check the category pool and labelled questions.

    Raises:
        InvalidFixtureError: If keys repeat, a parent or category is unknown,
            nesting is more than one level deep, or a question's labels do
            not fit the pool
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != FIXTURE_SCHEMA:
        raise InvalidFixtureError(f"Expected schema {FIXTURE_SCHEMA!r}")

    categories: list[PoolCategory] = []
    for item in raw["categories"]:
        categories.append(
            PoolCategory(item["key"], create_category(item["text"]), item["parent"])
        )
    keys = [entry.key for entry in categories]
    if len(keys) != len(set(keys)):
        raise InvalidFixtureError("Category keys repeat")
    if len({entry.category.id for entry in categories}) != len(categories):
        raise InvalidFixtureError("Two categories have the same text")
    by_key = {entry.key: entry for entry in categories}
    for entry in categories:
        if entry.parent is None:
            continue
        parent = by_key.get(entry.parent)
        if parent is None:
            raise InvalidFixtureError(f"{entry.key}: unknown parent {entry.parent!r}")
        if parent.parent is not None:
            raise InvalidFixtureError(f"{entry.key}: nesting is one level deep only")

    questions: list[LabelledQuestion] = []
    for item in raw["questions"]:
        acceptable = frozenset(item["acceptable"])
        squarely = frozenset(item["squarely_inside"])
        name = item["id"]
        if not acceptable <= by_key.keys():
            raise InvalidFixtureError(f"{name}: unknown category in 'acceptable'")
        if not squarely <= acceptable:
            raise InvalidFixtureError(
                f"{name}: 'squarely_inside' must be a subset of 'acceptable'"
            )
        for key in squarely:
            parent_key = by_key[key].parent
            if parent_key is None:
                raise InvalidFixtureError(f"{name}: {key} is not a nested category")
            if parent_key not in acceptable:
                raise InvalidFixtureError(
                    f"{name}: the parent of {key} must be acceptable too"
                )
        questions.append(
            LabelledQuestion(
                Question(name, item["title"], item["summary"], OPTIONS),
                acceptable,
                squarely,
            )
        )
    ids = [labelled.question.id for labelled in questions]
    if len(ids) != len(set(ids)):
        raise InvalidFixtureError("Question ids repeat")
    return RouterFixture(tuple(categories), tuple(questions))


# ---------------------------------------------------------------------------
# Voter category lists
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouterEvalConfig:
    """The evaluation's fixed parameters."""

    seed: int = 20261110
    # Voter category lists drawn per question, and the longest list
    sets_per_question: int = 8
    max_set_size: int = 5
    # The threshold reported in the headline, and the sweep
    operating_threshold: float = DEFAULT_THRESHOLD
    thresholds: tuple[float, ...] = tuple(
        round(0.05 * step, 2) for step in range(1, 20)
    )
    # Repeat-call spread: this many questions, each judged this many times
    repeat_questions: int = 12
    repeats: int = 4
    # How sure the model must be that one category sits inside another
    nesting_threshold: float = DEFAULT_NESTING_THRESHOLD


@dataclass(frozen=True)
class VoterCase:
    """One voter's category list facing one question."""

    question: str
    # Pool keys in the voter's category list order
    keys: tuple[str, ...]


def voter_cases(
    fixture: RouterFixture, config: RouterEvalConfig
) -> tuple[VoterCase, ...]:
    """
    Draw seeded voter category lists for every question.

    Half of each question's lists are drawn freely from the pool, which
    mostly produces lists the question does not belong to. The other half
    are forced to include one acceptable category, when the question has
    one, so both kinds of error get exercised. Each question has its own
    random stream, so adding a question does not change the others' lists.
    """
    cases: list[VoterCase] = []
    for labelled in fixture.questions:
        rng = random.Random(f"{config.seed}:{labelled.question.id}")
        for index in range(config.sets_per_question):
            size = rng.randint(1, config.max_set_size)
            if index % 2 == 0 and labelled.acceptable:
                anchor = rng.choice(sorted(labelled.acceptable))
                others = [key for key in fixture.keys if key != anchor]
                members = rng.sample(others, size - 1) + [anchor]
                rng.shuffle(members)
            else:
                members = rng.sample(list(fixture.keys), size)
            cases.append(VoterCase(labelled.question.id, tuple(members)))
    return tuple(cases)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class Verdict(Enum):
    """How one routing outcome compares with the labels."""

    CORRECT_DELEGATION = "correct_delegation"
    FALSE_DELEGATION = "false_delegation"
    CORRECT_KEEP = "correct_keep"
    FALSE_KEEP = "false_keep"
    # No answer was available for this case
    UNAVAILABLE = "unavailable"


def judge_outcome(
    labelled: LabelledQuestion, keys: Sequence[str], chosen: str | None
) -> Verdict:
    """
    Compare one outcome with the labels.

    Args:
        labelled: The question and its labels
        keys: The voter's category list
        chosen: The category the question was sent to, or None when the
            voter kept it
    """
    if chosen is not None:
        if chosen in labelled.acceptable:
            return Verdict.CORRECT_DELEGATION
        return Verdict.FALSE_DELEGATION
    if labelled.acceptable.isdisjoint(keys):
        return Verdict.CORRECT_KEEP
    return Verdict.FALSE_KEEP


@dataclass(frozen=True)
class Tally:
    """Routing outcomes over a set of voter cases."""

    cases: int
    # Cases whose list held an acceptable category
    delegable: int
    correct_delegations: int
    false_delegations: int
    correct_keeps: int
    false_keeps: int
    unavailable: int

    @property
    def scored(self) -> int:
        return self.cases - self.unavailable

    @property
    def delegated(self) -> int:
        return self.correct_delegations + self.false_delegations

    @property
    def coverage(self) -> float | None:
        """The share of scored cases that were sent to a delegate."""
        return self.delegated / self.scored if self.scored else None

    @property
    def false_delegation_rate(self) -> float | None:
        """Of the cases sent to a delegate, the share sent to a wrong one."""
        return self.false_delegations / self.delegated if self.delegated else None

    @property
    def false_keep_rate(self) -> float | None:
        """Of the cases with an acceptable category, the share kept."""
        return self.false_keeps / self.delegable if self.delegable else None

    def as_json(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "scored": self.scored,
            "delegable": self.delegable,
            "correct_delegations": self.correct_delegations,
            "false_delegations": self.false_delegations,
            "correct_keeps": self.correct_keeps,
            "false_keeps": self.false_keeps,
            "unavailable": self.unavailable,
            "coverage": _rounded(self.coverage),
            "false_delegation_rate": _rounded(self.false_delegation_rate),
            "false_keep_rate": _rounded(self.false_keep_rate),
        }


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _tally(
    fixture: RouterFixture,
    outcomes: Iterable[tuple[VoterCase, Verdict]],
) -> Tally:
    counts = {verdict: 0 for verdict in Verdict}
    cases = 0
    delegable = 0
    for case, verdict in outcomes:
        cases += 1
        counts[verdict] += 1
        acceptable = fixture.labelled(case.question).acceptable
        if verdict is not Verdict.UNAVAILABLE and not acceptable.isdisjoint(case.keys):
            delegable += 1
    return Tally(
        cases=cases,
        delegable=delegable,
        correct_delegations=counts[Verdict.CORRECT_DELEGATION],
        false_delegations=counts[Verdict.FALSE_DELEGATION],
        correct_keeps=counts[Verdict.CORRECT_KEEP],
        false_keeps=counts[Verdict.FALSE_KEEP],
        unavailable=counts[Verdict.UNAVAILABLE],
    )


def voter_network(
    fixture: RouterFixture,
    keys: Sequence[str],
    nesting: frozenset[NestingPair] = NO_NESTING,
) -> Network:
    """
    One voter who has handed each category in the list to its own delegate.

    Only the nesting between categories in the list is kept.
    """
    entries = [fixture.entry(key) for key in keys]
    held = {entry.category.id for entry in entries}
    persons = [Person(VOTER)] + [Person(f"delegate:{key}") for key in keys]
    return create_network(
        persons,
        [entry.category for entry in entries],
        [
            Delegation(VOTER, entry.category.id, f"delegate:{entry.key}")
            for entry in entries
        ],
        nesting=[pair for pair in nesting if pair[0] in held and pair[1] in held],
    )


def routed_key(
    fixture: RouterFixture,
    case: VoterCase,
    judgments: Judgments,
    threshold: float,
    nesting: frozenset[NestingPair] = NO_NESTING,
) -> tuple[RouteOutcome, str | None]:
    """Route one voter case with the real routing rule."""
    decision = route(
        voter_network(fixture, case.keys, nesting),
        VOTER,
        case.question,
        judgments,
        threshold=threshold,
    )
    chosen = None if decision.category is None else fixture.key_of(decision.category)
    return decision.outcome, chosen


def route_case(
    fixture: RouterFixture,
    case: VoterCase,
    judgments: Judgments,
    threshold: float,
    nesting: frozenset[NestingPair] = NO_NESTING,
) -> Verdict:
    """Route one voter case with the real routing rule and judge the outcome."""
    outcome, chosen = routed_key(fixture, case, judgments, threshold, nesting)
    if outcome is RouteOutcome.ROUTER_UNAVAILABLE:
        return Verdict.UNAVAILABLE
    return judge_outcome(fixture.labelled(case.question), case.keys, chosen)


def score_router(
    fixture: RouterFixture,
    cases: Sequence[VoterCase],
    judgments: Judgments,
    threshold: float,
    nesting: frozenset[NestingPair] = NO_NESTING,
) -> Tally:
    """
    Route every voter case at one threshold.

    With no nesting this is plain highest-score-wins; with a nesting, a
    category gives way to a narrower one inside it that also clears.
    """
    return _tally(
        fixture,
        (
            (case, route_case(fixture, case, judgments, threshold, nesting))
            for case in cases
        ),
    )


# ---------------------------------------------------------------------------
# Nested categories
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NestedPair:
    """A question squarely inside a narrow category, and both categories' scores."""

    question: str
    narrow: str
    parent: str
    narrow_score: float
    parent_score: float


def nested_pairs(
    fixture: RouterFixture, judgments: Judgments
) -> tuple[NestedPair, ...]:
    """Every (question, narrow category) pair for which both judgments exist."""
    pairs: list[NestedPair] = []
    for labelled in fixture.questions:
        for key in sorted(labelled.squarely_inside):
            narrow = fixture.entry(key)
            if narrow.parent is None:
                continue
            parent = fixture.entry(narrow.parent)
            narrow_score = judgments.get((labelled.question.id, narrow.category.id))
            parent_score = judgments.get((labelled.question.id, parent.category.id))
            if narrow_score is None or parent_score is None:
                continue
            pairs.append(
                NestedPair(
                    labelled.question.id, key, parent.key, narrow_score, parent_score
                )
            )
    return tuple(pairs)


def summarize_nested(pairs: Sequence[NestedPair], threshold: float) -> dict[str, Any]:
    """
    Who gets the vote when a voter holds both the narrow and the broad category.

    The routing rule sends the question to the higher score if it clears the
    threshold, so the narrow category gets the vote only when it clears the
    threshold and outscores its parent. An exact tie is counted apart,
    because it is settled by the order of the voter's list.
    """
    narrow_gets = sum(
        pair.narrow_score >= threshold and pair.narrow_score > pair.parent_score
        for pair in pairs
    )
    parent_gets = sum(
        pair.parent_score >= threshold and pair.parent_score > pair.narrow_score
        for pair in pairs
    )
    tied = sum(
        pair.narrow_score >= threshold and pair.narrow_score == pair.parent_score
        for pair in pairs
    )
    both_clear = [
        pair
        for pair in pairs
        if pair.narrow_score >= threshold and pair.parent_score >= threshold
    ]
    margins = [pair.narrow_score - pair.parent_score for pair in pairs]
    return {
        "pairs": len(pairs),
        "threshold": threshold,
        "narrow_gets_the_vote": narrow_gets,
        "parent_gets_the_vote": parent_gets,
        "exact_ties_above_threshold": tied,
        "voter_keeps_it": len(pairs) - narrow_gets - parent_gets - tied,
        "narrow_clears_threshold": sum(p.narrow_score >= threshold for p in pairs),
        "parent_clears_threshold": sum(p.parent_score >= threshold for p in pairs),
        "both_clear_threshold": len(both_clear),
        "narrow_higher_when_both_clear": sum(
            pair.narrow_score > pair.parent_score for pair in both_clear
        ),
        "mean_narrow_minus_parent": _rounded(_mean(margins)),
        "smallest_margin": _rounded(min((abs(m) for m in margins), default=None)),
    }


def labelled_nesting(fixture: RouterFixture) -> frozenset[NestingPair]:
    """The nesting the fixture's author declared: each narrow category and its parent."""
    return frozenset(
        (entry.category.id, fixture.entry(entry.parent).category.id)
        for entry in fixture.categories
        if entry.parent is not None
    )


def ordered_pairs(fixture: RouterFixture) -> tuple[tuple[Category, Category], ...]:
    """Every ordered pair of distinct pool categories."""
    return tuple(
        (first.category, second.category)
        for first in fixture.categories
        for second in fixture.categories
        if first.key != second.key
    )


def nested_outcomes_under_rule(
    fixture: RouterFixture,
    pairs: Sequence[NestedPair],
    judgments: Judgments,
    threshold: float,
    nesting: frozenset[NestingPair],
) -> dict[str, Any]:
    """
    Who gets the vote for each nested pair once the rule knows a nesting.

    Each case is a voter holding the broad category first and the narrow
    one second, the list order least favourable to the narrow category.
    """
    counts = {"narrow": 0, "parent": 0, "kept": 0}
    for pair in pairs:
        case = VoterCase(pair.question, (pair.parent, pair.narrow))
        _, chosen = routed_key(fixture, case, judgments, threshold, nesting)
        if chosen == pair.narrow:
            counts["narrow"] += 1
        elif chosen == pair.parent:
            counts["parent"] += 1
        else:
            counts["kept"] += 1
    return {
        "pairs": len(pairs),
        "threshold": threshold,
        "narrow_gets_the_vote": counts["narrow"],
        "parent_gets_the_vote": counts["parent"],
        "voter_keeps_it": counts["kept"],
    }


def score_nesting_detection(
    fixture: RouterFixture,
    probabilities: Mapping[NestingPair, float],
    threshold: float,
) -> dict[str, Any]:
    """
    Compare the nesting derived from containment judgments with the labels.

    A detected pair the fixture did not declare is not necessarily wrong:
    the labels list one parent per narrow category and nothing else.
    """
    detected = derive_nesting(probabilities, threshold)
    labelled = labelled_nesting(fixture)

    def named(pairs: frozenset[NestingPair]) -> list[str]:
        return sorted(
            f"{fixture.key_of(narrow)} inside {fixture.key_of(broad)}"
            for narrow, broad in pairs
        )

    return {
        "threshold": threshold,
        "ordered_pairs_judged": len(probabilities),
        "labelled_pairs": len(labelled),
        "detected_pairs": len(detected),
        "labelled_and_detected": len(detected & labelled),
        "labelled_but_missed": named(labelled - detected),
        "detected_but_not_labelled": named(detected - labelled),
    }


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def score_separation(
    fixture: RouterFixture, judgments: Judgments, threshold: float
) -> dict[str, Any]:
    """How far apart acceptable and other (question, category) scores sit."""
    acceptable: list[float] = []
    other: list[float] = []
    for labelled in fixture.questions:
        for entry in fixture.categories:
            score = judgments.get((labelled.question.id, entry.category.id))
            if score is None:
                continue
            (acceptable if entry.key in labelled.acceptable else other).append(score)

    def describe(scores: Sequence[float]) -> dict[str, Any]:
        return {
            "pairs": len(scores),
            "mean_score": _rounded(_mean(scores)),
            "share_clearing_threshold": _rounded(
                _mean([float(score >= threshold) for score in scores])
            ),
        }

    return {
        "threshold": threshold,
        "acceptable": describe(acceptable),
        "not_acceptable": describe(other),
    }


# ---------------------------------------------------------------------------
# The single-choice arm
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChoiceRecord:
    """A recorded answer to one voter case asked as a single choice question."""

    question: str
    keys: tuple[str, ...]
    # The chosen pool key, or None when the model chose "none of these"
    choice: str | None
    # Probability per pool key, plus NONE_OPTION
    probabilities: dict[str, float]


def choice_options(fixture: RouterFixture, case: VoterCase) -> dict[str, str | None]:
    """
    The options for one voter case, in the voter's list order with "none" last.

    Each option is named by its category text and has no separate
    description, so there is no name and definition to disagree.
    """
    options: dict[str, str | None] = {
        fixture.entry(key).category.text: None for key in case.keys
    }
    options[NONE_OPTION] = None
    return options


def score_choice(
    fixture: RouterFixture,
    cases: Sequence[VoterCase],
    records: Iterable[ChoiceRecord],
) -> Tally:
    """Score the single-choice arm on the same voter cases."""
    recorded = {(record.question, record.keys): record for record in records}

    def verdict(case: VoterCase) -> Verdict:
        record = recorded.get((case.question, case.keys))
        if record is None:
            return Verdict.UNAVAILABLE
        return judge_outcome(fixture.labelled(case.question), case.keys, record.choice)

    return _tally(fixture, ((case, verdict(case)) for case in cases))


# ---------------------------------------------------------------------------
# Repeat-call spread
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepeatRecord:
    """The same judgment asked several times."""

    question: str
    category: str
    probabilities: tuple[float, ...]

    @property
    def spread(self) -> float:
        return max(self.probabilities) - min(self.probabilities)


def repeat_questions(
    fixture: RouterFixture, config: RouterEvalConfig
) -> tuple[LabelledQuestion, ...]:
    """The seeded sample of questions judged repeatedly."""
    rng = random.Random(f"{config.seed}:repeats")
    count = min(config.repeat_questions, len(fixture.questions))
    chosen = rng.sample(range(len(fixture.questions)), count)
    return tuple(fixture.questions[index] for index in sorted(chosen))


def summarize_repeats(
    records: Sequence[RepeatRecord], threshold: float
) -> dict[str, Any]:
    """How far repeated judgments move, and how many cross the threshold."""
    spreads = sorted(record.spread for record in records)
    straddling = sum(
        min(record.probabilities) < threshold <= max(record.probabilities)
        for record in records
    )
    return {
        "judgments": len(records),
        "calls_each": len(records[0].probabilities) if records else 0,
        "largest_spread": _rounded(spreads[-1] if spreads else None),
        "mean_spread": _rounded(_mean(spreads)),
        "identical_every_time": sum(spread == 0 for spread in spreads),
        "threshold": threshold,
        "crossing_the_threshold": straddling,
    }


# ---------------------------------------------------------------------------
# The summary and the plan
# ---------------------------------------------------------------------------


def summarize(
    fixture: RouterFixture,
    config: RouterEvalConfig,
    judgments: Judgments,
    choice_records: Sequence[ChoiceRecord],
    repeat_records: Sequence[RepeatRecord],
    nesting_probabilities: Mapping[NestingPair, float] | None = None,
) -> dict[str, Any]:
    """
    Every reported number, from recorded answers alone.

    `router_at_operating_threshold` and `nested_categories` describe plain
    highest-score-wins, the rule as first measured. The `*_with_rule`
    sections describe the rule with a nesting: once with the nesting the
    fixture's author declared, and once with the nesting derived from the
    recorded containment judgments, which is what a real voter would get.
    """
    cases = voter_cases(fixture, config)
    threshold = config.operating_threshold
    expected = len(fixture.questions) * len(fixture.categories)
    pairs = nested_pairs(fixture, judgments)
    containment = dict(nesting_probabilities or {})
    nestings = {
        "labelled_nesting": labelled_nesting(fixture),
        "detected_nesting": derive_nesting(containment, config.nesting_threshold),
    }
    return {
        "study": STUDY_ID,
        "fixture": {
            "categories": len(fixture.categories),
            "nested_categories": sum(e.parent is not None for e in fixture.categories),
            "questions": len(fixture.questions),
            "voter_cases": len(cases),
        },
        "judgments": {"expected": expected, "recorded": len(judgments)},
        "router_at_operating_threshold": {
            "threshold": threshold,
            **score_router(fixture, cases, judgments, threshold).as_json(),
        },
        "router_by_threshold": [
            {
                "threshold": value,
                **score_router(fixture, cases, judgments, value).as_json(),
            }
            for value in config.thresholds
        ],
        "nested_categories": summarize_nested(pairs, threshold),
        "nesting_detection": score_nesting_detection(
            fixture, containment, config.nesting_threshold
        ),
        "router_with_rule": {
            name: score_router(fixture, cases, judgments, threshold, nesting).as_json()
            for name, nesting in nestings.items()
        },
        "nested_categories_with_rule": {
            name: nested_outcomes_under_rule(
                fixture, pairs, judgments, threshold, nesting
            )
            for name, nesting in nestings.items()
        },
        "score_separation": score_separation(fixture, judgments, threshold),
        "single_choice_arm": score_choice(fixture, cases, choice_records).as_json(),
        "repeat_spread": summarize_repeats(repeat_records, threshold),
    }


def _tokens(payload: Mapping[str, Any]) -> int:
    """A rough token count: four characters of JSON per token."""
    return len(json.dumps(payload)) // 4


def plan(fixture: RouterFixture, config: RouterEvalConfig) -> dict[str, Any]:
    """
    What a full collection would send, without sending anything.

    The token and cost figures are rough: the tokenizer is not public, and
    this counts four characters of request JSON per token.
    """
    cases = voter_cases(fixture, config)
    categories = [entry.category for entry in fixture.categories]

    def judging(question: Question) -> int:
        return _tokens(
            {
                "state": question_state(question),
                "questions": {
                    category.id: {
                        "type": "noul",
                        "instructions": category_instruction(category),
                    }
                    for category in categories
                },
            }
        )

    judge_tokens = sum(judging(labelled.question) for labelled in fixture.questions)
    choice_tokens = sum(
        _tokens(
            {
                "state": question_state(fixture.labelled(case.question).question),
                "questions": {
                    "route": {
                        "type": "choice",
                        "instructions": CHOICE_INSTRUCTION,
                        "criteria": choice_options(fixture, case),
                    }
                },
            }
        )
        for case in cases
    )
    repeat_tokens = config.repeats * sum(
        judging(labelled.question) for labelled in repeat_questions(fixture, config)
    )
    # Containment: one request per category, asking whether it sits inside
    # each of the others.
    nesting_tokens = sum(
        _tokens(
            {
                "state": NESTING_STATE,
                "questions": {
                    f"pair_{index}": {
                        "type": "noul",
                        "instructions": nesting_instruction(narrow, broad),
                    }
                    for index, broad in enumerate(categories)
                    if broad.id != narrow.id
                },
            }
        )
        for narrow in categories
    )
    total = judge_tokens + choice_tokens + repeat_tokens + nesting_tokens
    return {
        "nesting": {
            "requests": len(categories),
            "judgments": len(categories) * (len(categories) - 1),
            "estimated_input_tokens": nesting_tokens,
        },
        "judging": {
            "requests": len(fixture.questions),
            "judgments": len(fixture.questions) * len(categories),
            "estimated_input_tokens": judge_tokens,
        },
        "single_choice_arm": {
            "requests": len(cases),
            "estimated_input_tokens": choice_tokens,
        },
        "repeat_spread": {
            "requests": config.repeats * len(repeat_questions(fixture, config)),
            "estimated_input_tokens": repeat_tokens,
        },
        "total_requests": len(fixture.questions)
        + len(cases)
        + config.repeats * len(repeat_questions(fixture, config))
        + len(categories),
        "estimated_input_tokens": total,
        "estimated_usd": round(total * USD_PER_MILLION_INPUT_TOKENS / 1_000_000, 4),
    }
