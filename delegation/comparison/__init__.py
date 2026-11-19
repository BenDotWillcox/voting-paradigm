"""
The comparison behind demo 5's claim: direct voting (with a full-turnout
reference corner), a district representative, a matched pair of
three-candidate arms, a personal proxy and liquid delegation, scored on
overhead and fidelity over one simulated city.

Pure and seeded. The population is in `population` (structural) and
`beliefs` (fitted to the CES), delegate choice from vote history in
`choice`, the arrangements in `arrangements` and the measures in
`measures`. `compare` is the protocol's entry point: it calibrates liquid
and the proxy with the overhead rule. Design:
prompts/demo-5-liquid-democracy.md.
"""

from dataclasses import dataclass

from .arrangements import (
    DIRECT,
    DISTRICT_CHOICE,
    DISTRICT_CHOICE_VOTERS,
    FULL_TURNOUT,
    LIQUID,
    DIAL_TURNOUT,
    ORDINARY_RESOLVER_TURNOUT,
    PILOT_TURNOUT,
    SYMMETRIC_TURNOUT,
    PROXY,
    REPRESENTATIVE,
    REPRESENTATIVE_BY_RECORD,
    AcceptanceChoice,
    Election,
    Outcome,
    TurnoutPolicy,
    acceptance_for_overhead,
    choose_liquid,
    choose_proxies,
    delegation_network,
    direct,
    district_choice,
    district_choice_voters,
    elect_representatives,
    full_turnout,
    history_overhead,
    liquid,
    liquid_at_overhead,
    population_categories,
    population_tie_key,
    proxy,
    proxy_at_overhead,
    record_preferences,
    representative,
    representative_by_record,
    resolve_functional,
    resolve_with_loops,
)
from .choice import (
    DEFAULT_CREDIBLE_MASS,
    KEEP,
    Agreement,
    Choice,
    ChoicePolicy,
    PooledAgreements,
    agreement,
    agreement_counts,
    choose,
    lower_bound,
    pooled_agreements,
    tie_key,
    top_candidates,
)
from .measures import Attribution, Measures, attribute, fidelity_by_voter, measure
from .population import (
    NO,
    NOT_CAST,
    YES,
    Population,
    PopulationConfig,
    QuestionSet,
    simulate_population,
)


@dataclass(frozen=True)
class Comparison:
    """Every arrangement on one city, and how liquid and the proxy were calibrated."""

    measures: dict[str, Measures]
    liquid_acceptance: AcceptanceChoice
    proxy_acceptance: AcceptanceChoice
    # The headline and specialisation differences split over liquid's kept
    # and resolved pairs, keyed "liquid_minus_<arrangement>"
    attributions: dict[str, Attribution]
    # Every arrangement's outcome, in the order of `measures`, for callers
    # that need ballots rather than summaries (the benchmark runner)
    outcomes: dict[str, Outcome]


def compare(
    population: Population,
    turnout: TurnoutPolicy = DIAL_TURNOUT,
    max_overhead: float = 0.10,
    base: ChoicePolicy | None = None,
) -> Comparison:
    """
    The protocol's entry point: every arrangement on one city, with liquid
    and the proxy each calibrated by the overhead rule on history questions
    only, under the protocol's turnout condition (DIAL_TURNOUT: delegates at
    their own rate, office holders at the office-holder rate) unless another
    is given. Outcome agreement is measured against the full-turnout reference.
    The three-candidate chain representative_by_record ->
    district_choice_voters -> district_choice -> proxy -> liquid has
    contrasts that sum to liquid minus representative_by_record: sharing,
    choice by non-voters, the city-wide proxy (a combined effect of a wider
    pool, onward delegation, threshold keeping and, under ordinary turnout,
    the resolver floor) and topic delegates.
    """
    base = base or ChoicePolicy()
    reference = full_turnout(population)
    election = elect_representatives(population)
    liquid_outcome, liquid_fixed = liquid_at_overhead(population, base, turnout, max_overhead)
    proxy_outcome, proxy_fixed = proxy_at_overhead(population, base, turnout, max_overhead)
    outcomes = [
        reference,
        direct(population),
        representative(population, election, turnout),
        representative_by_record(population, election, turnout),
        district_choice_voters(population, election, turnout),
        district_choice(population, election, turnout),
        proxy_outcome,
        liquid_outcome,
    ]
    by_name = {o.arrangement: o for o in outcomes}
    return Comparison(
        measures={o.arrangement: measure(population, o, reference) for o in outcomes},
        liquid_acceptance=liquid_fixed,
        proxy_acceptance=proxy_fixed,
        attributions={
            f"liquid_minus_{other}": attribute(population, liquid_outcome, by_name[other])
            for other in (REPRESENTATIVE, PROXY)
        },
        outcomes=by_name,
    )


def compare_fixed(
    population: Population,
    policy: ChoicePolicy | None = None,
    turnout: TurnoutPolicy = DIAL_TURNOUT,
) -> dict[str, Measures]:
    """
    Exploration only, not the protocol: the original five arrangements with
    liquid and the proxy at one fixed choice policy, uncalibrated.
    """
    reference = full_turnout(population)
    outcomes = [
        reference,
        direct(population),
        representative(population, turnout=turnout),
        proxy(population, policy, turnout),
        liquid(population, policy, turnout),
    ]
    return {o.arrangement: measure(population, o, reference) for o in outcomes}


__all__ = [
    "DEFAULT_CREDIBLE_MASS",
    "DIRECT",
    "DISTRICT_CHOICE",
    "DISTRICT_CHOICE_VOTERS",
    "FULL_TURNOUT",
    "KEEP",
    "LIQUID",
    "NO",
    "NOT_CAST",
    "DIAL_TURNOUT",
    "ORDINARY_RESOLVER_TURNOUT",
    "PILOT_TURNOUT",
    "SYMMETRIC_TURNOUT",
    "PROXY",
    "REPRESENTATIVE",
    "REPRESENTATIVE_BY_RECORD",
    "YES",
    "AcceptanceChoice",
    "Agreement",
    "Attribution",
    "Choice",
    "ChoicePolicy",
    "Comparison",
    "Election",
    "Measures",
    "Outcome",
    "Population",
    "PooledAgreements",
    "PopulationConfig",
    "QuestionSet",
    "TurnoutPolicy",
    "acceptance_for_overhead",
    "agreement",
    "agreement_counts",
    "attribute",
    "choose",
    "choose_liquid",
    "choose_proxies",
    "compare",
    "compare_fixed",
    "delegation_network",
    "direct",
    "district_choice",
    "district_choice_voters",
    "elect_representatives",
    "fidelity_by_voter",
    "full_turnout",
    "history_overhead",
    "liquid",
    "liquid_at_overhead",
    "lower_bound",
    "measure",
    "pooled_agreements",
    "population_categories",
    "population_tie_key",
    "proxy",
    "proxy_at_overhead",
    "record_preferences",
    "representative",
    "representative_by_record",
    "resolve_functional",
    "resolve_with_loops",
    "simulate_population",
    "tie_key",
    "top_candidates",
]
