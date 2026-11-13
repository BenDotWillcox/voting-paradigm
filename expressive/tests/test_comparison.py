"""One electorate's individual curves, binary compression, and exact aggregation."""

from collections import Counter
from dataclasses import asdict, replace
from hashlib import sha256
import json
import math
import random

import pytest

from expressive.comparison import (
    AUTHORED_SCENARIOS, CANDIDATES, COMPARISON_SCENARIOS, ELECTORATE_SEED, PROPOSAL, SCORE_TIE_TOLERANCE, STATUS_QUO,
    ComparisonElectorate, ComparisonVoter, aggregate_electorate, compare_ballots,
    compare_scores, curve_vote, prepared_voters, scenario_voters, _sample_ballot,
)
from expressive.scalar import ScalarBallot, evaluate_scalar


def ballot() -> ScalarBallot:
    return ScalarBallot(6, 2, 1.5, 2, 10)


def electorate(*voters: ComparisonVoter) -> ComparisonElectorate:
    return ComparisonElectorate("test", "Test", "Authored test fixture", 0, voters)


def test_seeded_fixture_is_reproducible_and_varied_without_global_rng_effects() -> None:
    first = prepared_voters()
    state = random.getstate()
    prepared_voters.cache_clear()
    assert prepared_voters() == first
    assert random.getstate() == state
    assert len(first) == len({voter.id for voter in first}) == 99
    assert len({voter.ballot for voter in first}) == 99
    assert len({voter.ballot.ideal for voter in first}) > 90
    assert len({voter.ballot.lower_half_width for voter in first}) > 90
    assert len({voter.ballot.upper_half_width for voter in first}) > 90
    assert len({(voter.ballot.approval_min, voter.ballot.approval_max) for voter in first}) > 60
    assert min(voter.ballot.ideal for voter in first) < 2
    assert max(voter.ballot.ideal for voter in first) > 9
    assert all(voter.ballot.lower_half_width != voter.ballot.upper_half_width for voter in first)
    # Many distinct curves compress to the same binary choice; equal scores remain explicit.
    counts = Counter(voter.binary_vote for voter in first)
    assert counts["yes"] > 10 and counts["no"] > 10 and counts["abstain"] > 0
    for voter in first:
        assert voter.status_quo_score == evaluate_scalar(voter.ballot, STATUS_QUO).score
        assert voter.proposal_score == evaluate_scalar(voter.ballot, PROPOSAL).score
        assert voter.binary_vote == voter.curve_vote == curve_vote(voter.ballot)


def test_user_is_preserved_and_changes_do_not_regenerate_other_99_voters() -> None:
    original_ballot = ballot()
    first = compare_ballots(original_ballot, "yes")
    repeated = compare_ballots(original_ballot, "yes")
    changed = compare_ballots(ScalarBallot(99, 1, 2, 98, 100), "no")
    assert first == repeated
    assert first.electorate.id == "scalar-electorate-v1"
    assert first.electorate.seed == ELECTORATE_SEED
    assert len(first.electorate.voters) == 100
    assert first.electorate.voters[:-1] == changed.electorate.voters[:-1]
    user = first.electorate.voters[-1]
    assert user.id == "you" and user.ballot is original_ballot
    assert user.binary_vote == "yes" and user.curve_vote == "no"
    assert changed.binary.yes == first.binary.yes - 1
    assert changed.binary.no == first.binary.no + 1
    assert changed.binary.abstain == first.binary.abstain
    assert original_ballot == ballot()


def test_default_prepared_fixture_is_unchanged() -> None:
    # Captured before adding scenarios: fixture identity, seed, curves and votes
    # must retain their existing meaning for older callers and saved examples.
    inputs = [{"id": voter.id, "label": voter.label, "ballot": asdict(voter.ballot), "binary_vote": voter.binary_vote}
              for voter in prepared_voters()]
    # Hash the authored inputs, not platform-sensitive last bits from math.exp.
    serialized = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
    assert sha256(serialized.encode()).hexdigest() == "d9cf39ab9cf48cbc02472f827264b5ab7e2fa3666d3858c11486c6ab4fb8c6a8"
    assert compare_ballots(ballot(), "no") == compare_ballots(ballot(), "no", "prepared")


