"""Pure-domain invariants for clipped asymmetric scalar utility."""

from __future__ import annotations

from dataclasses import replace

import pytest

from expressive.scalar import (
    InvalidScalarError,
    ScalarBallot,
    evaluate_scalar,
    preview_scalar,
    scalar_unclipped_score,
)


def ballot() -> ScalarBallot:
    return ScalarBallot(
        ideal=6,
        lower_half_width=2,
        upper_half_width=3,
        approval_min=2,
        approval_max=10,
    )


def test_peak_and_directional_half_score_landmarks() -> None:
    authored = ballot()
    assert evaluate_scalar(authored, 6).score == 1
    assert evaluate_scalar(authored, 4).score == pytest.approx(.5)
    assert evaluate_scalar(authored, 9).score == pytest.approx(.5)
    assert evaluate_scalar(authored, 8).score > evaluate_scalar(authored, 4).score


def test_approval_clips_only_outside_inclusive_bounds() -> None:
    authored = ballot()
    for value in [2.0, 10.0]:
        evaluated = evaluate_scalar(authored, value)
        assert evaluated.approved
        assert evaluated.score == scalar_unclipped_score(authored, value)
        assert evaluated.score > 0
    for value in [1.999, 10.001]:
        assert not evaluate_scalar(authored, value).approved
        assert evaluate_scalar(authored, value).score == 0
        assert scalar_unclipped_score(authored, value) > 0


def test_clipping_does_not_renormalize_surviving_scores() -> None:
    original = ballot()
    narrower = replace(original, approval_min=4, approval_max=7)
    assert evaluate_scalar(original, 4) == evaluate_scalar(narrower, 4)
    assert evaluate_scalar(original, 6).score == evaluate_scalar(narrower, 6).score == 1


def test_equal_approval_bounds_preserve_single_ideal_point() -> None:
    authored = ScalarBallot(3.333, 2, 4, 3.333, 3.333)
    assert evaluate_scalar(authored, 3.333).score == 1
    assert evaluate_scalar(authored, 3.333).approved
    for value in [3.332, 3.334]:
        assert evaluate_scalar(authored, value).score == 0
        assert not evaluate_scalar(authored, value).approved


def test_curve_grid_preserves_exact_anchor_and_half_width_values() -> None:
    authored = ScalarBallot(6.123, .007, .013, 2.234, 11.345)
    result = preview_scalar(authored, 4.456)
    values = [point.value for point in result.points]
    assert values == sorted(set(values))
    assert len(values) == 2007
    assert set(index / 20 for index in range(2001)).issubset(values)
    assert {6.123, 2.234, 11.345, 4.456}.issubset(values)
    scores = {point.value: point.unclipped_score for point in result.points}
    assert scores[authored.ideal] == 1
    assert scores[authored.ideal - authored.lower_half_width] == pytest.approx(.5)
    assert scores[authored.ideal + authored.upper_half_width] == pytest.approx(.5)
    assert result == preview_scalar(authored, 4.456)


def test_curve_samples_are_unclipped_even_when_probe_is_rejected() -> None:
    result = preview_scalar(ballot(), 1)
    assert result.probe.score == 0
    assert not result.probe.approved
    assert next(point.unclipped_score for point in result.points if point.value == 1) > 0


def test_policy_extremes_and_outside_half_width_landmarks() -> None:
    for ideal in [0, 100]:
        authored = ScalarBallot(ideal, 100, 100, 0, 100)
        result = preview_scalar(authored, ideal)
        assert result.probe.score == 1
        assert len(result.points) == 2001
        assert result.points[0].value == 0
        assert result.points[-1].value == 100


def test_broad_curve_and_clipping_across_the_full_tax_range() -> None:
    authored = ScalarBallot(80, 50, 20, 30, 100)
    assert evaluate_scalar(authored, 80).score == 1
    assert evaluate_scalar(authored, 30).score == pytest.approx(.5)
    assert evaluate_scalar(authored, 100).score == pytest.approx(.5)
    assert not evaluate_scalar(authored, 29.95).approved
    result = preview_scalar(authored, 95.123)
    assert result.probe.value == 95.123
    assert result.probe.score == scalar_unclipped_score(authored, 95.123)
    assert {80, 100, 95.123}.issubset({point.value for point in result.points})


@pytest.mark.parametrize("field", ["ideal", "lower_half_width", "upper_half_width", "approval_min", "approval_max"])
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), True])
def test_nonfinite_and_boolean_ballot_fields_rejected(field: str, invalid: float) -> None:
    with pytest.raises(InvalidScalarError):
        replace(ballot(), **{field: invalid})


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), True, -0.1, 100.1])
def test_invalid_probe_rejected(invalid: float) -> None:
    with pytest.raises(InvalidScalarError):
        preview_scalar(ballot(), invalid)


@pytest.mark.parametrize("changes", [
    {"approval_min": 7}, {"approval_max": 5}, {"approval_min": 10, "approval_max": 2},
    {"ideal": -1}, {"ideal": 101}, {"approval_min": -1}, {"approval_max": 101},
    {"lower_half_width": 0}, {"upper_half_width": -1}, {"upper_half_width": 101},
])
def test_invalid_domain_order_and_widths_rejected(changes: dict[str, float]) -> None:
    with pytest.raises(InvalidScalarError):
        replace(ballot(), **changes)


def test_very_narrow_positive_width_underflows_safely() -> None:
    authored = replace(ballot(), lower_half_width=1e-300, upper_half_width=1e-300)
    assert evaluate_scalar(authored, 6).score == 1
    assert evaluate_scalar(authored, 5).score == 0


def test_out_of_range_large_integer_is_a_domain_error() -> None:
    with pytest.raises(InvalidScalarError):
        replace(ballot(), ideal=10**400)
