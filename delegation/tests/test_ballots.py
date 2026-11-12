"""Tests for the ballot shapes a question can use and how each is counted."""

from __future__ import annotations

import pytest

from delegation import Question
from delegation.ballots import (
    BALLOT_TYPES,
    METHODS,
    InvalidChoiceError,
    ballot_for,
    choice_on,
    count,
    sincere_choice_for,
)
from voting import (
    ApprovalBallot,
    Candidate,
    IRVResult,
    RankedChoiceBallot,
    SingleChoiceBallot,
    random_tiebreak,
)

OPTIONS = (Candidate("a", "A"), Candidate("b", "B"), Candidate("c", "C"))
QUESTION = Question("q", "A choice", "Among three.", OPTIONS)


class TestBallotFor:
    def test_each_type_builds_its_own_ballot(self) -> None:
        single = ballot_for("single_choice", "v", ["b"], QUESTION)
        ranked = ballot_for("ranked", "v", ["c", "a", "b"], QUESTION)
        approval = ballot_for("approval", "v", ["c", "a"], QUESTION)
        assert isinstance(single, SingleChoiceBallot) and single.choice == "b"
        assert isinstance(ranked, RankedChoiceBallot)
        assert ranked.ranking == ["c", "a", "b"]
        assert isinstance(approval, ApprovalBallot) and approval.approvals == {"a", "c"}
        assert {single.voter_id, ranked.voter_id, approval.voter_id} == {"v"}

    @pytest.mark.parametrize("ballot_type", BALLOT_TYPES)
    def test_no_choice_is_an_abstention(self, ballot_type: str) -> None:
        ballot = ballot_for(ballot_type, "v", None, QUESTION)  # type: ignore[arg-type]
        assert choice_on(ballot, QUESTION) is None

    @pytest.mark.parametrize(
        ("ballot_type", "choice"),
        [
            ("single_choice", ["a", "b"]),
            ("single_choice", []),
            ("single_choice", ["z"]),
            ("ranked", ["a", "b"]),
            ("ranked", ["a", "a", "b"]),
            ("ranked", ["a", "b", "z"]),
            ("approval", []),
            ("approval", ["a", "a"]),
            ("approval", ["z"]),
        ],
    )
    def test_a_choice_that_does_not_fit_is_rejected(
        self, ballot_type: str, choice: list[str]
    ) -> None:
        with pytest.raises(InvalidChoiceError):
            ballot_for(ballot_type, "v", choice, QUESTION)  # type: ignore[arg-type]

    def test_a_choice_reads_back_as_it_was_given(self) -> None:
        assert choice_on(ballot_for("single_choice", "v", ["b"], QUESTION), QUESTION) == [
            "b"
        ]
        assert choice_on(
            ballot_for("ranked", "v", ["c", "a", "b"], QUESTION), QUESTION
        ) == ["c", "a", "b"]
        # Approvals come back in the question's option order.
        assert choice_on(
            ballot_for("approval", "v", ["c", "a"], QUESTION), QUESTION
        ) == ["a", "c"]


class TestSincereChoice:
    UTILITIES = {"a": 0.2, "b": 0.9, "c": -0.5}

    def test_a_single_choice_is_the_favourite(self) -> None:
        assert sincere_choice_for("single_choice", self.UTILITIES, QUESTION) == ["b"]

    def test_a_ranking_runs_from_most_to_least_wanted(self) -> None:
        assert sincere_choice_for("ranked", self.UTILITIES, QUESTION) == ["b", "a", "c"]

    def test_approvals_are_the_options_above_the_average(self) -> None:
        # The average is 0.2, so only b is above it.
        assert sincere_choice_for("approval", self.UTILITIES, QUESTION) == ["b"]
        assert sincere_choice_for(
            "approval", {"a": 0.8, "b": 0.9, "c": -0.5}, QUESTION
        ) == ["a", "b"]

    def test_ties_go_to_the_earlier_option(self) -> None:
        level = {"a": 0.0, "b": 0.0, "c": 0.0}
        assert sincere_choice_for("single_choice", level, QUESTION) == ["a"]
        assert sincere_choice_for("ranked", level, QUESTION) == ["a", "b", "c"]
        # Nothing is above the average, so the favourite alone is approved.
        assert sincere_choice_for("approval", level, QUESTION) == ["a"]


class TestCount:
    def ballots(self, ballot_type: str, choices: list[list[str] | None]) -> list[object]:
        return [
            ballot_for(ballot_type, f"v{index}", choice, QUESTION)  # type: ignore[arg-type]
            for index, choice in enumerate(choices)
        ]

    def test_plurality_counts_single_choices(self) -> None:
        ballots = self.ballots("single_choice", [["a"], ["b"], ["b"], None])
        result = count("single_choice", OPTIONS, ballots, random_tiebreak(0))  # type: ignore[arg-type]
        assert result.winners == ["b"]
        assert result.vote_counts == {"a": 1, "b": 2, "c": 0}
        assert result.abstentions == 1

    def test_instant_runoff_transfers_from_the_eliminated_option(self) -> None:
        ballots = self.ballots(
            "ranked",
            [
                ["a", "b", "c"],
                ["a", "b", "c"],
                ["b", "c", "a"],
                ["b", "c", "a"],
                ["c", "b", "a"],
            ],
        )
        result = count("ranked", OPTIONS, ballots, random_tiebreak(0))  # type: ignore[arg-type]
        assert isinstance(result, IRVResult)
        assert result.winners == ["b"]
        assert len(result.rounds) == 2
        assert result.rounds[0].eliminated == ["c"]

    def test_approval_counts_every_approval(self) -> None:
        ballots = self.ballots("approval", [["a", "b"], ["b"], ["b", "c"], None])
        result = count("approval", OPTIONS, ballots, random_tiebreak(0))  # type: ignore[arg-type]
        assert result.winners == ["b"]
        assert result.vote_counts == {"a": 1, "b": 3, "c": 1}

    def test_every_type_names_its_method(self) -> None:
        assert METHODS == {
            "single_choice": "plurality",
            "ranked": "irv",
            "approval": "approval",
        }
