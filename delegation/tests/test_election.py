"""Tests for election processing: eligibility, vote copying and tallies."""

from __future__ import annotations

import random

import pytest

from delegation import (
    BallotPaper,
    Person,
    Question,
    create_ballot_paper,
    create_category,
    create_network,
    delegated_ballots,
    direct_ballots,
    eligible_voters,
    resolve_ballot_paper,
    resolve_question,
    tally_question,
    winners_differ,
)
from voting import (
    Candidate,
    ElectionResult,
    RankedChoiceBallot,
    SingleChoiceBallot,
    create_ranked_choice_ballot,
    create_single_choice_ballot,
    random_tiebreak,
    resolve_borda,
    resolve_plurality,
)

from .helpers import CITY, QUESTION, cid, network_of, random_scenario, scores

YES_NO = (Candidate("yes", "Yes"), Candidate("no", "No"))
MEASURE = Question(QUESTION, "A measure", "A yes or no question.", YES_NO)
TIEBREAK_SEED = 7


def plurality(
    candidates: list[Candidate], ballots: list[SingleChoiceBallot]
) -> ElectionResult:
    """Plurality with a fresh seeded tiebreak, so equal tallies tie-break alike."""
    return resolve_plurality(candidates, ballots, random_tiebreak(TIEBREAK_SEED))


def abstain(voter: str) -> SingleChoiceBallot:
    return create_single_choice_ballot(voter, None)


def choices(**by_voter: str) -> dict[str, SingleChoiceBallot]:
    return {
        voter: create_single_choice_ballot(voter, choice)
        for voter, choice in by_voter.items()
    }


class TestEligibility:
    def test_only_residents_originate_a_vote(self) -> None:
        network = create_network(
            [
                Person("b", frozenset({CITY})),
                Person("a", frozenset({CITY, "county"})),
                Person("c", frozenset({"county"})),
                Person("d"),
            ]
        )
        assert eligible_voters(network, CITY) == ("a", "b")
        assert eligible_voters(network, "county") == ("a", "c")
        assert eligible_voters(network, "elsewhere") == ()


class TestVoteCopying:
    def test_each_voter_gets_a_copy_of_their_resolvers_ballot(self) -> None:
        network = network_of(["a", "b", "c"], [("a", "taxes", "b")])
        resolution = resolve_question(
            network, QUESTION, ["a", "b", "c"], scores(taxes=0.9)
        )
        ballots = delegated_ballots(resolution, choices(b="yes", c="no"), abstain)

        assert [(ballot.voter_id, ballot.choice) for ballot in ballots] == [
            ("a", "yes"),
            ("b", "yes"),
            ("c", "no"),
        ]

    def test_delegators_own_ballot_is_not_used(self) -> None:
        network = network_of(["a", "b"], [("a", "taxes", "b")])
        resolution = resolve_question(network, QUESTION, ["a", "b"], scores(taxes=0.9))
        ballots = delegated_ballots(resolution, choices(a="no", b="yes"), abstain)
        assert [ballot.choice for ballot in ballots] == ["yes", "yes"]

    def test_outside_resolver_answers_but_has_no_vote_of_their_own(self) -> None:
        network = network_of(
            ["a", "b"],
            [("a", "taxes", "expert"), ("b", "taxes", "expert")],
            outsiders=["expert"],
        )
        resolution = resolve_question(
            network, QUESTION, eligible_voters(network, CITY), scores(taxes=0.9)
        )
        ballots = delegated_ballots(resolution, choices(expert="yes"), abstain)

        assert [ballot.voter_id for ballot in ballots] == ["a", "b"]
        assert all(ballot.choice == "yes" for ballot in ballots)

    def test_resolver_who_casts_nothing_turns_held_votes_into_abstentions(self) -> None:
        network = network_of(["a", "b", "c"], [("a", "taxes", "b")])
        resolution = resolve_question(
            network, QUESTION, ["a", "b", "c"], scores(taxes=0.9)
        )
        tally = tally_question(
            MEASURE, resolution, choices(c="no"), abstention=abstain, method=plurality
        )

        assert tally.result.abstentions == 2
        assert tally.result.total_ballots == 3
        assert tally.result.winners == ["no"]

    def test_copies_are_independent_of_the_original(self) -> None:
        options = ["x", "y", "z"]
        network = network_of(["a", "b"], [("a", "taxes", "b")])
        resolution = resolve_question(network, QUESTION, ["a", "b"], scores(taxes=0.9))
        original = create_ranked_choice_ballot("b", ["y", "x", "z"], options)

        def no_ranking(voter: str) -> RankedChoiceBallot:
            return create_ranked_choice_ballot(voter)

        copies = delegated_ballots(resolution, {"b": original}, no_ranking)
        copies[0].ranking.reverse()

        assert original.ranking == ["y", "x", "z"]
        assert copies[1].ranking == ["y", "x", "z"]
        assert copies[1] is not original