@pytest.mark.parametrize("scenario", COMPARISON_SCENARIOS)
def test_scenarios_have_fixed_99_voters_without_global_rng_effects(scenario: str) -> None:
    state = random.getstate()
    first = scenario_voters(scenario)
    scenario_voters.cache_clear()
    assert scenario_voters(scenario) == first
    assert random.getstate() == state
    assert len(first) == len({voter.id for voter in first}) == 99
    assert len({voter.ballot for voter in first}) == 99
    assert all(voter.binary_vote == voter.curve_vote == curve_vote(voter.ballot) for voter in first)
    initial = compare_ballots(ballot(), "yes", scenario)
    assert initial == compare_ballots(ballot(), "yes", scenario)
    assert initial.electorate.voters[:-1] == first
    if scenario != "prepared":
        assert initial.electorate.id == f"scalar-electorate-{scenario}-v2"
        assert initial.electorate.seed == AUTHORED_SCENARIOS[scenario].seed > 0
        assert len({voter.ballot.ideal for voter in first}) > 90
        assert len({voter.ballot.lower_half_width for voter in first}) > 90
        assert len({voter.ballot.upper_half_width for voter in first}) > 90
        assert len({voter.ballot.approval_min for voter in first}) > 70
        assert len({voter.ballot.approval_max for voter in first}) > 70
        assert sum(voter.ballot.lower_half_width != voter.ballot.upper_half_width for voter in first) > 90


def test_scenario_seeds_are_distinct_and_drive_the_generated_curves(monkeypatch: pytest.MonkeyPatch) -> None:
    seeds = [ELECTORATE_SEED, *(fixture.seed for fixture in AUTHORED_SCENARIOS.values())]
    assert len(set(seeds)) == 4
    for scenario, fixture in AUTHORED_SCENARIOS.items():
        original = scenario_voters(scenario)
        with monkeypatch.context() as context:
            context.setitem(AUTHORED_SCENARIOS, scenario, replace(fixture, seed=fixture.seed + 100))
            scenario_voters.cache_clear()
            assert scenario_voters(scenario) != original
        scenario_voters.cache_clear()
        assert scenario_voters(scenario) == original


def test_each_themed_cohort_has_visible_internal_variation() -> None:
    groups = [
        (scenario_voters("broad-agreement"), 1.0),
        (scenario_voters("polarized")[:49], 1.0),
        (scenario_voters("polarized")[49:], 1.0),
        (scenario_voters("intense-minority")[:65], 0.45),
        (scenario_voters("intense-minority")[65:], 0.15),
    ]
    for voters, ideal_span in groups:
        assert max(voter.ballot.ideal for voter in voters) - min(voter.ballot.ideal for voter in voters) > ideal_span
        for field in ("ideal", "lower_half_width", "upper_half_width", "approval_min", "approval_max"):
            assert len({getattr(voter.ballot, field) for voter in voters}) > len(voters) / 2


def test_sample_cache_retains_all_four_backgrounds_when_switching_scenarios() -> None:
    _sample_ballot.cache_clear()
    for scenario in COMPARISON_SCENARIOS:
        compare_ballots(ballot(), "no", scenario)
    warmed = _sample_ballot.cache_info()
    assert warmed.currsize >= 4 * 99
    assert warmed.maxsize <= 512  # Keep storage bounded, including submitted curves.
    for scenario in COMPARISON_SCENARIOS:
        compare_ballots(ballot(), "no", scenario)
    revisited = _sample_ballot.cache_info()
    assert revisited.misses == warmed.misses
    assert revisited.hits == warmed.hits + 400


@pytest.mark.parametrize("scenario", COMPARISON_SCENARIOS)
@pytest.mark.parametrize("ideal", [0, 100])
def test_scenarios_preserve_extreme_user_curves_and_their_explicit_binary_votes(scenario: str, ideal: float) -> None:
    submitted = ScalarBallot(ideal, 1, 1, ideal, ideal)
    original = compare_ballots(ballot(), "no", scenario)
    result = compare_ballots(submitted, "yes", scenario)
    user = result.electorate.voters[-1]
    assert len(result.electorate.voters) == 100
    assert result.electorate.voters[:-1] == original.electorate.voters[:-1]
    assert user.id == "you" and user.ballot is submitted
    assert user.binary_vote == "yes" and user.curve_vote == "abstain"
    assert result.binary.yes == original.binary.yes + 1
    assert result.binary.no == original.binary.no - 1
    point = next(point for point in result.points if point.rate == ideal)
    assert point.user_score == 1 and point.user_approved


