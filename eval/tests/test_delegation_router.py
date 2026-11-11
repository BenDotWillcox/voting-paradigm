"""
Tests for the demo 5 router evaluation.

Judgments here come from hand-built tables, never from Jev. The tables are
an oracle (acceptable categories score high, everything else low) and
variants of it, so every metric has a known right answer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from delegation import CategoryId
from eval.delegation_router import (
    NONE_OPTION,
    ChoiceRecord,
    InvalidFixtureError,
    RepeatRecord,
    RouterEvalConfig,
    RouterFixture,
    Verdict,
    choice_options,
    judge_outcome,
    load_fixture,
    nested_pairs,
    plan,
    repeat_questions,
    score_choice,
    score_router,
    score_separation,
    summarize,
    summarize_nested,
    summarize_repeats,
    voter_cases,
)
from eval.delegation_router import (
    labelled_nesting,
    nested_outcomes_under_rule,
    ordered_pairs,
    score_nesting_detection,
)
from eval.run_delegation_router_eval import main

FIXTURE = load_fixture()
CONFIG = RouterEvalConfig()
CASES = voter_cases(FIXTURE, CONFIG)

Table = dict[tuple[str, CategoryId], float]


def table(narrow: float = 0.9, parent: float = 0.9, other: float = 0.1) -> Table:
    """Scores by label: squarely-inside narrow, other acceptable, and the rest."""
    scores: Table = {}
    for labelled in FIXTURE.questions:
        for entry in FIXTURE.categories:
            if entry.key in labelled.squarely_inside:
                score = narrow
            elif entry.key in labelled.acceptable:
                score = parent
            else:
                score = other
            scores[(labelled.question.id, entry.category.id)] = score
    return scores


class TestFixture:
    def test_pool_and_questions_have_the_expected_shape(self) -> None:
        assert len(FIXTURE.categories) == 30
        assert len(FIXTURE.questions) == 68
        nested = [entry for entry in FIXTURE.categories if entry.parent is not None]
        assert len(nested) == 14

    def test_every_nested_category_has_two_questions_squarely_inside_it(self) -> None:
        for entry in FIXTURE.categories:
            if entry.parent is None:
                continue
            inside = [q for q in FIXTURE.questions if entry.key in q.squarely_inside]
            assert len(inside) == 2, entry.key

    def test_every_parent_has_a_question_outside_its_nested_categories(self) -> None:
        # Otherwise a narrow category firing on its parent's questions
        # could never be caught.
        parents = {e.parent for e in FIXTURE.categories if e.parent is not None}
        for parent in parents:
            children = {e.key for e in FIXTURE.categories if e.parent == parent}
            broad_only = [
                q
                for q in FIXTURE.questions
                if parent in q.acceptable and not (children & q.acceptable)
            ]
            assert broad_only, parent

    def test_some_questions_belong_to_no_category(self) -> None:
        assert sum(not q.acceptable for q in FIXTURE.questions) == 3

    def test_category_text_fits_the_package_limit_and_is_distinct(self) -> None:
        ids = {entry.category.id for entry in FIXTURE.categories}
        assert len(ids) == len(FIXTURE.categories)

    def write(self, tmp_path: Path, **changes: object) -> Path:
        raw = json.loads(
            (
                Path(__file__).parents[1] / "fixtures" / "delegation_router_v1.json"
            ).read_text(encoding="utf-8")
        )
        raw.update(changes)
        path = tmp_path / "fixture.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        return path

    def question(self, **labels: object) -> list[dict[str, object]]:
        return [{"id": "x", "title": "T", "summary": "S", **labels}]

    @pytest.mark.parametrize(
        "labels",
        [
            {"acceptable": ["no_such_category"], "squarely_inside": []},
            {"acceptable": ["taxes"], "squarely_inside": ["sales_tax"]},
            {"acceptable": ["taxes"], "squarely_inside": ["taxes"]},
            {"acceptable": ["sales_tax"], "squarely_inside": ["sales_tax"]},
        ],
    )
    def test_inconsistent_labels_are_rejected(
        self, tmp_path: Path, labels: dict[str, object]
    ) -> None:
        with pytest.raises(InvalidFixtureError):
            load_fixture(self.write(tmp_path, questions=self.question(**labels)))

    def test_wrong_schema_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidFixtureError):
            load_fixture(self.write(tmp_path, schema="something else"))


class TestVoterCases:
    def test_cases_are_reproducible(self) -> None:
        assert voter_cases(FIXTURE, CONFIG) == CASES
        assert voter_cases(FIXTURE, RouterEvalConfig(seed=1)) != CASES

    def test_each_question_gets_its_share_of_lists(self) -> None:
        assert len(CASES) == len(FIXTURE.questions) * CONFIG.sets_per_question
        for case in CASES:
            assert 1 <= len(case.keys) <= CONFIG.max_set_size
            assert len(set(case.keys)) == len(case.keys)

    def test_half_the_lists_hold_an_acceptable_category_when_one_exists(self) -> None:
        for labelled in FIXTURE.questions:
            mine = [case for case in CASES if case.question == labelled.question.id]
            holding = sum(
                not labelled.acceptable.isdisjoint(case.keys) for case in mine
            )
            if labelled.acceptable:
                assert holding >= CONFIG.sets_per_question // 2
            else:
                assert holding == 0

    def test_both_kinds_of_case_are_well_represented(self) -> None:
        delegable = sum(
            not FIXTURE.labelled(case.question).acceptable.isdisjoint(case.keys)
            for case in CASES
        )
        assert 200 < delegable < len(CASES) - 150


class TestJudgingOutcomes:
    LEVY = FIXTURE.labelled("q25")  # acceptable: schools, taxes

    def test_verdicts(self) -> None:
        keys = ["taxes", "parks"]
        assert judge_outcome(self.LEVY, keys, "taxes") is Verdict.CORRECT_DELEGATION
        assert judge_outcome(self.LEVY, keys, "parks") is Verdict.FALSE_DELEGATION
        assert judge_outcome(self.LEVY, keys, None) is Verdict.FALSE_KEEP
        assert judge_outcome(self.LEVY, ["parks"], None) is Verdict.CORRECT_KEEP


class TestRouterScoring:
    def test_an_oracle_makes_no_errors(self) -> None:
        tally = score_router(FIXTURE, CASES, table(), 0.7)
        assert tally.false_delegations == 0
        assert tally.false_keeps == 0
        assert tally.unavailable == 0
        assert tally.correct_delegations == tally.delegable
        assert tally.correct_delegations + tally.correct_keeps == len(CASES)
        assert tally.false_delegation_rate == 0.0
        assert tally.false_keep_rate == 0.0

    def test_scores_below_the_threshold_are_all_kept(self) -> None:
        tally = score_router(FIXTURE, CASES, table(), 0.95)
        assert tally.delegated == 0
        assert tally.false_keeps == tally.delegable
        assert tally.coverage == 0.0
        assert tally.false_delegation_rate is None
        assert tally.false_keep_rate == 1.0

    def test_a_router_that_says_yes_to_everything_delegates_everything(self) -> None:
        everything = table(narrow=0.9, parent=0.9, other=0.9)
        tally = score_router(FIXTURE, CASES, everything, 0.7)
        assert tally.delegated == len(CASES)
        assert tally.false_keeps == 0
        assert tally.false_delegations > 150

    def test_missing_judgments_are_counted_apart(self) -> None:
        tally = score_router(FIXTURE, CASES, {}, 0.7)
        assert tally.unavailable == len(CASES)
        assert tally.scored == 0 and tally.coverage is None

    def test_tally_serialises(self) -> None:
        body = score_router(FIXTURE, CASES, table(), 0.7).as_json()
        assert body["cases"] == len(CASES)
        assert json.dumps(body)


class TestNestedCategories:
    def test_one_pair_per_squarely_inside_label(self) -> None:
        pairs = nested_pairs(FIXTURE, table())
        assert len(pairs) == 28
        assert {pair.parent for pair in pairs} == {
            "taxes",
            "environment",
            "schools",
            "housing",
            "transport",
            "safety",
            "elections",
            "labor",
        }

    def test_broad_category_outscoring_the_narrow_one_takes_the_vote(self) -> None:
        summary = summarize_nested(
            nested_pairs(FIXTURE, table(narrow=0.90, parent=0.95)), 0.7
        )
        assert summary["narrow_gets_the_vote"] == 0
        assert summary["parent_gets_the_vote"] == 28
        assert summary["both_clear_threshold"] == 28
        assert summary["narrow_higher_when_both_clear"] == 0
        assert summary["mean_narrow_minus_parent"] == pytest.approx(-0.05)

    def test_narrow_category_outscoring_its_parent_takes_the_vote(self) -> None:
        summary = summarize_nested(
            nested_pairs(FIXTURE, table(narrow=0.95, parent=0.80)), 0.7
        )
        assert summary["narrow_gets_the_vote"] == 28
        assert summary["parent_gets_the_vote"] == 0

    def test_exact_ties_are_counted_apart(self) -> None:
        summary = summarize_nested(nested_pairs(FIXTURE, table()), 0.7)
        assert summary["exact_ties_above_threshold"] == 28
        assert summary["narrow_gets_the_vote"] == summary["parent_gets_the_vote"] == 0

    def test_narrow_miss_falls_back_to_the_parent(self) -> None:
        summary = summarize_nested(
            nested_pairs(FIXTURE, table(narrow=0.5, parent=0.9)), 0.7
        )
        assert summary["parent_gets_the_vote"] == 28
        assert summary["narrow_clears_threshold"] == 0

    def test_both_below_the_threshold_stay_with_the_voter(self) -> None:
        summary = summarize_nested(
            nested_pairs(FIXTURE, table(narrow=0.5, parent=0.4)), 0.7
        )
        assert summary["voter_keeps_it"] == 28

    def test_pairs_without_both_judgments_are_skipped(self) -> None:
        assert nested_pairs(FIXTURE, {}) == ()


class TestScoreSeparation:
    def test_oracle_scores_separate_cleanly(self) -> None:
        separation = score_separation(FIXTURE, table(), 0.7)
        assert separation["acceptable"]["share_clearing_threshold"] == 1.0
        assert separation["not_acceptable"]["share_clearing_threshold"] == 0.0
        total = (
            separation["acceptable"]["pairs"] + separation["not_acceptable"]["pairs"]
        )
        assert total == 68 * 30


class TestSingleChoiceArm:
    def test_options_follow_the_voters_list_with_none_last(self) -> None:
        case = next(case for case in CASES if len(case.keys) >= 2)
        options = choice_options(FIXTURE, case)
        assert list(options)[:-1] == [FIXTURE.entry(k).category.text for k in case.keys]
        assert list(options)[-1] == NONE_OPTION
        assert all(description is None for description in options.values())

    def oracle_record(self, case: object) -> ChoiceRecord:
        from eval.delegation_router import VoterCase

        assert isinstance(case, VoterCase)
        acceptable = FIXTURE.labelled(case.question).acceptable
        choice = next((key for key in case.keys if key in acceptable), None)
        return ChoiceRecord(case.question, case.keys, choice, {})

    def test_an_oracle_makes_no_errors(self) -> None:
        tally = score_choice(FIXTURE, CASES, [self.oracle_record(c) for c in CASES])
        assert tally.false_delegations == tally.false_keeps == tally.unavailable == 0

    def test_always_choosing_none_keeps_everything(self) -> None:
        records = [ChoiceRecord(c.question, c.keys, None, {}) for c in CASES]
        tally = score_choice(FIXTURE, CASES, records)
        assert tally.delegated == 0
        assert tally.false_keeps == tally.delegable

    def test_cases_without_a_record_are_unavailable(self) -> None:
        assert score_choice(FIXTURE, CASES, []).unavailable == len(CASES)


class TestRepeatSpread:
    def test_the_repeat_sample_is_seeded(self) -> None:
        sample = repeat_questions(FIXTURE, CONFIG)
        assert len(sample) == CONFIG.repeat_questions
        assert sample == repeat_questions(FIXTURE, CONFIG)

    def test_spread_and_threshold_crossings(self) -> None:
        records = [
            RepeatRecord("q01", "taxes", (0.90, 0.90, 0.90, 0.90)),
            RepeatRecord("q01", "parks", (0.10, 0.11, 0.10, 0.12)),
            RepeatRecord("q01", "budget", (0.69, 0.70, 0.71, 0.70)),
        ]
        summary = summarize_repeats(records, 0.7)
        assert summary["judgments"] == 3
        assert summary["calls_each"] == 4
        assert summary["largest_spread"] == pytest.approx(0.02)
        assert summary["identical_every_time"] == 1
        assert summary["crossing_the_threshold"] == 1

    def test_no_records(self) -> None:
        summary = summarize_repeats([], 0.7)
        assert summary["judgments"] == 0
        assert summary["largest_spread"] is None


class TestSummaryAndPlan:
    def test_summary_holds_every_section_and_serialises(self) -> None:
        summary = summarize(FIXTURE, CONFIG, table(), [], [])
        assert summary["judgments"] == {"expected": 2040, "recorded": 2040}
        assert len(summary["router_by_threshold"]) == len(CONFIG.thresholds)
        assert summary["router_at_operating_threshold"]["threshold"] == 0.7
        assert json.dumps(summary)

    def test_plan_counts_requests_without_sending_any(self) -> None:
        planned = plan(FIXTURE, CONFIG)
        assert planned["judging"] == {
            "requests": 68,
            "judgments": 2040,
            "estimated_input_tokens": planned["judging"]["estimated_input_tokens"],
        }
        assert planned["single_choice_arm"]["requests"] == len(CASES)
        assert planned["repeat_spread"]["requests"] == 48
        assert planned["nesting"]["requests"] == 30
        assert planned["nesting"]["judgments"] == 30 * 29
        assert planned["total_requests"] == 68 + len(CASES) + 48 + 30
        assert 0 < planned["estimated_usd"] < 0.10


class TestCommand:
    def test_plan_prints_and_exits_cleanly(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["plan"]) == 0
        assert json.loads(capsys.readouterr().out)["total_requests"] > 0

    @pytest.mark.parametrize("command", ["smoke", "collect"])
    def test_paid_commands_refuse_to_run_without_live(self, command: str) -> None:
        with pytest.raises(SystemExit, match="--live"):
            main([command])


def containment(
    inside: float = 0.95, reverse: float = 0.05, other: float = 0.05
) -> dict[tuple[CategoryId, CategoryId], float]:
    """Containment probabilities by label: declared pairs, their reverses, the rest."""
    declared = labelled_nesting(FIXTURE)
    probabilities: dict[tuple[CategoryId, CategoryId], float] = {}
    for narrow, broad in ordered_pairs(FIXTURE):
        pair = (narrow.id, broad.id)
        if pair in declared:
            probabilities[pair] = inside
        elif (broad.id, narrow.id) in declared:
            probabilities[pair] = reverse
        else:
            probabilities[pair] = other
    return probabilities


class TestNestingRule:
    # The measured situation: the broad category outscores the narrow one.
    BROAD_AHEAD = table(narrow=0.81, parent=0.95)

    def test_fixture_declares_fourteen_nested_pairs_over_every_ordered_pair(
        self,
    ) -> None:
        assert len(labelled_nesting(FIXTURE)) == 14
        assert len(ordered_pairs(FIXTURE)) == 30 * 29

    def test_without_a_nesting_the_broad_category_takes_every_pair(self) -> None:
        outcome = nested_outcomes_under_rule(
            FIXTURE,
            nested_pairs(FIXTURE, self.BROAD_AHEAD),
            self.BROAD_AHEAD,
            0.7,
            frozenset(),
        )
        assert outcome["parent_gets_the_vote"] == 28
        assert outcome["narrow_gets_the_vote"] == 0

    def test_with_the_nesting_the_narrow_category_takes_every_pair(self) -> None:
        outcome = nested_outcomes_under_rule(
            FIXTURE,
            nested_pairs(FIXTURE, self.BROAD_AHEAD),
            self.BROAD_AHEAD,
            0.7,
            labelled_nesting(FIXTURE),
        )
        assert outcome["narrow_gets_the_vote"] == 28
        assert outcome["parent_gets_the_vote"] == 0

    def test_a_narrow_category_below_the_threshold_still_falls_back(self) -> None:
        scores = table(narrow=0.5, parent=0.95)
        outcome = nested_outcomes_under_rule(
            FIXTURE,
            nested_pairs(FIXTURE, scores),
            scores,
            0.7,
            labelled_nesting(FIXTURE),
        )
        assert outcome["parent_gets_the_vote"] == 28

    def test_the_rule_makes_no_new_errors_for_an_oracle(self) -> None:
        tally = score_router(FIXTURE, CASES, table(), 0.7, labelled_nesting(FIXTURE))
        assert tally.false_delegations == 0
        assert tally.false_keeps == 0

    def test_a_narrow_category_that_fires_wrongly_now_overrules_its_parent(
        self,
    ) -> None:
        # Every narrow category scores high on every question its parent is
        # acceptable for, including ones it is not about. Without the rule the
        # parent's equal score wins by list order at least some of the time;
        # with it, the narrow category always wins, so wrong delegations rise.
        scores = table()
        declared = labelled_nesting(FIXTURE)
        for labelled in FIXTURE.questions:
            for entry in FIXTURE.categories:
                if entry.parent in labelled.acceptable:
                    scores[(labelled.question.id, entry.category.id)] = 0.9
        plain = score_router(FIXTURE, CASES, scores, 0.7)
        ruled = score_router(FIXTURE, CASES, scores, 0.7, declared)
        assert ruled.false_delegations > plain.false_delegations


class TestNestingDetection:
    def test_clean_containment_recovers_the_declared_nesting(self) -> None:
        detection = score_nesting_detection(FIXTURE, containment(), 0.7)
        assert detection["ordered_pairs_judged"] == 870
        assert detection["labelled_pairs"] == 14
        assert detection["detected_pairs"] == 14
        assert detection["labelled_and_detected"] == 14
        assert detection["labelled_but_missed"] == []
        assert detection["detected_but_not_labelled"] == []

    def test_yes_both_ways_is_not_detected_as_nesting(self) -> None:
        detection = score_nesting_detection(FIXTURE, containment(reverse=0.9), 0.7)
        assert detection["detected_pairs"] == 0
        assert len(detection["labelled_but_missed"]) == 14

    def test_missed_and_extra_pairs_are_named(self) -> None:
        probabilities = containment()
        frogs = FIXTURE.entry("tree_frogs").category.id
        environment = FIXTURE.entry("environment").category.id
        parks = FIXTURE.entry("parks").category.id
        probabilities[(frogs, environment)] = 0.2
        probabilities[(parks, environment)] = 0.9
        detection = score_nesting_detection(FIXTURE, probabilities, 0.7)
        assert detection["labelled_but_missed"] == ["tree_frogs inside environment"]
        assert detection["detected_but_not_labelled"] == ["parks inside environment"]

    def test_no_containment_judgments_means_no_nesting(self) -> None:
        detection = score_nesting_detection(FIXTURE, {}, 0.7)
        assert detection["detected_pairs"] == 0

    def test_summary_reports_the_rule_under_both_nestings(self) -> None:
        scores = table(narrow=0.81, parent=0.95)
        summary = summarize(FIXTURE, CONFIG, scores, [], [], containment())
        with_rule = summary["nested_categories_with_rule"]
        assert with_rule["labelled_nesting"]["narrow_gets_the_vote"] == 28
        assert with_rule["detected_nesting"]["narrow_gets_the_vote"] == 28
        assert summary["nested_categories"]["parent_gets_the_vote"] == 28
        assert set(summary["router_with_rule"]) == {
            "labelled_nesting",
            "detected_nesting",
        }
        assert json.dumps(summary)

    def test_summary_without_containment_judgments_detects_nothing(self) -> None:
        summary = summarize(FIXTURE, CONFIG, table(narrow=0.81, parent=0.95), [], [])
        with_rule = summary["nested_categories_with_rule"]
        assert with_rule["detected_nesting"]["narrow_gets_the_vote"] == 0
        assert with_rule["labelled_nesting"]["narrow_gets_the_vote"] == 28


def test_fixture_type_is_exported() -> None:
    assert isinstance(FIXTURE, RouterFixture)
