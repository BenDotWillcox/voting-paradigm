"""
Synthetic personas: authored latent preference profiles used as eval ground
truth.

Each persona is a hand-authored utility vector over the fixed civic-value
bank, scaled to [-1, 1]. Personas answer pairwise questions through a seeded
noise model, so elicitation runs against them are fully reproducible and the
"true" ranking every metric compares against is known exactly.

These are eval fixtures, not simulated voters — when demo 2 needs LLM-generated
personas for electorate diversity, those live in the (future) `personas/`
package; this module stays small and deterministic.
"""

from dataclasses import dataclass

import numpy as np

from preferences.types import Evidence, EvidenceSource, ItemId


@dataclass(frozen=True)
class Persona:
    """A synthetic user with a known latent utility for every bank item."""

    name: str
    description: str
    utilities: dict[ItemId, float]

    def true_gap(self, item_a: ItemId, item_b: ItemId) -> float:
        """True utility gap u_a - u_b in [-2, 2]."""
        return self.utilities[item_a] - self.utilities[item_b]

    def true_ranking(self, item_ids: list[ItemId]) -> list[ItemId]:
        """Items sorted by true utility, best first (stable for ties)."""
        return sorted(item_ids, key=lambda i: (-self.utilities[i], i))


def simulate_response(
    persona: Persona,
    item_a: ItemId,
    item_b: ItemId,
    rng: np.random.Generator,
    noise_std: float = 0.3,
    response_scale: float = 5.0,
) -> Evidence:
    """Simulate the persona answering a pairwise slider question.

    Response model: the persona perceives the true gap plus Gaussian noise,
    then reports it on the [-10, 10] slider:
        value = clip((true_gap + N(0, noise_std^2)) * response_scale, -10, 10)

    `response_scale = 5` maps the full [-2, 2] gap range onto the slider.
    All stochasticity flows through the injected numpy Generator.
    """
    perceived = persona.true_gap(item_a, item_b) + float(
        rng.normal(0.0, noise_std)
    )
    value = float(np.clip(perceived * response_scale, -10.0, 10.0))
    return Evidence(
        source=EvidenceSource.PAIRWISE,
        item_a=item_a,
        item_b=item_b,
        value=value,
        confidence=1.0,
        metadata={"persona": persona.name},
    )


# ---------------------------------------------------------------------------
# Authored profiles (over preferences/questions/seed_items.json)
# ---------------------------------------------------------------------------

MARKET_LIBERTARIAN = Persona(
    name="market_libertarian",
    description=(
        "Strong economic and personal liberty; skeptical of regulation, "
        "redistribution, and precaution; pro-innovation."
    ),
    utilities={
        "economic_freedom": 0.90,
        "economic_security": -0.50,
        "market_efficiency": 0.80,
        "regulated_fairness": -0.60,
        "property_rights": 0.85,
        "collective_goods": -0.50,
        "local_control": 0.60,
        "national_standards": -0.50,
        "direct_democracy": 0.10,
        "expert_technocracy": -0.40,
        "rapid_action": 0.00,
        "careful_deliberation": 0.10,
        "institutional_trust": -0.20,
        "institutional_reform": 0.30,
        "personal_privacy": 0.80,
        "public_safety": -0.40,
        "individual_rights": 0.90,
        "community_cohesion": -0.30,
        "meritocracy": 0.70,
        "equal_outcomes": -0.60,
        "tradition": -0.10,
        "progressive_change": 0.20,
        "rehabilitation": 0.00,
        "strict_accountability": 0.30,
        "environmental_protection": -0.30,
        "economic_development": 0.60,
        "precautionary_principle": -0.60,
        "innovation_speed": 0.80,
        "open_borders": 0.40,
        "national_sovereignty": 0.00,
        "global_cooperation": -0.20,
        "self_reliance": 0.30,
        "transparency": 0.40,
        "operational_secrecy": -0.30,
        "ballot_privacy": 0.60,
        "public_accountability": 0.40,
    },
)