@pytest.mark.parametrize("scenario", COMPARISON_SCENARIOS)
def test_every_aggregate_point_reconciles_to_the_same_individual_ballots(scenario: str) -> None:
    result = compare_ballots(ballot(), "no", scenario)
    voters = result.electorate.voters
    counts = Counter(voter.binary_vote for voter in voters)
    assert (result.binary.yes, result.binary.no, result.binary.abstain) == (
        counts["yes"], counts["no"], counts["abstain"],
    )
    assert result.binary.passed == (counts["yes"] > counts["no"])
    assert result.binary.outcome_rate == (PROPOSAL if result.binary.passed else STATUS_QUO)
    baseline_scores = [evaluate_scalar(voter.ballot, result.binary.outcome_rate).score for voter in voters]
    assert tuple(point.rate for point in result.points) == CANDIDATES
    for point in result.points:
        evaluations = [evaluate_scalar(voter.ballot, point.rate) for voter in voters]
        comparisons = [compare_scores(item.score, baseline) for item, baseline in zip(evaluations, baseline_scores)]
        assert point.mean_score == math.fsum(item.score for item in evaluations) / 100
        assert point.approval_count == sum(item.approved for item in evaluations)
        assert (point.user_score, point.user_approved) == (evaluations[-1].score, evaluations[-1].approved)
        assert (point.prefer_this, point.prefer_binary, point.indifferent) == (
            comparisons.count(1), comparisons.count(-1), comparisons.count(0),
        )
        assert point.prefer_this + point.prefer_binary + point.indifferent == 100
    by_rate = {point.rate: point for point in result.points}
    assert result.pair.status_quo_mean == by_rate[STATUS_QUO].mean_score
    assert result.pair.proposal_mean == by_rate[PROPOSAL].mean_score
    assert result.pair.status_quo_mean == math.fsum(voter.status_quo_score for voter in voters) / 100
    assert result.pair.proposal_mean == math.fsum(voter.proposal_score for voter in voters) / 100
    maximum_pair_score = max(result.pair.status_quo_mean, result.pair.proposal_mean)
    assert set(result.pair.winner_rates) == {
        rate for rate in (STATUS_QUO, PROPOSAL)
        if compare_scores(by_rate[rate].mean_score, maximum_pair_score) == 0
    }
    assert result.max_mean_score == max(point.mean_score for point in result.points)
    assert result.winner_rates == tuple(
        point.rate for point in result.points if compare_scores(point.mean_score, result.max_mean_score) == 0
    )
    assert by_rate[result.binary.outcome_rate].indifferent == 100


def test_authored_scenarios_have_distinct_interpretable_baseline_outcomes() -> None:
    # This reference user approves the whole domain and prefers the status quo.
    # The UI must calculate from the actual user, not hard-code these examples.
    user = ScalarBallot(STATUS_QUO, 2, 2, 0, 100)
    broad = compare_ballots(user, "no", "broad-agreement")
    assert broad.binary.yes > broad.binary.no
    broad_winners = [point for point in broad.points if point.rate in broad.winner_rates]
    binary_score = next(point.mean_score for point in broad.points if point.rate == broad.binary.outcome_rate)
    assert all(abs(point.rate - broad.binary.outcome_rate) <= 0.2 for point in broad_winners)
    assert all(point.approval_count == 100 and point.mean_score > 0.95 for point in broad_winners)
    assert broad.max_mean_score - binary_score < 0.01

    polarized = compare_ballots(user, "no", "polarized")
    assert (polarized.binary.yes, polarized.binary.no, polarized.binary.abstain) == (49, 51, 0)
    assert polarized.binary.outcome_rate == STATUS_QUO
    polarized_winners = [point for point in polarized.points if point.rate in polarized.winner_rates]
    assert all(point.rate < 3.8 or point.rate > 5.2 for point in polarized_winners)
    assert all(point.approval_count <= 51 for point in polarized_winners)
    assert max(voter.ballot.approval_max for voter in polarized.electorate.voters[:49]) < min(
        voter.ballot.approval_min for voter in polarized.electorate.voters[49:99]
    )
    # Averaging individual curves does not guarantee an acceptable middle.
    middle = next(point for point in polarized.points if point.rate == 4.5)
    assert middle.approval_count < 20 and middle.mean_score < 0.05

    minority = compare_ballots(user, "no", "intense-minority")
    assert (minority.binary.yes, minority.binary.no, minority.binary.abstain) == (34, 66, 0)
    assert minority.binary.outcome_rate == STATUS_QUO
    assert minority.pair.winner_rates == (PROPOSAL,)
    minority_winners = [point for point in minority.points if point.rate in minority.winner_rates]
    assert all(4.25 <= point.rate <= 4.45 for point in minority_winners)
    assert all(point.approval_count == 100 and point.prefer_binary >= 65 for point in minority_winners)
    binary_score = next(point.mean_score for point in minority.points if point.rate == minority.binary.outcome_rate)
    assert minority.max_mean_score - binary_score > 0.15
    # Larger differences on declared 0–1 curves, not measured interpersonal intensity.
    majority_voters, minority_voters = minority.electorate.voters[:65], minority.electorate.voters[65:99]
    assert all(0 < voter.status_quo_score - voter.proposal_score < 0.1 for voter in majority_voters)
    assert math.fsum(voter.proposal_score - voter.status_quo_score for voter in minority_voters) / 34 > 0.4


