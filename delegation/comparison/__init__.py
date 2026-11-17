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
    FULL_TURNOUT,
    LIQUID,
    ORDINARY_RESOLVER_TURNOUT,
    PILOT_TURNOUT,
    PRIMARY_TURNOUT,
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
    elect_representatives,
    full_turnout,
    history_overhead,
    liquid,
    liquid_at_overhead,
    population_categories,
    proxy,
    proxy_at_overhead,
    record_preferences,
    representative,
    representative_by_record,
    resolve_functional,
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
    top_candidates,
)
from .measures import Measures, fidelity_by_voter, measure
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


def compare(
    population: Population,
    turnout: TurnoutPolicy = PRIMARY_TURNOUT,
    max_overhead: float = 0.10,
    base: ChoicePolicy | None = None,
) -> Comparison:
    """
    The protocol's entry point: every arrangement on one city, with liquid
    and the proxy each calibrated by the overhead rule on history questions
    only. Outcome agreement is measured against the full-turnout reference.
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
        district_choice(population, election, turnout),
        proxy_outcome,
        liquid_outcome,
    ]
    return Comparison(
        measures={o.arrangement: measure(population, o, reference) for o in outcomes},
        liquid_acceptance=liquid_fixed,
        proxy_acceptance=proxy_fixed,
    )


def compare_fixed(
    population: Population,
    policy: ChoicePolicy | None = None,
    turnout: TurnoutPolicy = PRIMARY_TURNOUT,
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
    "FULL_TURNOUT",
    "KEEP",
    "LIQUID",
    "NO",
    "NOT_CAST",
    "ORDINARY_RESOLVER_TURNOUT",
    "PILOT_TURNOUT",
    "PRIMARY_TURNOUT",
    "PROXY",
    "REPRESENTATIVE",
    "REPRESENTATIVE_BY_RECORD",
    "YES",
    "AcceptanceChoice",
    "Agreement",
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
    "choose",
    "choose_liquid",
    "choose_proxies",
    "compare",
    "compare_fixed",
    "delegation_network",
    "direct",
    "district_choice",
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
    "proxy",
    "proxy_at_overhead",
    "record_preferences",
    "representative",
    "representative_by_record",
    "resolve_functional",
    "simulate_population",
    "top_candidates",
]
