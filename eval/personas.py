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

from preferences.types import ItemId


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


# ---------------------------------------------------------------------------
# Generated populations
# ---------------------------------------------------------------------------


def generate_personas(
    n: int,
    seed: int,
    archetypes: tuple[Persona, ...] = DEFAULT_PERSONAS,
    concentration: float = 0.5,
    jitter_std: float = 0.15,
) -> list[Persona]:
    """Generate a seeded population of structured synthetic personas.

    Each persona is a Dirichlet-weighted mixture of the authored archetype
    profiles plus per-item Gaussian jitter, clipped to [-1, 1]:

        u = clip(sum_k w_k * archetype_k + N(0, jitter_std^2), -1, 1),
        w ~ Dirichlet(concentration * 1)

    Mixing archetypes (rather than sampling items independently) preserves
    the correlated value structure real populations have — someone high on
    economic_freedom is unlikely to also be high on collective_goods,
    because no archetype is. ``concentration`` controls archetype purity:
    values < 1 concentrate mass near single archetypes (a polarized
    population); larger values produce centrist blends. Jitter adds
    idiosyncratic variation so no generated persona is a pure mixture.

    Deterministic given (n, seed, archetypes, concentration, jitter_std).
    The mixture weights are recorded in each persona's description for
    auditability.
    """
    if not archetypes:
        raise ValueError("generate_personas requires at least one archetype")
    item_ids = list(archetypes[0].utilities.keys())
    for arch in archetypes[1:]:
        if set(arch.utilities.keys()) != set(item_ids):
            raise ValueError(
                f"Archetype '{arch.name}' does not share the item universe "
                f"of '{archetypes[0].name}'"
            )

    profile_matrix = np.array(
        [[arch.utilities[i] for i in item_ids] for arch in archetypes]
    )  # shape (n_archetypes, n_items)

    rng = np.random.default_rng(seed)
    personas: list[Persona] = []
    for k in range(n):
        weights = rng.dirichlet(concentration * np.ones(len(archetypes)))
        base = weights @ profile_matrix
        jitter = rng.normal(0.0, jitter_std, size=len(item_ids))
        utilities = np.clip(base + jitter, -1.0, 1.0)
        mixture = ", ".join(
            f"{arch.name}={w:.2f}" for arch, w in zip(archetypes, weights)
        )
        personas.append(
            Persona(
                name=f"gen_s{seed}_{k:03d}",
                description=f"Generated mixture: {mixture}",
                utilities=dict(zip(item_ids, utilities.tolist())),
            )
        )
    return personas