def test_separate_tied_peaks_are_preserved_without_an_invented_compromise() -> None:
    # Isolate the tie rule from the seeded demonstration fixtures.
    result = aggregate_electorate(electorate(
        ComparisonVoter("other", "Other", ScalarBallot(5.95, 0.1, 0.1, 5.95, 5.95), "no"),
        ComparisonVoter("you", "You", ScalarBallot(3, 0.1, 0.1, 3, 3), "yes"),
    ))
    assert (result.binary.yes, result.binary.no) == (1, 1)
    assert not result.binary.passed and result.binary.outcome_rate == STATUS_QUO
    assert result.winner_rates == (3, 5.95)
    assert result.max_mean_score == 0.5


def test_equal_scores_abstain_and_binary_and_pair_ties_are_preserved() -> None:
    symmetric = ScalarBallot((STATUS_QUO + PROPOSAL) / 2, 2, 2, 0, 100)
    assert curve_vote(symmetric) == "abstain"
    result = aggregate_electorate(electorate(
        ComparisonVoter("prepared", "Prepared", symmetric, "yes"),
        ComparisonVoter("you", "You", symmetric, "no"),
    ))
    assert (result.binary.yes, result.binary.no, result.binary.abstain) == (1, 1, 0)
    assert not result.binary.passed and result.binary.outcome_rate == STATUS_QUO
    assert result.pair.winner_rates == (STATUS_QUO, PROPOSAL)
    assert result.winner_rates == (4.45, 4.5)


def test_yes_majority_and_abstentions_have_distinct_meanings() -> None:
    low = ScalarBallot(3, 2, 2, 0, 100)
    rejected_pair = ScalarBallot(9, 1, 1, 8, 10)
    result = aggregate_electorate(electorate(
        ComparisonVoter("you", "You", low, "yes"),
        ComparisonVoter("prepared", "Prepared", rejected_pair, curve_vote(rejected_pair)),
    ))
    assert result.binary.passed and result.binary.outcome_rate == PROPOSAL
    assert (result.binary.yes, result.binary.no, result.binary.abstain) == (1, 0, 1)
    assert result.electorate.voters[1].status_quo_score == result.electorate.voters[1].proposal_score == 0
    # One person's disapproval does not veto a grid rate supported by another.
    assert any(point.approval_count == 1 and point.mean_score > 0 for point in result.points)


@pytest.mark.parametrize("ideal", [0, 98.55, 100])
def test_grid_supports_full_domain_and_user_need_not_be_last(ideal: float) -> None:
    high = ScalarBallot(ideal, 1, 1, 0, 100)
    user = ComparisonVoter("you", "You", high, "no")
    result = aggregate_electorate(electorate(user))
    assert len(CANDIDATES) == 2001
    assert CANDIDATES[0] == 0 and CANDIDATES[-1] == 100
    assert STATUS_QUO in CANDIDATES and PROPOSAL in CANDIDATES
    assert result.winner_rates == (ideal,)
    at_ideal = next(point for point in result.points if point.rate == ideal)
    assert at_ideal.mean_score == at_ideal.user_score == 1
    assert at_ideal.user_approved and at_ideal.approval_count == 1
    other = ComparisonVoter("other", "Other", ballot(), "no")
    with_other = aggregate_electorate(electorate(user, other))
    assert next(point for point in with_other.points if point.rate == ideal).user_score == 1


def test_off_grid_zero_width_approval_returns_all_grid_ties() -> None:
    narrow = ScalarBallot(6.123, 2, 2, 6.123, 6.123)
    result = aggregate_electorate(electorate(ComparisonVoter("you", "You", narrow, "no")))
    assert result.winner_rates == CANDIDATES
    assert result.max_mean_score == 0
    assert all(point.approval_count == 0 and point.indifferent == 1 for point in result.points)
    assert result.pair.winner_rates == (STATUS_QUO, PROPOSAL)


def test_score_tolerance_is_absolute_and_explicit() -> None:
    assert compare_scores(0, SCORE_TIE_TOLERANCE) == 0
    assert compare_scores(0, SCORE_TIE_TOLERANCE * 1.01) == -1
    assert compare_scores(1, 1 - SCORE_TIE_TOLERANCE * 2) == 1


def test_invalid_electorates_and_user_votes_fail() -> None:
    with pytest.raises(ValueError):
        compare_ballots(ballot(), "abstain")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        aggregate_electorate(electorate())
    voter = ComparisonVoter("you", "You", ballot(), "no")
    with pytest.raises(ValueError):
        aggregate_electorate(electorate(voter, voter))
    with pytest.raises(ValueError):
        aggregate_electorate(electorate(replace(voter, id="other")))
    with pytest.raises(ValueError):
        ComparisonVoter("you", "You", ballot(), "invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="scenario"):
        compare_ballots(ballot(), "no", "unknown")  # type: ignore[arg-type]
