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
    FULL_TURNOUT,
    LIQUID,
    PROXY,
    REPRESENTATIVE,
    Election,
    Outcome,
    choose_liquid,
    choose_proxies,
    delegation_network,
    dimension_category,
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
    agreement,
    agreement_counts,
    choose,
    lower_bound,
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
    population: Population, policy: ChoicePolicy | None = None
) -> dict[str, Measures]:
    """
    Every arrangement on one population, keyed by arrangement. Outcome
    agreement is measured against the full-turnout reference.
    """
    reference = full_turnout(population)
    outcomes = [
        reference,
        direct(population),
        representative(population),
        proxy(population, policy),
        liquid(population, policy),
    ]
    return {o.arrangement: measure(population, o, reference) for o in outcomes}


__all__ = [
    "DEFAULT_CREDIBLE_MASS",
    "DIRECT",
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
    "PopulationConfig",
    "QuestionSet",
    "agreement",
    "agreement_counts",
    "choose",
    "choose_liquid",
    "choose_proxies",
    "compare",
    "delegation_network",
    "dimension_category",
    "direct",
    "elect_representatives",
    "fidelity_by_voter",
    "full_turnout",
    "liquid",
    "lower_bound",
    "measure",
    "proxy",
    "representative",
    "simulate_population",
]
