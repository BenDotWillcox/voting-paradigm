"""
Response scenarios: how a persona turns a true utility gap into slider evidence.

The simulators make the response process an explicit, swept-over sensitivity
axis. They resemble assumptions made by the fitted models without claiming an
exact generative match:

- ``gaussian_gap`` adds Gaussian noise to the latent gap before scaling and
  clipping it onto the slider. Its scale, clipping, and constant generative
  noise differ from the Gaussian model's normalized, strength-weighted
  observation likelihood.
- ``logistic_choice`` samples a temperature-scaled binary choice and reports a
  fixed slider magnitude. Its temperature and fixed evidence weight differ
  from the Bradley-Terry model's fitted likelihood.
- ``sloppy`` adds occasional random responses, tanh compression, and integer
  slider ticks as a deliberately stylized stress condition.

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

    This resembles a continuous Gaussian observation, but it is not an exact
    match for the fitted Gaussian model because scaling, clipping, and noise
    weighting differ. ``response_scale = 5`` maps the full [-2, 2] gap range
    onto the slider.
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

    This resembles a Bradley-Terry response process, but it is not an exact
    match for the fitted model because its temperature and fixed-magnitude
    evidence weight differ. Lower temperature means more deterministic
    choices.
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

    This is a stylized stress condition rather than a validated model of human
    response behavior.
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
