"""A directly authored scalar utility curve with inclusive approval clipping.

The theoretical policy domain is a 0--100 percent income-tax rate.
Directional half-widths express tolerance, not uncertainty. Clipping changes
only values outside the approval band; the remaining curve is not renormalized.
An individual approval flag is not a collective exclusion or veto.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

SCALAR_DOMAIN_MIN = 0.0
SCALAR_DOMAIN_MAX = 100.0
SCALAR_MODEL_VERSION: Literal["clipped-asymmetric-gaussian-v2"] = "clipped-asymmetric-gaussian-v2"


class InvalidScalarError(ValueError):
    """A scalar ballot or probe is outside the explicitly supported contract."""


def _finite_number(value: float, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidScalarError(f"{label} must be a finite number.")
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidScalarError(f"{label} must be a finite number.")


def _policy_value(value: float, label: str) -> None:
    _finite_number(value, label)
    if not SCALAR_DOMAIN_MIN <= value <= SCALAR_DOMAIN_MAX:
        raise InvalidScalarError(f"{label} must lie between 0 and 100 percent.")


@dataclass(frozen=True)
class ScalarBallot:
    ideal: float
    lower_half_width: float
    upper_half_width: float
    approval_min: float
    approval_max: float

    def __post_init__(self) -> None:
        _policy_value(self.ideal, "Ideal")
        _policy_value(self.approval_min, "Approval minimum")
        _policy_value(self.approval_max, "Approval maximum")
        if not self.approval_min <= self.ideal <= self.approval_max:
            raise InvalidScalarError("Approval bounds must contain the ideal rate.")
        for name, value in (
            ("Lower half-width", self.lower_half_width),
            ("Upper half-width", self.upper_half_width),
        ):
            _finite_number(value, name)
            if not 0 < value <= SCALAR_DOMAIN_MAX:
                raise InvalidScalarError(f"{name} must be greater than 0 and at most 100 percentage points.")


@dataclass(frozen=True)
class ScalarCurvePoint:
    value: float
    unclipped_score: float


@dataclass(frozen=True)
class ScalarProbe:
    value: float
    score: float
    approved: bool


@dataclass(frozen=True)
class ScalarPreview:
    points: tuple[ScalarCurvePoint, ...]
    probe: ScalarProbe


def scalar_unclipped_score(ballot: ScalarBallot, value: float) -> float:
    """Evaluate the authored taper at a policy value before approval clipping."""
    _policy_value(value, "Policy value")
    delta = value - ballot.ideal
    width = ballot.lower_half_width if delta < 0 else ballot.upper_half_width
    ratio = abs(delta) / width
    return 0.0 if ratio > 40 else math.exp(-math.log(2) * ratio * ratio)


def evaluate_scalar(ballot: ScalarBallot, value: float) -> ScalarProbe:
    """Evaluate a policy outcome; both approval endpoints remain approved."""
    _policy_value(value, "Probe")
    approved = ballot.approval_min <= value <= ballot.approval_max
    return ScalarProbe(
        value=value,
        score=scalar_unclipped_score(ballot, value) if approved else 0.0,
        approved=approved,
    )


def preview_scalar(ballot: ScalarBallot, probe: float) -> ScalarPreview:
    """Return a deterministic grid plus exact anchors for plotting and probing.

    Curve samples are deliberately unclipped so the frontend can depict the
    removed tails and the discontinuity at each approval boundary. The probe's
    explicit score follows the clipped function, including a zero-width band.
    """
    evaluation = evaluate_scalar(ballot, probe)
    values = {index / 20 for index in range(int(SCALAR_DOMAIN_MAX * 20) + 1)}
    values.update((ballot.ideal, ballot.approval_min, ballot.approval_max, probe))
    for landmark in (
        ballot.ideal - ballot.lower_half_width,
        ballot.ideal + ballot.upper_half_width,
    ):
        if SCALAR_DOMAIN_MIN <= landmark <= SCALAR_DOMAIN_MAX:
            values.add(landmark)
    return ScalarPreview(
        points=tuple(
            ScalarCurvePoint(value=value, unclipped_score=scalar_unclipped_score(ballot, value))
            for value in sorted(values)
        ),
        probe=evaluation,
    )
