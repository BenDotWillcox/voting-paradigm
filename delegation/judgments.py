"""
Judgments: what the routing rule reads, and where they come from.

A judgment is a decision model's probability that a ballot question is
primarily about a voter-written category. The model is asked one yes/no
question per (question, category) pair; the routing rule in routing.py then
makes the decision.

Hosted decision models are not repeatable to the last digit, so judgments
are recorded:

  - Every (model, question content, instruction) is hashed to a key.
  - The first response for a key is stored and never replaced.
  - Resolution reads only stored judgments, so a run is deterministic given
    its store.

This module is pure apart from the store's file. The network lives in
jev.py, behind the JudgmentSource protocol, and tests use a scripted source.

Failing closed: when a source is missing or fails, the pair simply has no
judgment, and the routing rule keeps that vote with its holder.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generic, Protocol, TypeVar

from .types import (
    Category,
    CategoryId,
    InvalidJudgmentError,
    Question,
    QuestionId,
    validate_probability,
)

# The yes/no question asked about each category. The wording is part of every
# judgment's key, so changing it starts a fresh set of recorded judgments.
NOUL_INSTRUCTION = (
    "Is this ballot question primarily about the following topic? Topic: {topic}"
)


class JudgmentUnavailable(Exception):
    """Raised by a source that could not produce judgments for a request."""


def question_state(question: Question) -> dict[str, object]:
    """The content of a question as the decision model sees it."""
    return {
        "title": question.title,
        "summary": question.summary,
        "options": [option.name for option in question.options],
    }


def category_instruction(category: Category) -> str:
    """The yes/no question asked about one category."""
    return NOUL_INSTRUCTION.format(topic=category.text)


def judgment_key(model: str, question: Question, category: Category) -> str:
    """
    The identity of one judgment: the model and exactly what it was asked.

    Question and category ids are left out on purpose. Two questions with the
    same content, or one category text held by many voters, share a judgment.
    """
    asked = {
        "model": model,
        "type": "noul",
        "state": question_state(question),
        "instructions": category_instruction(category),
    }
    canonical = json.dumps(asked, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceAnswer:
    """One probability from a source, with the model that produced it."""

    probability: float
    answered_by: str


class JudgmentSource(Protocol):
    """Anything that can judge a question against some categories."""

    @property
    def model(self) -> str:
        """The pinned model id this source asks."""
        ...

    def judge(
        self, question: Question, categories: Sequence[Category]
    ) -> Mapping[CategoryId, SourceAnswer]:
        """
        Judge one question against each category.

        Raises:
            JudgmentUnavailable: If the request failed or its answer could
                not be trusted
        """
        ...


@dataclass(frozen=True)
class JudgmentRecord:
    """A stored judgment."""

    key: str
    # The pinned model id that was asked, and the id the response reported
    model: str
    answered_by: str
    question: QuestionId
    category: CategoryId
    category_text: str
    probability: float
    # When it was recorded (UTC, ISO 8601). Not part of the judgment's identity.
    recorded_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Stored(Protocol):
    """What a record needs for the store to keep it."""

    @property
    def key(self) -> str: ...

    @property
    def probability(self) -> float: ...


R = TypeVar("R", bound=_Stored)


class RecordStore(Generic[R]):
    """
    An append-only store of first responses, one JSON object per line.

    With no path the store lives in memory, which is what tests use.

    Raises:
        InvalidJudgmentError: If the file holds a line that is not a valid
            record
    """

    def __init__(self, record_type: Callable[..., R], path: Path | None = None) -> None:
        self._record_type = record_type
        self._path = path
        self._records: dict[str, R] = {}
        if path is not None and path.exists():
            with path.open(encoding="utf-8") as lines:
                for number, line in enumerate(lines, start=1):
                    if not line.strip():
                        continue
                    record = self._parse(line, number)
                    # The first response for a key is the one that counts.
                    self._records.setdefault(record.key, record)

    def _parse(self, line: str, number: int) -> R:
        try:
            record = self._record_type(**json.loads(line))
        except (ValueError, TypeError) as error:
            raise InvalidJudgmentError(
                f"{self._path}: line {number} is not a valid record"
            ) from error
        validate_probability(record.probability, f"{self._path}: line {number}")
        return record

    def __len__(self) -> int:
        return len(self._records)

    def get(self, key: str) -> R | None:
        """The stored record for a key, if there is one."""
        return self._records.get(key)

    def record(self, record: R) -> R:
        """
        Store a record unless its key already has one.

        Returns:
            The record now stored under the key: the existing one if there
            was one, otherwise the new one.

        Raises:
            InvalidJudgmentError: If the probability is not a probability
        """
        existing = self._records.get(record.key)
        if existing is not None:
            return existing
        validate_probability(record.probability, f"Record {record.key[:12]}")
        if self._path is not None:
            fields: dict[str, Any] = dict(vars(record))
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8", newline="\n") as lines:
                lines.write(json.dumps(fields, sort_keys=True) + "\n")
        self._records[record.key] = record
        return record


class JudgmentStore(RecordStore[JudgmentRecord]):
    """The recorded yes/no judgments, one per question and category."""

    def __init__(self, path: Path | None = None) -> None:
        super().__init__(JudgmentRecord, path)


@dataclass(frozen=True)
class GatherReport:
    """The judgments available for some questions, and how they were obtained."""

    # What the routing rule reads
    judgments: dict[tuple[QuestionId, CategoryId], float]
    # Pairs served from the store, and pairs newly judged and stored
    recorded: int
    fetched: int
    # Pairs with no judgment, because there was no source or it failed
    missing: tuple[tuple[QuestionId, CategoryId], ...]
    # One message per failed request
    failures: tuple[str, ...]


def gather_judgments(
    questions: Iterable[Question],
    categories: Iterable[Category],
    store: JudgmentStore,
    *,
    model: str,
    source: JudgmentSource | None = None,
    batch_size: int = 50,
    clock: Callable[[], str] = _utc_now,
) -> GatherReport:
    """
    Collect the judgments for every (question, category) pair.

    Stored judgments are used first. Pairs without one are sent to the
    source, a question at a time, and each new answer is stored before it is
    used. A failed request leaves its pairs without a judgment; it does not
    stop the others.

    Args:
        questions: The questions to judge
        categories: The distinct categories in use
        store: Where judgments are recorded
        model: The pinned model id the judgments belong to
        source: Where missing judgments come from. With no source only
            stored judgments are returned.
        batch_size: The most categories sent in one request
        clock: Supplies the recording time

    Raises:
        ValueError: If the source asks a different model, or batch_size is
            not positive
    """
    if source is not None and source.model != model:
        raise ValueError(
            f"The source asks {source.model!r} but judgments were requested "
            f"for {model!r}"
        )
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    distinct: dict[CategoryId, Category] = {}
    for category in categories:
        distinct.setdefault(category.id, category)

    judgments: dict[tuple[QuestionId, CategoryId], float] = {}
    missing: list[tuple[QuestionId, CategoryId]] = []
    failures: list[str] = []
    recorded = 0
    fetched = 0

    for question in questions:
        wanted: list[Category] = []
        for category in distinct.values():
            stored = store.get(judgment_key(model, question, category))
            if stored is None:
                wanted.append(category)
            else:
                judgments[(question.id, category.id)] = stored.probability
                recorded += 1

        for start in range(0, len(wanted), batch_size):
            batch = wanted[start : start + batch_size]
            answers: Mapping[CategoryId, SourceAnswer] = {}
            if source is not None:
                try:
                    answers = source.judge(question, batch)
                except JudgmentUnavailable as error:
                    failures.append(f"{question.id}: {error}")
            for category in batch:
                answer = answers.get(category.id)
                if answer is None or answer.answered_by != model:
                    missing.append((question.id, category.id))
                    continue
                kept = store.record(
                    JudgmentRecord(
                        key=judgment_key(model, question, category),
                        model=model,
                        answered_by=answer.answered_by,
                        question=question.id,
                        category=category.id,
                        category_text=category.text,
                        probability=answer.probability,
                        recorded_at=clock(),
                    )
                )
                judgments[(question.id, category.id)] = kept.probability
                fetched += 1

    return GatherReport(
        judgments=judgments,
        recorded=recorded,
        fetched=fetched,
        missing=tuple(missing),
        failures=tuple(failures),
    )
