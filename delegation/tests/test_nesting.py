"""Tests for nested categories: the relation, the rule, and how it is gathered."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from delegation import (
    Category,
    CategoryId,
    InvalidJudgmentError,
    InvalidNetworkError,
    JudgmentUnavailable,
    NestingStore,
    Person,
    RouteOutcome,
    SourceAnswer,
    add_delegation,
    co_held_pairs,
    create_category,
    create_network,
    derive_nesting,
    gather_nesting,
    remove_delegation,
    resolve_question,
    route,
    with_nesting,
)
from delegation.nesting import nesting_instruction, nesting_key

from .helpers import QUESTION, cid, network_of, scores

MODEL = "jev-1.14.0"
ENVIRONMENT = create_category("the environment")
FROGS = create_category("tree frogs in the Amazon")
TAXES = create_category("all things taxes")
FROGS_IN_ENVIRONMENT = (FROGS.id, ENVIRONMENT.id)

# The broad category is listed first, the order least favourable to the
# narrow one.
VOTER = with_nesting(
    network_of(
        ["voter", "lee", "sam", "dana"],
        [
            ("voter", "the environment", "lee"),
            ("voter", "tree frogs in the Amazon", "sam"),
            ("voter", "all things taxes", "dana"),
        ],
    ),
    [FROGS_IN_ENVIRONMENT],
)


def judged(
    environment: float, frogs: float, taxes: float
) -> dict[tuple[str, CategoryId], float]:
    return scores(
        the_environment=environment,
        tree_frogs_in_the_Amazon=frogs,
        all_things_taxes=taxes,
    )


class TestNetworkNesting:
    def test_nesting_is_transitive(self) -> None:
        a, b, c = (create_category(text) for text in ("frogs", "wildlife", "nature"))
        network = create_network(
            [Person("p")], [a, b, c], nesting=[(a.id, b.id), (b.id, c.id)]
        )
        assert network.is_inside(a.id, b.id)
        assert network.is_inside(a.id, c.id)
        assert not network.is_inside(c.id, a.id)
        assert not network.is_inside(a.id, a.id)

    def test_no_nesting_by_default(self) -> None:
        network = network_of(["a", "b"], [("a", "taxes", "b")])
        assert network.nesting == frozenset()
        assert not network.is_inside(cid("taxes"), cid("taxes"))

    def test_unknown_category_is_rejected(self) -> None:
        with pytest.raises(InvalidNetworkError):
            create_network([Person("p")], [FROGS], nesting=[(FROGS.id, "cat_missing")])

    @pytest.mark.parametrize(
        "pairs",
        [
            [("a", "a")],
            [("a", "b"), ("b", "a")],
            [("a", "b"), ("b", "c"), ("c", "a")],
        ],
    )
    def test_nesting_that_loops_is_rejected(self, pairs: list[tuple[str, str]]) -> None:
        categories = {name: create_category(name) for name in "abc"}
        with pytest.raises(InvalidNetworkError):
            create_network(
                [Person("p")],
                categories.values(),
                nesting=[(categories[n].id, categories[b].id) for n, b in pairs],
            )

    def test_adding_and_removing_delegations_keeps_the_nesting(self) -> None:
        network = add_delegation(VOTER, "lee", TAXES, "dana")
        assert network.nesting == frozenset([FROGS_IN_ENVIRONMENT])
        network = remove_delegation(network, "lee", TAXES.id)
        assert network.nesting == frozenset([FROGS_IN_ENVIRONMENT])

    def test_with_nesting_drops_pairs_the_network_does_not_have(self) -> None:
        network = network_of(["a", "b"], [("a", "the environment", "b")])
        applied = with_nesting(network, [FROGS_IN_ENVIRONMENT])
        assert applied.nesting == frozenset()


class TestSpecificOverrulesGeneral:
    def test_narrow_category_wins_when_both_clear_even_with_a_lower_score(self) -> None:
        # The tree-frog questions in the router evaluation: 0.81 and 0.83
        # against 0.95 and 0.96 for the environment.
        decision = route(VOTER, "voter", QUESTION, judged(0.95, 0.81, 0.03))
        assert decision.delegate == "sam"
        assert decision.category == FROGS.id
        assert decision.set_aside == (ENVIRONMENT.id,)

    def test_without_nesting_the_higher_score_wins(self) -> None:
        plain = with_nesting(VOTER, [])
        decision = route(plain, "voter", QUESTION, judged(0.95, 0.81, 0.03))
        assert decision.delegate == "lee"
        assert decision.set_aside == ()

    def test_narrow_miss_falls_back_to_the_broad_category(self) -> None:
        decision = route(VOTER, "voter", QUESTION, judged(0.93, 0.45, 0.05))
        assert decision.delegate == "lee"
        assert decision.set_aside == ()

    def test_both_below_the_threshold_stay_with_the_voter(self) -> None:
        decision = route(VOTER, "voter", QUESTION, judged(0.60, 0.65, 0.05))
        assert decision.outcome is RouteOutcome.NONE_AVAILABLE
        assert decision.set_aside == ()

    def test_narrow_category_must_clear_the_threshold_itself(self) -> None:
        decision = route(VOTER, "voter", QUESTION, judged(0.99, 0.69, 0.0))
        assert decision.delegate == "lee"

    def test_an_unrelated_category_still_competes_on_score(self) -> None:
        # Environment gives way to tree frogs; taxes is unrelated to both
        # and has the highest score of what remains.
        decision = route(VOTER, "voter", QUESTION, judged(0.90, 0.80, 0.99))
        assert decision.delegate == "dana"
        assert decision.set_aside == (ENVIRONMENT.id,)

    def test_list_order_does_not_decide_a_nested_pair(self) -> None:
        narrow_first = with_nesting(
            network_of(
                ["voter", "lee", "sam"],
                [
                    ("voter", "tree frogs in the Amazon", "sam"),
                    ("voter", "the environment", "lee"),
                ],
            ),
            [FROGS_IN_ENVIRONMENT],
        )
        table = scores(the_environment=0.95, tree_frogs_in_the_Amazon=0.81)
        assert route(narrow_first, "voter", QUESTION, table).delegate == "sam"

    def test_a_narrow_category_the_voter_does_not_hold_changes_nothing(self) -> None:
        only_broad = with_nesting(
            network_of(
                ["voter", "lee", "other", "sam"],
                [
                    ("voter", "the environment", "lee"),
                    ("other", "tree frogs in the Amazon", "sam"),
                ],
            ),
            [FROGS_IN_ENVIRONMENT],
        )
        table = scores(the_environment=0.95, tree_frogs_in_the_Amazon=0.99)
        decision = route(only_broad, "voter", QUESTION, table)
        assert decision.delegate == "lee"
        assert decision.set_aside == ()

    def test_the_narrowest_of_a_chain_wins(self) -> None:
        wildlife = create_category("wildlife")
        network = with_nesting(
            network_of(
                ["voter", "lee", "sam", "kim"],
                [
                    ("voter", "the environment", "lee"),
                    ("voter", "wildlife", "kim"),
                    ("voter", "tree frogs in the Amazon", "sam"),
                ],
            ),
            [(FROGS.id, wildlife.id), (wildlife.id, ENVIRONMENT.id)],
        )
        table = scores(the_environment=0.99, wildlife=0.9, tree_frogs_in_the_Amazon=0.8)
        decision = route(network, "voter", QUESTION, table)
        assert decision.delegate == "sam"
        assert decision.set_aside == (ENVIRONMENT.id, wildlife.id)

    def test_two_narrow_categories_under_one_parent_compete_on_score(self) -> None:
        trees = create_category("street trees")
        network = with_nesting(
            network_of(
                ["voter", "lee", "sam", "kim"],
                [
                    ("voter", "the environment", "lee"),
                    ("voter", "tree frogs in the Amazon", "sam"),
                    ("voter", "street trees", "kim"),
                ],
            ),
            [FROGS_IN_ENVIRONMENT, (trees.id, ENVIRONMENT.id)],
        )
        table = scores(
            the_environment=0.99, tree_frogs_in_the_Amazon=0.75, street_trees=0.9
        )
        assert route(network, "voter", QUESTION, table).delegate == "kim"

    def test_resolution_uses_the_rule(self) -> None:
        resolution = resolve_question(
            VOTER, QUESTION, ["voter"], judged(0.95, 0.81, 0.03)
        )
        assert resolution.resolver_of("voter") == "sam"
        assert resolution.decisions["voter"].set_aside == (ENVIRONMENT.id,)


class TestDeriveNesting:
    def test_yes_one_way_and_no_the_other_is_nesting(self) -> None:
        nesting = derive_nesting({("frogs", "nature"): 0.95, ("nature", "frogs"): 0.05})
        assert nesting == frozenset([("frogs", "nature")])

    def test_yes_both_ways_is_two_wordings_not_nesting(self) -> None:
        assert (
            derive_nesting({("tax", "taxes"): 0.9, ("taxes", "tax"): 0.9})
            == frozenset()
        )

    def test_no_both_ways_is_not_nesting(self) -> None:
        assert derive_nesting(
            {("roads", "schools"): 0.1, ("schools", "roads"): 0.1}
        ) == (frozenset())

    def test_both_directions_must_have_been_judged(self) -> None:
        assert derive_nesting({("frogs", "nature"): 0.95}) == frozenset()

    def test_threshold_is_inclusive_and_adjustable(self) -> None:
        table = {("frogs", "nature"): 0.7, ("nature", "frogs"): 0.69}
        assert derive_nesting(table) == frozenset([("frogs", "nature")])
        assert derive_nesting(table, threshold=0.8) == frozenset()

    def test_a_pair_that_would_close_a_loop_is_left_out(self) -> None:
        table = {
            ("a", "b"): 0.95,
            ("b", "a"): 0.1,
            ("b", "c"): 0.90,
            ("c", "b"): 0.1,
            ("c", "a"): 0.80,
            ("a", "c"): 0.1,
        }
        assert derive_nesting(table) == frozenset([("a", "b"), ("b", "c")])

    def test_threshold_must_be_a_probability(self) -> None:
        with pytest.raises(InvalidJudgmentError):
            derive_nesting({}, threshold=1.5)


class TestCoHeldPairs:
    def test_only_categories_one_person_holds_together_are_paired(self) -> None:
        network = network_of(
            ["a", "b", "c"],
            [
                ("a", "the environment", "c"),
                ("a", "tree frogs in the Amazon", "c"),
                ("b", "all things taxes", "c"),
            ],
        )
        pairs = {(narrow.id, broad.id) for narrow, broad in co_held_pairs(network)}
        assert pairs == {(ENVIRONMENT.id, FROGS.id), (FROGS.id, ENVIRONMENT.id)}

    def test_a_pair_two_people_hold_appears_once(self) -> None:
        network = network_of(
            ["a", "b", "c"],
            [
                ("a", "the environment", "c"),
                ("a", "all things taxes", "c"),
                ("b", "all things taxes", "c"),
                ("b", "the environment", "c"),
            ],
        )
        assert len(co_held_pairs(network)) == 2

    def test_no_delegations_no_pairs(self) -> None:
        assert co_held_pairs(network_of(["a"])) == ()


class ScriptedNestingSource:
    """Answers containment from a table and remembers what it was asked."""

    def __init__(
        self,
        table: Mapping[tuple[CategoryId, CategoryId], float],
        *,
        model: str = MODEL,
        answered_by: str | None = None,
        fail: bool = False,
    ) -> None:
        self._table = table
        self._model = model
        self._answered_by = answered_by or model
        self._fail = fail
        self.calls: list[int] = []

    @property
    def model(self) -> str:
        return self._model

    def judge_nesting(
        self, pairs: Sequence[tuple[Category, Category]]
    ) -> Mapping[tuple[CategoryId, CategoryId], SourceAnswer]:
        self.calls.append(len(pairs))
        if self._fail:
            raise JudgmentUnavailable("HTTP 529")
        return {
            (narrow.id, broad.id): SourceAnswer(
                self._table[(narrow.id, broad.id)], self._answered_by
            )
            for narrow, broad in pairs
            if (narrow.id, broad.id) in self._table
        }


BOTH_WAYS = [(FROGS, ENVIRONMENT), (ENVIRONMENT, FROGS)]
TABLE = {(FROGS.id, ENVIRONMENT.id): 0.96, (ENVIRONMENT.id, FROGS.id): 0.03}


class TestGatherNesting:
    def test_judgments_are_fetched_once_then_replayed(self, tmp_path: Path) -> None:
        path = tmp_path / "nesting.jsonl"
        source = ScriptedNestingSource(TABLE)
        first = gather_nesting(
            BOTH_WAYS, NestingStore(path), model=MODEL, source=source
        )

        assert first.nesting == frozenset([FROGS_IN_ENVIRONMENT])
        assert first.probabilities == TABLE
        assert (first.fetched, first.recorded) == (2, 0)

        replay = gather_nesting(BOTH_WAYS, NestingStore(path), model=MODEL)
        assert replay.nesting == first.nesting
        assert (replay.fetched, replay.recorded) == (0, 2)
        assert source.calls == [2]

    def test_a_later_answer_never_replaces_a_recorded_one(self) -> None:
        store = NestingStore()
        gather_nesting(
            BOTH_WAYS, store, model=MODEL, source=ScriptedNestingSource(TABLE)
        )
        flipped = ScriptedNestingSource({key: 0.5 for key in TABLE})
        again = gather_nesting(BOTH_WAYS, store, model=MODEL, source=flipped)
        assert again.probabilities == TABLE
        assert flipped.calls == []

    def test_without_a_source_nothing_is_nested(self) -> None:
        report = gather_nesting(BOTH_WAYS, NestingStore(), model=MODEL)
        assert report.nesting == frozenset()
        assert set(report.missing) == set(TABLE)

    def test_a_failed_request_leaves_pairs_unnested(self) -> None:
        store = NestingStore()
        report = gather_nesting(
            BOTH_WAYS,
            store,
            model=MODEL,
            source=ScriptedNestingSource(TABLE, fail=True),
        )
        assert report.nesting == frozenset()
        assert report.failures == ("HTTP 529",)
        assert len(store) == 0

    def test_an_answer_from_another_model_is_not_recorded(self) -> None:
        store = NestingStore()
        source = ScriptedNestingSource(TABLE, answered_by="jev-1.15.0")
        report = gather_nesting(BOTH_WAYS, store, model=MODEL, source=source)
        assert report.nesting == frozenset() and len(store) == 0

    def test_pairs_are_sent_in_batches_and_self_pairs_are_skipped(self) -> None:
        source = ScriptedNestingSource(TABLE)
        gather_nesting(
            BOTH_WAYS + [(FROGS, FROGS)],
            NestingStore(),
            model=MODEL,
            source=source,
            batch_size=1,
        )
        assert source.calls == [1, 1]

    def test_source_must_ask_the_requested_model(self) -> None:
        with pytest.raises(ValueError):
            gather_nesting(
                BOTH_WAYS,
                NestingStore(),
                model=MODEL,
                source=ScriptedNestingSource(TABLE, model="jev-1.13.0"),
            )

    def test_gathered_nesting_changes_who_gets_the_vote(self) -> None:
        plain = with_nesting(VOTER, [])
        report = gather_nesting(
            co_held_pairs(plain),
            NestingStore(),
            model=MODEL,
            source=ScriptedNestingSource(
                {
                    **TABLE,
                    (TAXES.id, ENVIRONMENT.id): 0.02,
                    (ENVIRONMENT.id, TAXES.id): 0.02,
                    (TAXES.id, FROGS.id): 0.01,
                    (FROGS.id, TAXES.id): 0.01,
                }
            ),
        )
        table = judged(0.95, 0.81, 0.03)
        assert route(plain, "voter", QUESTION, table).delegate == "lee"
        nested = with_nesting(plain, report.nesting)
        assert route(nested, "voter", QUESTION, table).delegate == "sam"


class TestWhatIsAsked:
    def test_instruction_names_both_topics_in_order(self) -> None:
        instruction = nesting_instruction(FROGS, ENVIRONMENT)
        assert "Topic A: tree frogs in the Amazon." in instruction
        assert "Topic B: the environment." in instruction

    def test_key_depends_on_model_and_direction(self) -> None:
        key = nesting_key(MODEL, FROGS, ENVIRONMENT)
        assert key == nesting_key(MODEL, FROGS, ENVIRONMENT)
        assert key != nesting_key(MODEL, ENVIRONMENT, FROGS)
        assert key != nesting_key("jev-1.13.0", FROGS, ENVIRONMENT)