class TestTally:
    def test_delegation_can_change_the_winner(self) -> None:
        # Directly, "no" wins 3-2. A hands the question to E, who votes
        # "yes", and "yes" wins 3-2.
        network = network_of(["a", "b", "c", "d", "e"], [("a", "taxes", "e")])
        voters = eligible_voters(network, CITY)
        cast = choices(a="no", b="no", c="no", d="yes", e="yes")
        resolution = resolve_question(network, QUESTION, voters, scores(taxes=0.9))

        direct = plurality(list(YES_NO), direct_ballots(voters, cast, abstain))
        delegated = tally_question(
            MEASURE, resolution, cast, abstention=abstain, method=plurality
        )

        assert direct.winners == ["no"]
        assert delegated.result.winners == ["yes"]
        assert delegated.result.vote_counts == {"yes": 3, "no": 2}
        assert winners_differ(direct, delegated.result)

    def test_ranked_ballots_are_copied_and_tallied(self) -> None:
        options = (Candidate("x", "X"), Candidate("y", "Y"), Candidate("z", "Z"))
        ids = [option.id for option in options]
        question = Question(QUESTION, "A race", "Rank the options.", options)
        network = network_of(
            ["a", "b", "c"], [("a", "taxes", "c"), ("b", "taxes", "c")]
        )
        resolution = resolve_question(
            network, QUESTION, ["a", "b", "c"], scores(taxes=0.9)
        )
        cast = {
            "a": create_ranked_choice_ballot("a", ["x", "y", "z"], ids),
            "b": create_ranked_choice_ballot("b", ["x", "z", "y"], ids),
            "c": create_ranked_choice_ballot("c", ["z", "y", "x"], ids),
        }

        tally = tally_question(
            question,
            resolution,
            cast,
            abstention=lambda voter: create_ranked_choice_ballot(voter),
            method=lambda candidates, ballots: resolve_borda(
                candidates, ballots, random_tiebreak(TIEBREAK_SEED)
            ),
        )

        assert [ballot.ranking for ballot in tally.ballots] == [["z", "y", "x"]] * 3
        assert tally.result.winners == ["z"]

    def test_resolution_for_another_question_is_rejected(self) -> None:
        resolution = resolve_question(network_of(["a"]), "another question", ["a"], {})
        with pytest.raises(ValueError):
            tally_question(
                MEASURE, resolution, {}, abstention=abstain, method=plurality
            )

    @pytest.mark.parametrize("seed", range(100))
    def test_without_delegations_the_tally_is_the_direct_tally(self, seed: int) -> None:
        scenario = random_scenario(seed)
        rng = random.Random(seed)
        network = create_network(scenario.network.persons.values())
        cast = choices(
            **{voter: rng.choice(["yes", "no"]) for voter in scenario.voters}
        )

        resolution = resolve_question(network, QUESTION, scenario.voters, {})
        delegated = delegated_ballots(resolution, cast, abstain)
        direct = direct_ballots(scenario.voters, cast, abstain)

        assert delegated == direct
        assert plurality(list(YES_NO), delegated) == plurality(list(YES_NO), direct)

    @pytest.mark.parametrize("seed", range(100))
    def test_copying_ballots_equals_weighting_resolvers(self, seed: int) -> None:
        scenario = random_scenario(seed)
        rng = random.Random(seed)
        cast = choices(
            **{
                person: rng.choice(["yes", "no"])
                for person in scenario.network.persons
                if rng.random() < 0.9
            }
        )
        resolution = resolve_question(
            scenario.network,
            QUESTION,
            scenario.voters,
            scenario.judgments,
            direct_voters=scenario.direct_voters,
        )
        tally = tally_question(
            MEASURE, resolution, cast, abstention=abstain, method=plurality
        )

        weighted = {"yes": 0, "no": 0}
        silent = 0
        for resolver, weight in resolution.weights().items():
            if resolver in cast:
                choice = cast[resolver].choice
                assert choice is not None
                weighted[choice] += weight
            else:
                silent += weight

        assert tally.result.vote_counts == weighted
        assert tally.result.abstentions == silent
        assert tally.result.total_ballots == len(scenario.voters)
        assert [ballot.voter_id for ballot in tally.ballots] == sorted(scenario.voters)


