"""Tests for the arrangement comparison (delegation.comparison)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from delegation.comparison import (
    KEEP,
    ORDINARY_RESOLVER_TURNOUT,
    PILOT_TURNOUT,
    TurnoutPolicy,
    NO,
    NOT_CAST,
    YES,
    ChoicePolicy,
    PopulationConfig,
    agreement,
    agreement_counts,
    choose,
    choose_liquid,
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
    result = compare(small).measures
    assert list(result) == [
        "full_turnout",
        "direct",
        "representative",
        "representative_by_record",
        "district_choice_voters",
        "district_choice",
        "proxy",
        "liquid",
    ]
    assert result["full_turnout"].outcome_agreement == 1.0
    assert result["full_turnout"].fidelity == 1.0


def test_compare_is_the_calibrated_entry_point(small):
    from delegation.comparison import acceptance_for_overhead, liquid_at_overhead

    result = compare(small)
    assert result.liquid_acceptance == acceptance_for_overhead(small)
    calibrated, _ = liquid_at_overhead(small)
    assert result.measures["liquid"].overhead == pytest.approx(calibrated.kept.mean())
    # History and evaluation share topic proportions here, so with exact
    # routing evaluation overhead equals history overhead exactly
    assert result.measures["liquid"].overhead == pytest.approx(
        result.liquid_acceptance.history_overhead
    )


def test_shares_sum_to_one_and_decompose_fidelity(small):
    for m in compare(small).measures.values():
        assert m.fidelity + m.contrary_share + m.none_share == pytest.approx(1.0)
        if m.arrangement in ("proxy", "liquid", "district_choice", "district_choice_voters"):
            assert 0.0 <= m.resolver_attendance <= 1.0


def test_matched_arms_share_candidates(small):
    from delegation.comparison import (
        district_choice,
        record_preferences,
        representative_by_record,
    )

    election = elect_representatives(small)
    preferred = record_preferences(small, election)
    for district, drawn in enumerate(election.candidates):
        assert set(preferred[small.residents_of(district)]) <= set(drawn.tolist())
    choice = district_choice(small, election, PILOT_TURNOUT)
    assert np.array_equal(choice.resolver[:, 0], preferred)
    elected = representative_by_record(small, election, PILOT_TURNOUT)
    for district, drawn in enumerate(election.candidates):
        rows = small.residents_of(district)
        winner = set(elected.resolver[rows, 0].tolist())
        assert len(winner) == 1 and winner <= set(drawn.tolist())


def test_representative(small):
    election = elect_representatives(small)
    for district, (drawn, rep) in enumerate(zip(election.candidates, election.elected)):
        assert len(set(drawn.tolist())) == SMALL.candidates_per_district
        assert rep in drawn
        assert small.district[rep] == district
    outcome = representative(small, election, PILOT_TURNOUT)
    rep = election.elected[small.district]
    assert np.array_equal(outcome.counted, small.evaluation.sincere[rep])
    # Only the elected residents decide, for themselves (consistent accounting)
    assert np.array_equal(outcome.kept.any(axis=1), np.isin(np.arange(small.size), election.elected))


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
    outcome = proxy(small, policy, ORDINARY_RESOLVER_TURNOUT)
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
    # repr, not ==: some measures are NaN when undefined, and NaN != NaN
    assert repr(compare(small)) == repr(compare(simulate_population(SMALL)))


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


# ---------------------------------------------------------------------------
# Resolver turnout (amendment A1)
# ---------------------------------------------------------------------------


def test_turnout_policy_rejects_bad_rates():
    with pytest.raises(ValueError):
        TurnoutPolicy(office_rate=1.5)
    with pytest.raises(ValueError):
        TurnoutPolicy(resolver_turnout=-0.1)


def test_representative_votes_at_the_office_rate(small):
    election = elect_representatives(small)
    always = representative(small, election, TurnoutPolicy(office_rate=1.0))
    assert (always.counted != NOT_CAST).all()
    never = representative(small, election, TurnoutPolicy(office_rate=0.0))
    # With no floor the representative votes at their own turnout rate
    rep = election.elected[small.district]
    assert np.array_equal(never.counted, small.evaluation.own_votes[rep])


def test_resolvers_vote_at_the_floor_and_keepers_at_their_own_rate(small):
    policy = ChoicePolicy()
    full = proxy(small, policy, TurnoutPolicy(resolver_turnout=1.0))
    cols = np.arange(len(small.evaluation))[None, :]
    voters = np.arange(small.size)[:, None]
    holds = np.zeros(full.resolver.shape, dtype=bool)
    others = full.resolver != voters
    holds[full.resolver[others], np.broadcast_to(cols, full.resolver.shape)[others]] = True
    resolver_holds = holds[full.resolver, cols]
    # Every vote resolved by someone holding others' votes is cast
    assert (full.counted[resolver_holds] != NOT_CAST).all()
    # A voter who keeps and holds nobody else's vote votes at their own rate
    alone = full.kept & ~holds
    own = small.evaluation.own_votes
    assert np.array_equal(full.counted[alone], own[alone])


def test_raising_resolver_turnout_only_adds_ballots(small):
    policy = ChoicePolicy()
    previous = None
    for rate in (0.0, 0.5, 0.9, 1.0):
        counted = liquid(small, policy, TurnoutPolicy(resolver_turnout=rate)).counted
        if previous is not None:
            # Coupled draws: a ballot cast at a lower floor is still cast
            assert ((previous == NOT_CAST) | (counted == previous)).all()
            assert (counted != NOT_CAST).sum() >= (previous != NOT_CAST).sum()
        previous = counted


def test_pilot_turnout_reproduces_the_old_rules(small):
    policy = ChoicePolicy()
    rep = representative(small, turnout=PILOT_TURNOUT)
    assert (rep.counted != NOT_CAST).all()
    old = proxy(small, policy, PILOT_TURNOUT)
    cols = np.arange(len(small.evaluation))[None, :]
    assert np.array_equal(old.counted, small.evaluation.own_votes[old.resolver, cols])


# ---------------------------------------------------------------------------
# Agreement pooled across categories (amendment A3)
# ---------------------------------------------------------------------------

POOL = PopulationConfig(
    seed=5,
    districts=2,
    residents_per_district=60,
    dimensions=4,
    history_questions_per_dimension=15,
    evaluation_questions_per_dimension=2,
)


def _pooled(config: PopulationConfig):
    from delegation.comparison import pooled_agreements

    pop = simulate_population(config)
    return pop, pooled_agreements(
        pop.history.own_votes, pop.history.dimension, config.dimensions
    )


def test_pooling_is_stronger_when_categories_agree():
    # Fully correlated issues: a pair's agreement barely differs between
    # categories, so the prior should carry more weight than when issues
    # cut across
    _, together = _pooled(replace(POOL, factor_loading=1.0))
    _, apart = _pooled(replace(POOL, factor_loading=0.0))
    assert together.strength > apart.strength


def test_thin_categories_lean_on_the_whole_record():
    from delegation.comparison import pooled_agreements

    pop = simulate_population(replace(POOL, factor_loading=1.0))
    votes = pop.history.own_votes
    # Category 0 gets only two questions; category 1 gets the rest
    category = np.ones(votes.shape[1], dtype=np.int64)
    category[:2] = 0
    pooled = pooled_agreements(votes, category, 2)
    overall = agreement(votes)
    thin_pooled = pooled.agreements[0].mean
    thin_uniform = agreement(votes[:, :2]).mean
    off = ~np.eye(pop.size, dtype=bool)
    gap_pooled = np.abs(thin_pooled - overall.mean)[off].mean()
    gap_uniform = np.abs(thin_uniform - overall.mean)[off].mean()
    assert gap_pooled < gap_uniform


def test_pooled_agreement_keeps_counts_and_excludes_self():
    pop, pooled = _pooled(POOL)
    for k, a in enumerate(pooled.agreements):
        m, n = agreement_counts(pop.history.own_votes[:, pop.history.dimension == k])
        assert np.array_equal(a.matches, m) and np.array_equal(a.trials, n)
        assert np.isneginf(np.diag(a.lower)).all()
        assert ((a.mean > 0) & (a.mean < 1)).all()


def test_borrow_strength_can_be_switched_off():
    from delegation.comparison import population_tie_key

    pop = simulate_population(POOL)
    uniform = choose_liquid(pop, ChoicePolicy(borrow_strength=False))
    by_hand = choose(
        [agreement(pop.history.own_votes[:, pop.history.on_dimension(d)]) for d in range(4)],
        ChoicePolicy(),
        population_tie_key(pop),
    )
    assert np.array_equal(uniform.delegate, by_hand.delegate)
    pooled = choose_liquid(pop, ChoicePolicy())
    assert not np.array_equal(pooled.delegate, uniform.delegate)


# ---------------------------------------------------------------------------
# The 10% overhead rule
# ---------------------------------------------------------------------------


def test_overhead_rule_meets_the_bound_from_history_only():
    from delegation.comparison import acceptance_for_overhead, history_overhead

    pop = simulate_population(POOL)
    fixed = acceptance_for_overhead(pop, ChoicePolicy(), max_overhead=0.10)
    assert fixed.feasible
    assert fixed.history_overhead <= 0.10
    assert history_overhead(pop, ChoicePolicy(acceptance=fixed.acceptance)) == pytest.approx(
        fixed.history_overhead
    )
    # A stricter bound never allows a higher acceptance
    stricter = acceptance_for_overhead(pop, ChoicePolicy(), max_overhead=0.05)
    assert stricter.acceptance <= fixed.acceptance


def test_overhead_rule_reports_an_impossible_bound():
    from delegation.comparison import acceptance_for_overhead

    pop = simulate_population(POOL)
    impossible = acceptance_for_overhead(pop, ChoicePolicy(), max_overhead=0.0)
    # Someone must decide, so zero overhead cannot be reached; the level
    # with the lowest overhead is used and the city is flagged
    assert not impossible.feasible
    assert impossible.history_overhead > 0.0


def test_overhead_rule_uses_no_evaluation_question():
    from delegation.comparison import acceptance_for_overhead

    pop = simulate_population(POOL)
    other = simulate_population(replace(POOL, evaluation_questions_per_dimension=5))
    # Same history, different evaluation period: same acceptance
    assert acceptance_for_overhead(pop).acceptance == acceptance_for_overhead(other).acceptance


def test_liquid_at_overhead_runs():
    from delegation.comparison import liquid_at_overhead

    pop = simulate_population(POOL)
    outcome, fixed = liquid_at_overhead(pop)
    assert outcome.arrangement == "liquid"
    assert 0.0 <= fixed.acceptance <= 1.0


# ---------------------------------------------------------------------------
# Exact resolver and exhaustive overhead rule (pre-freeze review)
# ---------------------------------------------------------------------------


def test_fast_resolver_matches_the_graph_machinery():
    from delegation.comparison.arrangements import (
        _resolve_by_category,
        reference_resolvers,
    )

    pop = simulate_population(POOL)
    liquid_choice = choose_liquid(pop, ChoicePolicy())
    assert np.array_equal(
        _resolve_by_category(liquid_choice, pop.evaluation.dimension)[0],
        reference_resolvers(pop, liquid_choice, pop.evaluation, single_category=False),
    )
    proxy_choice = choose_proxies(pop, ChoicePolicy())
    everything = np.zeros(len(pop.evaluation), dtype=np.int64)
    assert np.array_equal(
        _resolve_by_category(proxy_choice, everything)[0],
        reference_resolvers(pop, proxy_choice, pop.evaluation, single_category=True),
    )


def test_resolve_functional_on_loops_and_chains():
    from delegation.comparison.arrangements import resolve_functional

    # 0 <-> 1 is a loop; 2 -> 0 enters it; 3 -> 2 -> 0; 4 keeps; 5 -> 4
    delegate_of = np.array([1, 0, 0, 2, KEEP, 4])
    assert resolve_functional(delegate_of).tolist() == [0, 1, 0, 0, 4, 4]


def test_loop_membership_separates_a_mutual_pair_from_two_keeps():
    from delegation.comparison import resolve_with_loops

    # The same resolvers, two different stories
    mutual = np.array([1, 0, KEEP])
    keeps = np.array([KEEP, KEEP, KEEP])
    r_mutual, on_loop, loops = resolve_with_loops(mutual)
    r_keeps, no_loop, none = resolve_with_loops(keeps)
    assert r_mutual.tolist() == r_keeps.tolist() == [0, 1, 2]
    assert on_loop.tolist() == [True, True, False] and loops == 1
    assert not no_loop.any() and none == 0
    # Two loops and a chain into one of them
    _, on_loop, loops = resolve_with_loops(np.array([1, 0, 3, 4, 2, 2]))
    assert loops == 2 and on_loop.tolist() == [True, True, True, True, True, False]


def test_compare_reports_loops(small):
    from delegation.comparison import liquid_at_overhead

    outcome, _ = liquid_at_overhead(small)
    m = compare(small).measures
    assert m["liquid"].loop_share == pytest.approx(outcome.looped.mean())
    assert m["liquid"].mean_loops == pytest.approx(outcome.loops.mean())
    # Looped voters decide for themselves
    assert outcome.kept[outcome.looped].all()
    for name in ("direct", "representative", "district_choice"):
        assert m[name].loop_share == 0.0 and m[name].mean_loops == 0.0


def test_attribution_sums_to_the_fidelity_difference(small):
    result = compare(small)
    for key, a in result.attributions.items():
        other = key.removeprefix("liquid_minus_")
        expected = result.measures["liquid"].fidelity - result.measures[other].fidelity
        assert a.difference == pytest.approx(expected)
        parts = a.kept_share * a.kept_difference + (1 - a.kept_share) * a.resolved_difference
        assert parts == pytest.approx(a.difference)


def test_ties_do_not_follow_row_order():
    # Everyone agrees equally with everyone: every candidate ties
    people = 40
    lower = np.zeros((people, people))
    np.fill_diagonal(lower, -np.inf)
    from delegation.comparison import Agreement, tie_key, top_candidates

    flat = Agreement(
        np.zeros((people, people), dtype=np.int64),
        np.zeros((people, people), dtype=np.int64),
        lower,
        0.8,
    )
    by_index, _ = top_candidates([flat])
    assert set(by_index[:, 0].tolist()) <= {0, 1}
    key = tie_key(7, people)
    seeded, _ = top_candidates([flat], key)
    assert len(set(seeded[:, 0].tolist())) > people // 4
    assert (seeded[:, 0] != np.arange(people)).all()
    assert np.array_equal(seeded, top_candidates([flat], tie_key(7, people))[0])


def test_matched_participation_arm(small):
    from delegation.comparison import (
        district_choice,
        district_choice_voters,
        record_preferences,
        representative_by_record,
    )
    from delegation.comparison.arrangements import _record_election

    election = elect_representatives(small)
    preferred = record_preferences(small, election)
    winner_of, voted = _record_election(small, election, preferred)
    assert 0 < voted.mean() < 1
    voters = district_choice_voters(small, election, PILOT_TURNOUT)
    elected = representative_by_record(small, election, PILOT_TURNOUT)
    everyone = district_choice(small, election, PILOT_TURNOUT)
    # Election voters choose their own candidate; non-voters get the winner
    assert np.array_equal(voters.resolver[voted, 0], preferred[voted])
    assert np.array_equal(voters.resolver[~voted, 0], elected.resolver[~voted, 0])
    assert np.array_equal(everyone.resolver[:, 0], preferred)
    # Constituents of an elected representative maintain no assignment
    assert (elected.delegations == 0).all()
    assert (voters.delegations[~voted] == 0).all()
    assert np.array_equal(voters.delegations[voted], (preferred[voted] != np.flatnonzero(voted)).astype(int))


def test_overhead_rule_finds_the_level_that_breaks_a_mutual_pair():
    from delegation.comparison.arrangements import _overhead_rule

    # Ten people, one category. Everyone delegates to person 0, and 0 and 1
    # are each other's best match. At acceptance 0 the loop rule leaves both
    # deciding for themselves: overhead 0.2. A level just above person 1's
    # bound breaks 1 -> 0, everyone resolves to 1: overhead 0.1.
    top = np.array([[1], [0], [0], [0], [0], [0], [0], [0], [0], [0]])
    best = np.array([[0.9], [0.4], [0.8], [0.8], [0.8], [0.8], [0.8], [0.8], [0.8], [0.8]])
    fixed = _overhead_rule(top, best, np.array([1.0]), max_overhead=0.10)
    assert fixed.feasible
    assert fixed.history_overhead == pytest.approx(0.10)
    assert 0.4 < fixed.acceptance <= 0.8


def test_overhead_rule_takes_the_lowest_overhead_when_infeasible():
    from delegation.comparison.arrangements import _overhead_rule

    top = np.array([[1], [0]])
    best = np.array([[0.9], [0.9]])
    fixed = _overhead_rule(top, best, np.array([1.0]), max_overhead=0.10)
    assert not fixed.feasible
    # Delegating forms the pair loop (overhead 1); either way overhead is 1
    assert fixed.history_overhead == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Third review (2026-11-18)
# ---------------------------------------------------------------------------


def test_resolver_attendance_reads_the_resolvers_own_cast():
    from delegation.comparison import (
        PRIMARY_TURNOUT,
        district_choice_voters,
        record_preferences,
    )
    from delegation.comparison.arrangements import _record_election

    pop = simulate_population(POOL)
    election = elect_representatives(pop)
    outcome = district_choice_voters(pop, election, PRIMARY_TURNOUT)
    people, questions = outcome.resolver.shape
    columns = np.broadcast_to(np.arange(questions), (people, questions))
    others = outcome.resolver != np.arange(people)[:, None]
    holds = np.zeros((people, questions), dtype=bool)
    holds[outcome.resolver[others], columns[others]] = True
    # Recompute each person's own cast independently of the outcome
    rate = np.where(holds, np.maximum(pop.turnout[:, None], 0.96), pop.turnout[:, None])
    cast = pop.evaluation.turnout_draw < rate
    expected = cast[holds].mean()
    m = measure(pop, outcome, full_turnout(pop))
    assert m.resolver_attendance == pytest.approx(expected)
    # The case that broke the old reading: a candidate who skipped the
    # election holds followers while their own vote goes to the winner
    preferred = record_preferences(pop, election)
    _, voted = _record_election(pop, election, preferred)
    assigned_away = holds & ~outcome.kept
    assert assigned_away.any()
    assert not voted[np.flatnonzero(assigned_away.any(axis=1))].any()
    # Their own counted ballot is the winner's, which can differ from what
    # they cast for their followers
    own_none = outcome.counted == NOT_CAST
    assert (own_none[assigned_away] != ~cast[assigned_away]).any()
    # They decide those questions, so they count toward overhead
    assert m.overhead == pytest.approx((outcome.kept | holds).mean())
    assert m.overhead > outcome.kept.mean()


def test_overhead_is_self_resolution_wherever_holders_resolve_themselves():
    result = compare(simulate_population(POOL))
    pop = simulate_population(POOL)
    from delegation.comparison import liquid_at_overhead, proxy_at_overhead

    for outcome, _ in (liquid_at_overhead(pop), proxy_at_overhead(pop)):
        assert result.measures[outcome.arrangement].overhead == pytest.approx(outcome.kept.mean())


def test_platform_and_record_elections_share_tie_breaks():
    from delegation.comparison import representative_by_record

    # One candidate per district: both elections are uncontested
    pop = simulate_population(replace(SMALL, candidates_per_district=1))
    election = elect_representatives(pop)
    by_record = representative_by_record(pop, election)
    assert np.array_equal(by_record.resolver[:, 0], election.elected[pop.district])
    # With nobody voting, three candidates tie 1-1-1 on their own ballots,
    # and the two elections must resolve that tie identically
    base = simulate_population(SMALL)
    silent = replace(base, turnout=np.zeros_like(base.turnout))
    platform = elect_representatives(silent)
    record = representative_by_record(silent, platform)
    assert np.array_equal(record.resolver[:, 0], platform.elected[silent.district])


def test_full_overhead_budget_selects_acceptance_one(small):
    from delegation.comparison import acceptance_for_overhead

    fixed = acceptance_for_overhead(small, ChoicePolicy(), max_overhead=1.0)
    assert fixed.acceptance == 1.0
    assert fixed.history_overhead == pytest.approx(1.0)
    assert fixed.feasible
    # The protocol's 10% level is unaffected
    assert acceptance_for_overhead(small).acceptance < 1.0


def test_only_people_who_decide_cast_ballots(small):
    from delegation.comparison import (
        PRIMARY_TURNOUT,
        district_choice,
        district_choice_voters,
        liquid_at_overhead,
        proxy_at_overhead,
        representative_by_record,
    )

    election = elect_representatives(small)
    outcomes = [
        direct(small),
        representative(small, election, PRIMARY_TURNOUT),
        representative_by_record(small, election, PRIMARY_TURNOUT),
        district_choice_voters(small, election, PRIMARY_TURNOUT),
        district_choice(small, election, PRIMARY_TURNOUT),
        liquid_at_overhead(small)[0],
        proxy_at_overhead(small)[0],
    ]
    for outcome in outcomes:
        people, questions = outcome.resolver.shape
        columns = np.broadcast_to(np.arange(questions), (people, questions))
        others = outcome.resolver != np.arange(people)[:, None]
        holds = np.zeros((people, questions), dtype=bool)
        holds[outcome.resolver[others], columns[others]] = True
        decides = outcome.kept | holds
        assert not (outcome.cast & ~decides).any(), outcome.arrangement
        # A counted ballot exists exactly when its resolver cast one
        rows = outcome.resolver
        assert np.array_equal(outcome.counted != NOT_CAST, outcome.cast[rows, columns]), outcome.arrangement
    rep = outcomes[1]
    assert set(np.flatnonzero(rep.cast.any(axis=1))) <= set(election.elected.tolist())
