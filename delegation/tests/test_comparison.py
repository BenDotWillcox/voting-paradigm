"""Tests for the arrangement comparison (delegation.comparison)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from delegation.comparison import (
    KEEP,
    NO,
    NOT_CAST,
    YES,
    ChoicePolicy,
    PopulationConfig,
    agreement,
    agreement_counts,
    choose,
    choose_proxies,
    compare,
    direct,
    elect_representatives,
    full_turnout,
    liquid,
    lower_bound,
    measure,
    proxy,
    representative,
    simulate_population,
)

SMALL = PopulationConfig(
    seed=7,
    districts=3,
    residents_per_district=20,
    dimensions=3,
    history_questions_per_dimension=8,
    evaluation_questions_per_dimension=6,
)


@pytest.fixture(scope="module")
def small():
    return simulate_population(SMALL)


# ---------------------------------------------------------------------------
# Population
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        {"districts": 0},
        {"dimensions": 0},
        {"factor_loading": 1.5},
        {"cutpoint_sd": -1.0},
        {"min_turnout": 0.8, "max_turnout": 0.5},
        {"candidates_per_district": 50},
    ],
)
def test_config_rejects_bad_values(changes):
    with pytest.raises(ValueError):
        replace(SMALL, **changes)


def test_population_is_deterministic():
    a = simulate_population(SMALL)
    b = simulate_population(SMALL)
    assert a.ids == b.ids
    for name in ("district", "positions", "turnout"):
        assert np.array_equal(getattr(a, name), getattr(b, name))
    for period in ("history", "evaluation"):
        pa, pb = getattr(a, period), getattr(b, period)
        assert pa.ids == pb.ids
        assert np.array_equal(pa.sincere, pb.sincere)
        assert np.array_equal(pa.casts, pb.casts)


def test_population_shapes_and_balance(small):
    assert small.size == 60
    assert list(small.ids) == sorted(small.ids)
    assert small.positions.shape == (60, 3)
    assert len(small.history) == 24
    assert len(small.evaluation) == 18
    # Questions are balanced across dimensions
    assert np.bincount(small.history.dimension).tolist() == [8, 8, 8]
    assert set(np.unique(small.history.sincere)) <= {YES, NO}
    own = small.history.own_votes
    assert np.array_equal(own == NOT_CAST, ~small.history.casts)


def test_loading_sets_cross_issue_correlation():
    config = PopulationConfig(
        residents_per_district=4000,
        districts=1,
        district_lean_sd=0.0,
        history_questions_per_dimension=1,
        evaluation_questions_per_dimension=1,
    )
    for loading in (0.0, 0.6, 1.0):
        positions = simulate_population(replace(config, factor_loading=loading)).positions
        corr = np.corrcoef(positions.T)
        off = corr[~np.eye(corr.shape[0], dtype=bool)]
        assert off.mean() == pytest.approx(loading**2, abs=0.05)


def test_loading_sweep_reuses_draws():
    # The factor and specific draws are shared, so positions move smoothly
    low = simulate_population(replace(SMALL, factor_loading=0.5)).positions
    high = simulate_population(replace(SMALL, factor_loading=0.51)).positions
    assert np.abs(low - high).max() < 0.1


def test_sincere_vote_is_side_of_cutpoint_without_noise():
    pop = simulate_population(replace(SMALL, preference_noise_sd=0.0))
    q = pop.evaluation
    side = q.direction * (pop.positions[:, q.dimension] - q.cutpoint)
    assert np.array_equal(q.sincere, np.where(side > 0, YES, NO))


# ---------------------------------------------------------------------------
# Agreement and choice
# ---------------------------------------------------------------------------


def test_agreement_counts_rules():
    votes = np.array(
        [
            [YES, NO, YES, NOT_CAST],  # voter 0 votes on three questions
            [YES, NO, NOT_CAST, YES],  # skips one of voter 0's
            [NO, NO, YES, YES],
        ],
        dtype=np.int8,
    )
    matches, trials = agreement_counts(votes)
    # Voter 0's trials are the three questions they voted on
    assert trials[0].tolist() == [3, 3, 3]
    # Voter 1 skipped question 2: a miss for voter 0, not left out
    assert matches[0, 1] == 2
    assert matches[0, 2] == 2
    # Question 3, which voter 0 skipped, never counts for voter 0
    assert matches[1, 2] == 2 and trials[1, 2] == 3


def test_agreement_counts_rejects_bad_votes():
    with pytest.raises(ValueError):
        agreement_counts(np.array([[2, 1]], dtype=np.int8))


def test_lower_bound_prefers_more_evidence():
    assert lower_bound(18, 20) > lower_bound(2, 2)
    assert lower_bound(0, 0) == pytest.approx(0.1)
    with pytest.raises(ValueError):
        lower_bound(3, 2)


def test_ranking_excludes_self_and_breaks_ties_by_index():
    votes = np.array([[YES, YES], [YES, YES], [YES, YES], [NO, NO]], dtype=np.int8)
    a = agreement(votes)
    assert np.isneginf(np.diag(a.lower)).all()
    assert a.ranking(0).tolist() == [1, 2, 3]
    assert a.ranking(3).tolist() == [0, 1, 2]


def test_choose_respects_acceptance_and_limit():
    votes = simulate_population(SMALL).history.own_votes
    agreements = [agreement(votes[:, i::3]) for i in range(3)]
    nobody = choose(agreements, ChoicePolicy(acceptance=1.0))
    assert (nobody.delegate == KEEP).all()
    one = choose(agreements, ChoicePolicy(max_categories=1))
    assert (one.held().sum(axis=1) == 1).all()
    # The single category kept is each voter's best one
    every = choose(agreements, ChoicePolicy())
    for v in range(votes.shape[0]):
        (k,) = np.flatnonzero(one.held()[v])
        assert every.lower[v, k] == np.nanmax(every.lower[v])
        assert one.delegate[v, k] == agreements[k].ranking(v)[0]


def test_choose_is_simultaneous():
    # Two people who are each other's best match both delegate to each
    # other; nobody is refused for coming second.
    votes = np.array(
        [[YES, YES, YES, YES], [YES, YES, YES, YES], [NO, NO, NO, YES]],
        dtype=np.int8,
    )
    choice = choose([agreement(votes)], ChoicePolicy())
    assert choice.delegate[:, 0].tolist() == [1, 0, 0]


# ---------------------------------------------------------------------------
# Arrangements
# ---------------------------------------------------------------------------


def test_full_turnout_is_the_reference_corner(small):
    outcome = full_turnout(small)
    assert np.array_equal(outcome.counted, small.evaluation.sincere)
    m = measure(small, outcome, outcome)
    assert (m.fidelity, m.overhead, m.outcome_agreement) == (1.0, 1.0, 1.0)
    assert m.delegated_share == 0.0


def test_direct(small):
    outcome = direct(small)
    assert outcome.kept.all()
    cast = small.evaluation.casts
    assert (outcome.counted[cast] == small.evaluation.sincere[cast]).all()
    assert (outcome.counted[~cast] == NOT_CAST).all()
    m = measure(small, outcome, full_turnout(small))
    assert m.overhead == 1.0
    # Direct fidelity is turnout: a non-voter's ballot matches nothing
    assert m.fidelity == pytest.approx(cast.mean())


def test_compare_measures_outcomes_against_full_turnout(small):
    result = compare(small)
    assert list(result) == [
        "full_turnout",
        "direct",
        "representative",
        "proxy",
        "liquid",
    ]
    assert result["full_turnout"].outcome_agreement == 1.0
    assert result["full_turnout"].fidelity == 1.0


def test_representative(small):
    election = elect_representatives(small)
    for district, (drawn, rep) in enumerate(zip(election.candidates, election.elected)):
        assert len(set(drawn.tolist())) == SMALL.candidates_per_district
        assert rep in drawn
        assert small.district[rep] == district
    outcome = representative(small, election)
    rep = election.elected[small.district]
    assert np.array_equal(outcome.counted, small.evaluation.sincere[rep])
    assert not outcome.kept.any()


def test_representative_wins_their_own_district_vote():
    # With one candidate the election is uncontested
    pop = simulate_population(replace(SMALL, candidates_per_district=1))
    election = elect_representatives(pop)
    assert all(rep == drawn[0] for drawn, rep in zip(election.candidates, election.elected))


def test_liquid_with_no_delegations_is_direct(small):
    nobody = ChoicePolicy(acceptance=1.0)
    assert np.array_equal(liquid(small, nobody).counted, direct(small).counted)
    assert np.array_equal(proxy(small, nobody).counted, direct(small).counted)


def test_delegated_resolvers_are_consistent(small):
    policy = ChoicePolicy()
    choice = choose_proxies(small, policy)
    outcome = proxy(small, policy)
    for v in range(small.size):
        for q in range(len(small.evaluation)):
            r = outcome.resolver[v, q]
            # A resolver decides for themself
            assert outcome.resolver[r, q] == r
            if r != v:
                assert choice.delegate[v, 0] != KEEP
    # Each counted ballot is the resolver's own ballot
    own = small.evaluation.own_votes
    cols = np.arange(len(small.evaluation))[None, :]
    assert np.array_equal(outcome.counted, own[outcome.resolver, cols])


def test_mutual_best_matches_keep_through_the_loop_rule(small):
    policy = ChoicePolicy()
    choice = choose_proxies(small, policy)
    outcome = proxy(small, policy)
    delegate = choice.delegate[:, 0]
    mutual = [v for v in range(small.size) if delegate[v] != KEEP and delegate[delegate[v]] == v]
    assert mutual, "the fixture should contain a mutual best match"
    for v in mutual:
        assert outcome.kept[v].all()


def test_compare_is_deterministic(small):
    assert compare(small) == compare(simulate_population(SMALL))


# ---------------------------------------------------------------------------
# Properties the benchmark relies on
# ---------------------------------------------------------------------------

MEDIUM = PopulationConfig(
    seed=11,
    districts=3,
    residents_per_district=60,
    dimensions=4,
    history_questions_per_dimension=20,
    evaluation_questions_per_dimension=10,
)


def test_bundling_costs_more_when_issues_cut_across():
    def gap(loading: float) -> float:
        pop = simulate_population(replace(MEDIUM, factor_loading=loading))
        reference = full_turnout(pop)
        return (
            measure(pop, liquid(pop), reference).fidelity
            - measure(pop, proxy(pop), reference).fidelity
        )

    assert gap(0.0) > gap(1.0)


def test_longer_history_picks_better_proxies():
    def chosen_agreement(per_dimension: int) -> float:
        pop = simulate_population(
            replace(MEDIUM, history_questions_per_dimension=per_dimension)
        )
        delegate = choose_proxies(pop, ChoicePolicy()).delegate[:, 0]
        sincere = pop.evaluation.sincere
        return float((sincere == sincere[delegate]).mean())

    assert chosen_agreement(2) < chosen_agreement(30)