class TestBallotPaper:
    TAXES = create_category("all things taxes")
    FROGS = create_category("the well-being of tree frogs in the Amazon")

    def paper_and_judgments(
        self,
    ) -> tuple[BallotPaper, dict[tuple[str, str], float]]:
        paper = create_ballot_paper(
            CITY,
            [
                Question("levy", "Property tax levy", "", YES_NO),
                Question("frogs", "Amphibian habitat fund", "", YES_NO),
                Question("school", "School construction bond", "", YES_NO),
            ],
        )
        judgments = {
            ("levy", self.TAXES.id): 0.97,
            ("levy", self.FROGS.id): 0.01,
            ("frogs", self.TAXES.id): 0.04,
            ("frogs", self.FROGS.id): 0.92,
            ("school", self.TAXES.id): 0.30,
            ("school", self.FROGS.id): 0.01,
        }
        return paper, judgments

    def test_one_voters_questions_fan_out_to_different_resolvers(self) -> None:
        network = network_of(
            ["voter"],
            [
                ("voter", "all things taxes", "dana"),
                ("voter", "the well-being of tree frogs in the Amazon", "sam"),
            ],
            outsiders=["dana", "sam"],
        )
        paper, judgments = self.paper_and_judgments()
        resolutions = resolve_ballot_paper(network, paper, judgments)

        assert list(resolutions) == ["levy", "frogs", "school"]
        assert resolutions["levy"].resolver_of("voter") == "dana"
        assert resolutions["frogs"].resolver_of("voter") == "sam"
        assert resolutions["school"].resolver_of("voter") == "voter"
        assert resolutions["levy"].decisions["voter"].category == cid(
            "all things taxes"
        )

    def test_direct_votes_apply_per_question(self) -> None:
        network = network_of(
            ["voter"], [("voter", "all things taxes", "dana")], outsiders=["dana"]
        )
        paper, judgments = self.paper_and_judgments()
        judgments = {
            key: value for key, value in judgments.items() if key[1] == self.TAXES.id
        }
        resolutions = resolve_ballot_paper(
            network, paper, judgments, direct_voters={"levy": {"voter"}}
        )

        assert resolutions["levy"].resolver_of("voter") == "voter"

    def test_only_residents_of_the_jurisdiction_are_issued_the_paper(self) -> None:
        network = create_network(
            [Person("in", frozenset({CITY})), Person("out", frozenset({"county"}))]
        )
        paper, judgments = self.paper_and_judgments()
        resolutions = resolve_ballot_paper(network, paper, judgments)
        assert resolutions["levy"].voters == ("in",)
