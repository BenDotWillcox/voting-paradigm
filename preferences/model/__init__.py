"""
Preference models and the registry that maps names/versions to classes.

Registered models:
    gaussian_linear — exact conjugate Gaussian linear utility model.
    bradley_terry   — Bradley-Terry logistic likelihood + Laplace posterior.
"""

from .base import PreferenceModel
from .bradley_terry import BradleyTerryLaplaceModel
from .gaussian_linear import GaussianLinearUtilityModel

MODEL_REGISTRY: dict[str, type] = {
    "gaussian_linear": GaussianLinearUtilityModel,
    "bradley_terry": BradleyTerryLaplaceModel,
}

DEFAULT_MODEL_NAME = "gaussian_linear"

# model_version prefixes -> registry names, including legacy versions.
# "thurstone_v1" states were produced by the mis-named predecessor of the
# Gaussian linear model; the math is identical, so they resume seamlessly.
_VERSION_TO_NAME = {
    "gaussian_linear": "gaussian_linear",
    "thurstone": "gaussian_linear",
    "bradley_terry": "bradley_terry",
}


def create_model(
    name: str = DEFAULT_MODEL_NAME, **hyperparams: float
) -> PreferenceModel:
    """Instantiate a registered model by name.

    Keyword arguments override the model's default hyperparameters (e.g.
    ``prior_variance``); the eval harness uses this for sensitivity sweeps.
    """
    try:
        cls = MODEL_REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unknown preference model '{name}'. "
            f"Available: {sorted(MODEL_REGISTRY)}"
        ) from None
    return cls(**hyperparams)  # type: ignore[no-any-return]


def model_for_version(model_version: str) -> PreferenceModel:
    """Instantiate the model that owns a serialized state's model_version."""
    for prefix, name in _VERSION_TO_NAME.items():
        if model_version.startswith(prefix):
            return create_model(name)
    raise ValueError(f"No model registered for model_version '{model_version}'")


__all__ = [
    "PreferenceModel",
    "GaussianLinearUtilityModel",
    "BradleyTerryLaplaceModel",
    "MODEL_REGISTRY",
    "DEFAULT_MODEL_NAME",
    "create_model",
    "model_for_version",
]