SOCIAL_DEMOCRAT = Persona(
    name="social_democrat",
    description=(
        "Egalitarian and internationalist; strong safety net, regulation, "
        "and collective goods; reform-minded and progressive."
    ),
    utilities={
        "economic_freedom": -0.30,
        "economic_security": 0.90,
        "market_efficiency": -0.40,
        "regulated_fairness": 0.85,
        "property_rights": -0.20,
        "collective_goods": 0.80,
        "local_control": -0.10,
        "national_standards": 0.60,
        "direct_democracy": 0.30,
        "expert_technocracy": 0.20,
        "rapid_action": 0.10,
        "careful_deliberation": 0.40,
        "institutional_trust": 0.10,
        "institutional_reform": 0.50,
        "personal_privacy": 0.40,
        "public_safety": 0.20,
        "individual_rights": 0.30,
        "community_cohesion": 0.50,
        "meritocracy": -0.30,
        "equal_outcomes": 0.85,
        "tradition": -0.40,
        "progressive_change": 0.80,
        "rehabilitation": 0.80,
        "strict_accountability": -0.40,
        "environmental_protection": 0.70,
        "economic_development": -0.20,
        "precautionary_principle": 0.50,
        "innovation_speed": -0.20,
        "open_borders": 0.60,
        "national_sovereignty": -0.50,
        "global_cooperation": 0.80,
        "self_reliance": -0.40,
        "transparency": 0.60,
        "operational_secrecy": -0.40,
        "ballot_privacy": 0.30,
        "public_accountability": 0.70,
    },
)

COMMUNITARIAN_TRADITIONALIST = Persona(
    name="communitarian_traditionalist",
    description=(
        "Localist and tradition-minded; high trust in community and "
        "established institutions, low appetite for rapid change or "
        "supranational projects."
    ),
    utilities={
        "economic_freedom": 0.10,
        "economic_security": 0.40,
        "market_efficiency": 0.00,
        "regulated_fairness": 0.20,
        "property_rights": 0.50,
        "collective_goods": 0.30,
        "local_control": 0.85,
        "national_standards": -0.60,
        "direct_democracy": 0.40,
        "expert_technocracy": -0.70,
        "rapid_action": -0.30,
        "careful_deliberation": 0.60,
        "institutional_trust": 0.70,
        "institutional_reform": -0.60,
        "personal_privacy": 0.30,
        "public_safety": 0.40,
        "individual_rights": -0.20,
        "community_cohesion": 0.90,
        "meritocracy": 0.20,
        "equal_outcomes": 0.00,
        "tradition": 0.90,
        "progressive_change": -0.80,
        "rehabilitation": -0.10,
        "strict_accountability": 0.60,
        "environmental_protection": 0.20,
        "economic_development": 0.30,
        "precautionary_principle": 0.30,
        "innovation_speed": -0.50,
        "open_borders": -0.70,
        "national_sovereignty": 0.85,
        "global_cooperation": -0.50,
        "self_reliance": 0.70,
        "transparency": 0.10,
        "operational_secrecy": 0.30,
        "ballot_privacy": 0.70,
        "public_accountability": 0.20,
    },
)

GREEN_TECHNOCRAT = Persona(
    name="green_technocrat",
    description=(
        "Expertise-driven environmentalist; strong precaution, global "
        "cooperation, and standardized policy; low attachment to tradition."
    ),
    utilities={
        "economic_freedom": -0.20,
        "economic_security": 0.50,
        "market_efficiency": 0.10,
        "regulated_fairness": 0.60,
        "property_rights": -0.10,
        "collective_goods": 0.60,
        "local_control": -0.30,
        "national_standards": 0.70,
        "direct_democracy": -0.50,
        "expert_technocracy": 0.90,
        "rapid_action": 0.30,
        "careful_deliberation": 0.50,
        "institutional_trust": 0.40,
        "institutional_reform": 0.30,
        "personal_privacy": 0.10,
        "public_safety": 0.60,
        "individual_rights": 0.00,
        "community_cohesion": 0.20,
        "meritocracy": 0.50,
        "equal_outcomes": 0.30,
        "tradition": -0.60,
        "progressive_change": 0.70,
        "rehabilitation": 0.50,
        "strict_accountability": 0.10,
        "environmental_protection": 0.95,
        "economic_development": -0.50,
        "precautionary_principle": 0.80,
        "innovation_speed": 0.20,
        "open_borders": 0.20,
        "national_sovereignty": -0.30,
        "global_cooperation": 0.90,
        "self_reliance": -0.50,
        "transparency": 0.70,
        "operational_secrecy": 0.00,
        "ballot_privacy": 0.20,
        "public_accountability": 0.60,
    },
)

DEFAULT_PERSONAS: tuple[Persona, ...] = (
    MARKET_LIBERTARIAN,
    SOCIAL_DEMOCRAT,
    COMMUNITARIAN_TRADITIONALIST,
    GREEN_TECHNOCRAT,
)
