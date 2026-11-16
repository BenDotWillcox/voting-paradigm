"""
The comparison behind demo 5's claim: direct voting (with a full-turnout
reference corner), a district representative, a personal proxy and liquid
delegation, scored on overhead and fidelity over one simulated city.

Pure and seeded. The population is in `population`, delegate choice from
vote history in `choice`, the arrangements in `arrangements` and the
measures in `measures`. Design: prompts/demo-5-liquid-democracy.md.
"""

from .arrangements import (
    DIRECT,
    ORDINARY_RESOLVER_TURNOUT,
    PILOT_TURNOUT,
    PRIMARY_TURNOUT,
    TurnoutPolicy,
    FULL_TURNOUT,
    LIQUID,
    PROXY,
    REPRESENTATIVE,
    Election,
    Outcome,
    choose_liquid,
    choose_proxies,
    delegation_network,
    population_categories,
    direct,
    elect_representatives,
    full_turnout,
    liquid,
    proxy,
    representative,
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


def compare(
    population: Population,
    policy: ChoicePolicy | None = None,
    turnout: TurnoutPolicy = PRIMARY_TURNOUT,
) -> dict[str, Measures]:
    """
    Every arrangement on one population, keyed by arrangement. Outcome
    agreement is measured against the full-turnout reference.
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
    "ORDINARY_RESOLVER_TURNOUT",
    "PILOT_TURNOUT",
    "PRIMARY_TURNOUT",
    "TurnoutPolicy",
    "FULL_TURNOUT",
    "KEEP",
    "LIQUID",
    "NO",
    "NOT_CAST",
    "PROXY",
    "REPRESENTATIVE",
    "YES",
    "Agreement",
    "Choice",
    "ChoicePolicy",
    "Election",
    "Measures",
    "Outcome",
    "Population",
    "PooledAgreements",
    "PopulationConfig",
    "QuestionSet",
    "agreement",
    "agreement_counts",
    "choose",
    "choose_liquid",
    "choose_proxies",
    "compare",
    "delegation_network",
    "population_categories",
    "direct",
    "elect_representatives",
    "fidelity_by_voter",
    "full_turnout",
    "liquid",
    "lower_bound",
    "measure",
    "pooled_agreements",
    "proxy",
    "representative",
    "simulate_population",
]
