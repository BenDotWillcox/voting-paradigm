"""
Response models: how a persona turns a true utility gap into slider evidence.

The original harness had exactly one response model — Gaussian noise on the
continuous gap — which is the Gaussian linear model's own likelihood. Any
comparison run under it alone hands the Gaussian model a rigged game. These
simulators make the generative assumption an explicit, swept-over choice so
the model comparison becomes a misspecification study:

- ``gaussian_gap``    matches GaussianLinearUtilityModel's likelihood.
- ``logistic_choice`` matches BradleyTerryLaplaceModel's likelihood: only the
  *direction* is stochastic (Bernoulli through a logistic link); the reported
  magnitude carries no extra signal.
- ``sloppy``          matches neither: occasional lapses (random answers),
  tanh compression of perceived gaps, and integer slider ticks — a stylized
  "real human on a slider" model.

All randomness flows through the injected numpy Generator; a response model
instance is stateless, so trials stay byte-deterministic given the seed.
"""

from dataclasses import dataclass

import numpy as np

from preferences.types import Evidence, EvidenceSource, ItemId

from .personas import Persona


def _pairwise_evidence(
    persona: Persona, item_a: ItemId, item_b: ItemId, value: float
) -> Evidence:
    return Evidence(
        source=EvidenceSource.PAIRWISE,
        item_a=item_a,
        item_b=item_b,
        value=float(value),
        confidence=1.0,
        metadata={"persona": persona.name},
    )


@dataclass(frozen=True)
class GaussianGapResponseModel:
    """Slider value is a noisy continuous reading of the true gap.

    value = clip((gap + N(0, noise_std^2)) * response_scale, -10, 10)

    This is exactly the observation model the Gaussian linear utility model
    assumes, so under this simulator that model is correctly specified.
    ``response_scale = 5`` maps the full [-2, 2] gap range onto the slider.
    """

    noise_std: float = 0.3
    response_scale: float = 5.0

    name = "gaussian_gap"

    def respond(
        self,
        persona: Persona,
        item_a: ItemId,
        item_b: ItemId,
        rng: np.random.Generator,
    ) -> Evidence:
        perceived = persona.true_gap(item_a, item_b) + float(
            rng.normal(0.0, self.noise_std)
        )
        value = float(np.clip(perceived * self.response_scale, -10.0, 10.0))
        return _pairwise_evidence(persona, item_a, item_b, value)


@dataclass(frozen=True)
class LogisticChoiceResponseModel:
    """Only the choice direction is informative; magnitude is a constant.

    P(prefer a) = sigmoid(gap / temperature); value = +/- magnitude.

    This is Bradley-Terry's generative assumption, so under this simulator
    the BT model is correctly specified and the Gaussian model is fitting a
    continuous observation that never varies in size. Lower temperature =
    more deterministic choices.
    """

    temperature: float = 0.5
    magnitude: float = 5.0

    name = "logistic_choice"

    def respond(
        self,
        persona: Persona,
        item_a: ItemId,
        item_b: ItemId,
        rng: np.random.Generator,
    ) -> Evidence:
        gap = persona.true_gap(item_a, item_b)
        p_prefer_a = 1.0 / (1.0 + np.exp(-gap / self.temperature))
        chose_a = bool(rng.random() < p_prefer_a)
        value = self.magnitude if chose_a else -self.magnitude
        return _pairwise_evidence(persona, item_a, item_b, value)


@dataclass(frozen=True)
class SloppyResponseModel:
    """A stylized careless human: lapses, compression, and coarse ticks.

    With probability ``lapse_rate`` the answer is uniform noise (attention
    lapse). Otherwise the perceived gap is noisy and tanh-compressed —
    moderate preferences cluster mid-slider and only extreme gaps reach the
    ends — then rounded to integer slider ticks.

    Neither model's likelihood matches this; it measures graceful
    degradation under realistic misspecification.
    """

    noise_std: float = 0.3
    gain: float = 1.5
    lapse_rate: float = 0.1

    name = "sloppy"

    def respond(
        self,
        persona: Persona,
        item_a: ItemId,
        item_b: ItemId,
        rng: np.random.Generator,
    ) -> Evidence:
        if rng.random() < self.lapse_rate:
            value = float(rng.integers(-10, 11))
            return _pairwise_evidence(persona, item_a, item_b, value)
        perceived = persona.true_gap(item_a, item_b) + float(
            rng.normal(0.0, self.noise_std)
        )
        compressed = float(np.tanh(perceived * self.gain)) * 10.0
        value = float(np.clip(round(compressed), -10, 10))
        return _pairwise_evidence(persona, item_a, item_b, value)


RESPONSE_MODEL_REGISTRY: dict[str, type] = {
    GaussianGapResponseModel.name: GaussianGapResponseModel,
    LogisticChoiceResponseModel.name: LogisticChoiceResponseModel,
    SloppyResponseModel.name: SloppyResponseModel,
}

DEFAULT_RESPONSE_MODEL_NAME = GaussianGapResponseModel.name


def create_response_model(
    name: str = DEFAULT_RESPONSE_MODEL_NAME, **params: float
):
    """Instantiate a registered response model by name."""
    try:
        cls = RESPONSE_MODEL_REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unknown response model '{name}'. "
            f"Available: {sorted(RESPONSE_MODEL_REGISTRY)}"
        ) from None
    return cls(**params)
