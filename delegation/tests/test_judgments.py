"""Tests for recorded judgments and gathering them from a source."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from delegation import (
    Category,
    CategoryId,
    InvalidJudgmentError,
    Question,
    create_category,
    create_network,
    resolve_question,
)
from delegation import Person, add_delegation
from delegation.judgments import (
    JudgmentRecord,
    JudgmentStore,
    JudgmentUnavailable,
    SourceAnswer,
    category_instruction,
    gather_judgments,
    judgment_key,
    question_state,
)
from voting import Candidate

MODEL = "jev-1.14.0"
YES_NO = (Candidate("yes", "Yes"), Candidate("no", "No"))
LEVY = Question("levy", "Property tax levy", "Adds a levy for schools.", YES_NO)
FROGS = Question("frogs", "Amphibian habitat fund", "Protects tree frogs.", YES_NO)
TAXES = create_category("all things taxes")
TREE_FROGS = create_category("the well-being of tree frogs in the Amazon")


class ScriptedSource:
    """A source that answers from a table and remembers what it was asked."""

    def __init__(
        self,
        table: Mapping[tuple[str, CategoryId], float],
        *,
        model: str = MODEL,
        answered_by: str | None = None,
        fail_on: frozenset[str] = frozenset(),
    ) -> None:
        self._table = table
        self._model = model
        self._answered_by = answered_by or model
        self._fail_on = fail_on
        self.calls: list[tuple[str, tuple[CategoryId, ...]]] = []

    @property
    def model(self) -> str:
        return self._model

    def judge(
        self, question: Question, categories: Sequence[Category]
    ) -> Mapping[CategoryId, SourceAnswer]:
        self.calls.append((question.id, tuple(c.id for c in categories)))
        if question.id in self._fail_on:
            raise JudgmentUnavailable("HTTP 529")
        return {
            category.id: SourceAnswer(
                self._table[(question.id, category.id)], self._answered_by
            )
            for category in categories
            if (question.id, category.id) in self._table
        }


TABLE = {
    ("levy", TAXES.id): 0.97,
    ("levy", TREE_FROGS.id): 0.01,
    ("frogs", TAXES.id): 0.04,
    ("frogs", TREE_FROGS.id): 0.92,
}


def fixed_clock() -> str:
    return "2026-11-10T00:00:00+00:00"


class TestWhatIsAsked:
    def test_state_is_the_questions_content(self) -> None:
        assert question_state(LEVY) == {
            "title": "Property tax levy",
            "summary": "Adds a levy for schools.",
            "options": ["Yes", "No"],
        }

    def test_instruction_carries_the_category_text(self) -> None:
        assert category_instruction(TAXES).endswith("Topic: all things taxes")

    def test_key_depends_on_model_question_content_and_category_text(self) -> None:
        base = judgment_key(MODEL, LEVY, TAXES)
        assert base == judgment_key(MODEL, LEVY, TAXES)
        assert base != judgment_key("jev-1.13.0", LEVY, TAXES)
        assert base != judgment_key(MODEL, FROGS, TAXES)
        assert base != judgment_key(MODEL, LEVY, TREE_FROGS)

    def test_key_ignores_ids_so_identical_content_shares_a_judgment(self) -> None:
        renamed = Question("another-id", LEVY.title, LEVY.summary, LEVY.options)
        assert judgment_key(MODEL, renamed, TAXES) == judgment_key(MODEL, LEVY, TAXES)


class TestStore:
    def record(self, probability: float = 0.9, key: str = "k1") -> JudgmentRecord:
        return JudgmentRecord(
            key=key,
            model=MODEL,
            answered_by=MODEL,
            question="levy",
            category=TAXES.id,
            category_text=TAXES.text,
            probability=probability,
            recorded_at=fixed_clock(),
        )

    def test_first_response_wins(self) -> None:
        store = JudgmentStore()
        first = store.record(self.record(0.90))
        second = store.record(self.record(0.91))
        assert second is first
        stored = store.get("k1")
        assert stored is not None and stored.probability == 0.90
        assert len(store) == 1

    def test_records_survive_a_reload(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "judgments.jsonl"
        store = JudgmentStore(path)
        store.record(self.record(0.90, "k1"))
        store.record(self.record(0.20, "k2"))
        store.record(self.record(0.95, "k1"))

        reloaded = JudgmentStore(path)
        assert len(reloaded) == 2
        assert reloaded.get("k1") == self.record(0.90, "k1")
        assert len(path.read_text(encoding="utf-8").splitlines()) == 2

    def test_missing_key_is_none(self) -> None:
        assert JudgmentStore().get("absent") is None

    def test_invalid_probability_is_rejected(self) -> None:
        with pytest.raises(InvalidJudgmentError):
            JudgmentStore().record(self.record(1.5))

    def test_corrupt_file_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "judgments.jsonl"
        path.write_text('{"key": "k1"}\n', encoding="utf-8")
        with pytest.raises(InvalidJudgmentError):
            JudgmentStore(path)

    def test_stored_probability_out_of_range_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "judgments.jsonl"
        bad = {**self.record().__dict__, "probability": 7}
        path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
        with pytest.raises(InvalidJudgmentError):
            JudgmentStore(path)


class TestGathering:
    def test_new_judgments_are_fetched_once_and_then_replayed(self) -> None:
        store = JudgmentStore()
        source = ScriptedSource(TABLE)

        first = gather_judgments(
            [LEVY, FROGS],
            [TAXES, TREE_FROGS],
            store,
            model=MODEL,
            source=source,
            clock=fixed_clock,
        )
        assert first.judgments == TABLE
        assert (first.fetched, first.recorded) == (4, 0)
        assert first.missing == () and first.failures == ()
        assert len(source.calls) == 2  # one request per question

        replay = gather_judgments(
            [LEVY, FROGS], [TAXES, TREE_FROGS], store, model=MODEL, source=source
        )
        assert replay.judgments == TABLE
        assert (replay.fetched, replay.recorded) == (0, 4)
        assert len(source.calls) == 2  # nothing was asked again

    def test_replay_needs_no_source(self) -> None:
        store = JudgmentStore()
        gather_judgments(
            [LEVY], [TAXES], store, model=MODEL, source=ScriptedSource(TABLE)
        )
        replay = gather_judgments([LEVY], [TAXES], store, model=MODEL)
        assert replay.judgments == {("levy", TAXES.id): 0.97}

    def test_a_later_answer_never_replaces_a_recorded_one(self) -> None:
        store = JudgmentStore()
        gather_judgments(
            [LEVY], [TAXES], store, model=MODEL, source=ScriptedSource(TABLE)
        )
        drifted = ScriptedSource({("levy", TAXES.id): 0.955})
        again = gather_judgments([LEVY], [TAXES], store, model=MODEL, source=drifted)
        assert again.judgments == {("levy", TAXES.id): 0.97}
        assert drifted.calls == []

    def test_only_missing_categories_are_asked(self) -> None:
        store = JudgmentStore()
        source = ScriptedSource(TABLE)
        gather_judgments([LEVY], [TAXES], store, model=MODEL, source=source)
        gather_judgments([LEVY], [TAXES, TREE_FROGS], store, model=MODEL, source=source)
        assert source.calls == [("levy", (TAXES.id,)), ("levy", (TREE_FROGS.id,))]

    def test_one_category_text_from_many_voters_is_asked_once(self) -> None:
        source = ScriptedSource(TABLE)
        same_text = create_category("ALL things  taxes")
        gather_judgments(
            [LEVY], [TAXES, same_text], JudgmentStore(), model=MODEL, source=source
        )
        assert source.calls == [("levy", (TAXES.id,))]

    def test_categories_are_sent_in_batches(self) -> None:
        categories = [create_category(f"topic {index}") for index in range(5)]
        table = {("levy", category.id): 0.5 for category in categories}
        source = ScriptedSource(table)
        gather_judgments(
            [LEVY],
            categories,
            JudgmentStore(),
            model=MODEL,
            source=source,
            batch_size=2,
        )
        assert [len(ids) for _, ids in source.calls] == [2, 2, 1]

    def test_no_source_leaves_pairs_missing(self) -> None:
        report = gather_judgments([LEVY], [TAXES], JudgmentStore(), model=MODEL)
        assert report.judgments == {}
        assert report.missing == (("levy", TAXES.id),)

    def test_a_failed_request_fails_closed_without_stopping_the_rest(self) -> None:
        store = JudgmentStore()
        source = ScriptedSource(TABLE, fail_on=frozenset({"levy"}))
        report = gather_judgments(
            [LEVY, FROGS], [TAXES, TREE_FROGS], store, model=MODEL, source=source
        )

        assert set(report.missing) == {("levy", TAXES.id), ("levy", TREE_FROGS.id)}
        assert report.failures == ("levy: HTTP 529",)
        assert report.judgments == {
            ("frogs", TAXES.id): 0.04,
            ("frogs", TREE_FROGS.id): 0.92,
        }
        assert len(store) == 2

    def test_an_answer_from_another_model_is_not_recorded(self) -> None:
        store = JudgmentStore()
        source = ScriptedSource(TABLE, answered_by="jev-1.15.0")
        report = gather_judgments([LEVY], [TAXES], store, model=MODEL, source=source)
        assert report.judgments == {}
        assert report.missing == (("levy", TAXES.id),)
        assert len(store) == 0

    def test_source_must_ask_the_requested_model(self) -> None:
        with pytest.raises(ValueError):
            gather_judgments(
                [LEVY],
                [TAXES],
                JudgmentStore(),
                model=MODEL,
                source=ScriptedSource(TABLE, model="jev-1.13.0"),
            )

    def test_batch_size_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            gather_judgments(
                [LEVY], [TAXES], JudgmentStore(), model=MODEL, batch_size=0
            )


class TestGatheredJudgmentsDriveRouting:
    def test_resolution_reads_recorded_judgments(self) -> None:
        network = create_network([Person("voter"), Person("dana"), Person("sam")])
        network = add_delegation(network, "voter", TAXES, "dana")
        network = add_delegation(network, "voter", TREE_FROGS, "sam")
        store = JudgmentStore()
        gather_judgments(
            [LEVY, FROGS],
            network.categories.values(),
            store,
            model=MODEL,
            source=ScriptedSource(TABLE),
        )
        judgments = gather_judgments(
            [LEVY, FROGS], network.categories.values(), store, model=MODEL
        ).judgments

        assert (
            resolve_question(network, "levy", ["voter"], judgments).resolver_of("voter")
            == "dana"
        )
        assert (
            resolve_question(network, "frogs", ["voter"], judgments).resolver_of(
                "voter"
            )
            == "sam"
        )

    def test_without_judgments_the_voter_keeps_every_decision(self) -> None:
        network = create_network([Person("voter"), Person("dana")])
        network = add_delegation(network, "voter", TAXES, "dana")
        judgments = gather_judgments(
            [LEVY], network.categories.values(), JudgmentStore(), model=MODEL
        ).judgments
        assert (
            resolve_question(network, "levy", ["voter"], judgments).resolver_of("voter")
            == "voter"
        )
