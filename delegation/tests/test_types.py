"""Tests for categories, networks and ballot papers."""

from __future__ import annotations

import pytest

from delegation import (
    MAX_CATEGORY_LENGTH,
    Category,
    Delegation,
    InvalidBallotPaperError,
    InvalidCategoryError,
    InvalidNetworkError,
    Network,
    Person,
    Question,
    create_ballot_paper,
    create_category,
    create_network,
    normalize_category_text,
)
from voting import Candidate

from .helpers import cid, network_of


class TestCategory:
    def test_case_and_whitespace_do_not_change_identity(self) -> None:
        first = create_category("All things  taxes")
        second = create_category("  all things taxes ")
        assert first.id == second.id

    def test_text_is_kept_as_written_with_whitespace_collapsed(self) -> None:
        category = create_category("  The well-being of  tree frogs ")
        assert category.text == "The well-being of tree frogs"

    def test_different_wording_is_a_different_category(self) -> None:
        assert cid("taxes") != cid("taxation")

    def test_any_granularity_is_allowed(self) -> None:
        narrow = create_category("the well-being of tree frogs in the Amazon")
        broad = create_category("all things taxes")
        assert narrow.id != broad.id

    @pytest.mark.parametrize("text", ["", "   ", "\n\t"])
    def test_empty_text_is_rejected(self, text: str) -> None:
        with pytest.raises(InvalidCategoryError):
            create_category(text)

    def test_length_limit_is_inclusive(self) -> None:
        create_category("x" * MAX_CATEGORY_LENGTH)
        with pytest.raises(InvalidCategoryError):
            create_category("x" * (MAX_CATEGORY_LENGTH + 1))

    def test_length_is_measured_after_collapsing_whitespace(self) -> None:
        padded = "x" * MAX_CATEGORY_LENGTH + " " * 50
        assert normalize_category_text(padded) == "x" * MAX_CATEGORY_LENGTH


class TestNetwork:
    def test_delegations_keep_the_persons_category_list_order(self) -> None:
        network = network_of(
            ["a", "b", "c"],
            [("a", "taxes", "b"), ("b", "taxes", "c"), ("a", "schools", "c")],
        )
        assert [d.category for d in network.delegations_of("a")] == [
            cid("taxes"),
            cid("schools"),
        ]
        assert network.delegate_for("a", cid("schools")) == "c"
        assert network.delegate_for("a", cid("roads")) is None
        assert network.delegations_of("c") == ()

    def test_same_text_from_two_voters_is_one_category(self) -> None:
        network = network_of(
            ["a", "b", "c"], [("a", "Taxes", "c"), ("b", "taxes", "c")]
        )
        assert len(network.categories) == 1
        assert network.categories[cid("taxes")].text == "Taxes"

    def test_duplicate_person_is_rejected(self) -> None:
        with pytest.raises(InvalidNetworkError):
            create_network([Person("a"), Person("a")])

    def test_unknown_delegate_is_rejected(self) -> None:
        with pytest.raises(InvalidNetworkError):
            network_of(["a"], [("a", "taxes", "ghost")])

    def test_unknown_category_is_rejected(self) -> None:
        with pytest.raises(InvalidNetworkError):
            create_network(
                [Person("a"), Person("b")],
                [],
                [Delegation("a", "cat_missing", "b")],
            )

    def test_self_delegation_is_rejected(self) -> None:
        with pytest.raises(InvalidNetworkError):
            network_of(["a"], [("a", "taxes", "a")])

    def test_delegating_one_category_twice_is_rejected(self) -> None:
        with pytest.raises(InvalidNetworkError):
            network_of(["a", "b", "c"], [("a", "taxes", "b"), ("a", "taxes", "c")])

    def test_mismatched_ids_are_rejected(self) -> None:
        with pytest.raises(InvalidNetworkError):
            Network(persons={"a": Person("b")}, categories={})
        with pytest.raises(InvalidNetworkError):
            Network(persons={}, categories={"cat_x": Category("cat_y", "taxes")})

    def test_construction_does_not_reject_loops(self) -> None:
        # Loops are the creation checks' and the resolution rule's job.
        network = network_of(["a", "b"], [("a", "taxes", "b"), ("b", "taxes", "a")])
        assert len(network.delegations) == 2


class TestBallotPaper:
    def test_questions_keep_their_order(self) -> None:
        options = (Candidate("yes", "Yes"), Candidate("no", "No"))
        paper = create_ballot_paper(
            "city",
            [
                Question("q2", "Second", "", options),
                Question("q1", "First", "", options),
            ],
        )
        assert [question.id for question in paper.questions] == ["q2", "q1"]

    def test_empty_paper_is_rejected(self) -> None:
        with pytest.raises(InvalidBallotPaperError):
            create_ballot_paper("city", [])

    def test_repeated_question_id_is_rejected(self) -> None:
        options = (Candidate("yes", "Yes"),)
        with pytest.raises(InvalidBallotPaperError):
            create_ballot_paper(
                "city",
                [Question("q1", "A", "", options), Question("q1", "B", "", options)],
            )
