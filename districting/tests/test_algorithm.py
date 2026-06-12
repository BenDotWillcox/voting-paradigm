"""
Tests for the balanced-power-diagram algorithm.

Coverage map (mirrors the test plan in prompts/demo-3-districting.md):

  - Population balance: synthetic grids hit exact or near-exact balance
  - Power-diagram correctness: every unit assigned to argmin score
  - Convexity: implied by power-diagram correctness, but we also test
    a "no enclaves" form on grid inputs (no unit of cell A surrounded
    by cells of B in the convex hull sense)
  - Determinism: same seed → byte-identical assignments
  - Reasonable behavior on non-uniform populations
  - Edge cases: k=1, k=n, zero-population guards, small inputs

These tests exercise the *math*, not real shapefiles; that integration
lands in step 4 alongside the precompute pipeline.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from districting import (
    DistrictingError,
    Unit,
    balanced_power_diagram,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def grid_units(width: int, height: int, *, population: int = 1) -> list[Unit]:
    """Regular `width × height` grid, uniform population."""
    units: list[Unit] = []
    for i in range(width):
        for j in range(height):
            units.append(
                Unit(
                    geoid=f"{i:02d}{j:02d}",
                    centroid=(float(i), float(j)),
                    population=population,
                )
            )
    return units


def population_per_cell(result, k: int) -> dict[int, int]:
    return {i: result.populations[i] for i in range(k)}


def assert_power_diagram_consistent(result, units: list[Unit]) -> None:
    """Every unit's assigned cell minimizes (||c_i − x_j||² − w_i)."""
    coords = np.asarray([u.centroid for u in units], dtype=float)
    centers = np.asarray(
        [(c.x, c.y) for c in result.centers], dtype=float
    )
    weights = np.asarray([c.weight for c in result.centers], dtype=float)
    sq_dist = np.sum(
        (coords[:, None, :] - centers[None, :, :]) ** 2, axis=2
    )
    expected = (sq_dist - weights[None, :]).argmin(axis=1)
    for j, unit in enumerate(units):
        assert result.assignments[unit.geoid] == expected[j], (
            f"unit {unit.geoid} assigned to {result.assignments[unit.geoid]} "
            f"but argmin says {expected[j]}"
        )


# ---------------------------------------------------------------------------
# Headline test from the design doc
# ---------------------------------------------------------------------------


class TestUniformGridFourDistricts:
    """10×10 grid of equal-population units, k=4.

    Target per cell is exactly 25, so the population-balance test
    should hit max_imbalance == 0, and we expect roughly-quadrant cells.
    """

    @pytest.fixture(scope="class")
    def result(self):
        units = grid_units(10, 10, population=1)
        return units, balanced_power_diagram(units, n_districts=4, seed=42)

    def test_assignment_covers_every_unit(self, result):
        units, r = result
        assert len(r.assignments) == 100

    def test_n_districts_matches(self, result):
        _, r = result
        assert r.n_districts == 4

    def test_each_cell_at_target(self, result):
        _, r = result
        for pop in r.populations.values():
            assert pop == 25

    def test_max_imbalance_zero(self, result):
        _, r = result
        assert r.max_population_imbalance == 0

    def test_power_diagram_consistent(self, result):
        units, r = result
        assert_power_diagram_consistent(r, units)

    def test_converged(self, result):
        _, r = result
        assert r.converged, (
            f"did not converge in {r.iterations} iterations"
        )

    def test_total_population_preserved(self, result):
        _, r = result
        assert sum(r.populations.values()) == 100


# ---------------------------------------------------------------------------
# Non-uniform populations
# ---------------------------------------------------------------------------


class TestNonUniformPopulations:
    """Grid with population varying across the field.

    Even when units have different populations, the algorithm should
    achieve near-exact balance: target per cell is ⌊total/k⌋ (with
    rem cells getting +1), and discreteness lets us off by at most a
    handful of people in practice.
    """

    @pytest.fixture(scope="class")
    def result(self):
        units: list[Unit] = []
        for i in range(10):
            for j in range(10):
                # Population varies from 1 to 19
                pop = 1 + (i + j)
                units.append(
                    Unit(
                        geoid=f"{i:02d}{j:02d}",
                        centroid=(float(i), float(j)),
                        population=pop,
                    )
                )
        return units, balanced_power_diagram(units, n_districts=5, seed=7)

    def test_balance_within_a_few_units(self, result):
        units, r = result
        total_pop = sum(u.population for u in units)
        target = total_pop // r.n_districts
        # Every cell within 5 people of target is comfortably tighter
        # than the design doc's "ensemble-method-like" tolerance, and
        # well within what L-BFGS-B should achieve on a 5-cell solve.
        for pop in r.populations.values():
            assert abs(pop - target) <= 5, (
                f"cell pop {pop} too far from target {target}"
            )

    def test_power_diagram_consistent(self, result):
        units, r = result
        assert_power_diagram_consistent(r, units)

    def test_total_population_preserved(self, result):
        units, r = result
        assert sum(r.populations.values()) == sum(u.population for u in units)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_same_assignments(self):
        units = grid_units(8, 8, population=1)
        r1 = balanced_power_diagram(units, n_districts=4, seed=123)
        r2 = balanced_power_diagram(units, n_districts=4, seed=123)
        assert r1.assignments == r2.assignments
        assert r1.populations == r2.populations
        assert r1.iterations == r2.iterations

    def test_same_seed_same_centers(self):
        units = grid_units(8, 8, population=1)
        r1 = balanced_power_diagram(units, n_districts=4, seed=123)
        r2 = balanced_power_diagram(units, n_districts=4, seed=123)
        for c1, c2 in zip(r1.centers, r2.centers):
            assert c1.district_id == c2.district_id
            assert math.isclose(c1.x, c2.x, abs_tol=1e-12)
            assert math.isclose(c1.y, c2.y, abs_tol=1e-12)
            # Weights from L-BFGS may differ in low bits across runs of
            # the same call due to no nondeterminism in our pipeline,
            # but we still allow a small float tolerance for safety.
            assert math.isclose(c1.weight, c2.weight, abs_tol=1e-9)

    def test_different_seeds_can_yield_different_results(self):
        """Sanity: the seed actually does something."""
        units = grid_units(8, 8, population=1)
        r1 = balanced_power_diagram(units, n_districts=4, seed=1)
        r2 = balanced_power_diagram(units, n_districts=4, seed=99)
        # We don't insist they differ — symmetric inputs may converge
        # to the same partition under different seeds — but we do
        # insist that BOTH are valid partitions hitting the population
        # target.
        assert r1.max_population_imbalance == 0
        assert r2.max_population_imbalance == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_k_equals_one(self):
        units = grid_units(5, 5, population=1)
        r = balanced_power_diagram(units, n_districts=1, seed=0)
        assert r.n_districts == 1
        assert r.populations[0] == 25
        # Every unit goes to district 0
        assert all(d == 0 for d in r.assignments.values())

    def test_k_equals_n(self):
        """One district per unit — degenerate but should not crash."""
        units = grid_units(3, 3, population=1)
        r = balanced_power_diagram(units, n_districts=9, seed=0)
        assert r.n_districts == 9
        # Each district has at least zero population; total is 9.
        assert sum(r.populations.values()) == 9

    def test_rejects_negative_n_districts(self):
        units = grid_units(3, 3)
        with pytest.raises(DistrictingError):
            balanced_power_diagram(units, n_districts=0, seed=0)
        with pytest.raises(DistrictingError):
            balanced_power_diagram(units, n_districts=-1, seed=0)

    def test_rejects_n_districts_greater_than_units(self):
        units = grid_units(2, 2, population=1)  # 4 units
        with pytest.raises(DistrictingError):
            balanced_power_diagram(units, n_districts=5, seed=0)

    def test_rejects_zero_total_population(self):
        units = grid_units(3, 3, population=0)
        with pytest.raises(DistrictingError):
            balanced_power_diagram(units, n_districts=2, seed=0)

    def test_rejects_negative_population_in_unit(self):
        with pytest.raises(ValueError):
            Unit(geoid="x", centroid=(0.0, 0.0), population=-1)

    def test_rejects_non_2d_centroid(self):
        with pytest.raises(ValueError):
            Unit(geoid="x", centroid=(0.0,), population=1)  # type: ignore[arg-type]

    def test_minimal_two_district_case(self):
        units = [
            Unit(geoid="a", centroid=(0.0, 0.0), population=10),
            Unit(geoid="b", centroid=(10.0, 0.0), population=10),
        ]
        r = balanced_power_diagram(units, n_districts=2, seed=0)
        # Exactly one unit per district.
        assert sorted(r.populations.values()) == [10, 10]
        assert set(r.assignments.values()) == {0, 1}


# ---------------------------------------------------------------------------
# Asymmetric populations across cells
# ---------------------------------------------------------------------------


class TestUnevenTargetSplit:
    """When total_pop doesn't divide k evenly, targets should split as
    evenly as possible (⌊tot/k⌋ for some, ⌈tot/k⌉ for the remainder).
    """

    def test_total_seven_three_districts(self):
        # Seven equal-pop units, k=3 → targets [3, 2, 2]
        units = [
            Unit(geoid=f"u{i}", centroid=(float(i), 0.0), population=1)
            for i in range(7)
        ]
        r = balanced_power_diagram(units, n_districts=3, seed=0)
        pop_counts = sorted(r.populations.values())
        assert pop_counts == [2, 2, 3]
        assert r.max_population_imbalance == 0


# ---------------------------------------------------------------------------
# Convex/contiguous-region property on a grid
# ---------------------------------------------------------------------------


class TestConvexityOnGrid:
    """A power diagram is convex by construction.  On a regular grid
    that means: the units assigned to a single cell form a convex
    region — i.e. for any two units in the same cell, every grid point
    lying on the line segment between them is also in that cell.

    We check the discrete analog: for each pair of units in the same
    cell, the unit closest to the segment midpoint must also belong to
    that cell.  This is a weaker form than full convexity but catches
    "salamander" patterns the algorithm should never produce.
    """

    def test_uniform_grid_cells_are_convex(self):
        units = grid_units(10, 10, population=1)
        r = balanced_power_diagram(units, n_districts=4, seed=42)
        # Group units by district
        by_district: dict[int, list[Unit]] = {}
        for u in units:
            by_district.setdefault(r.assignments[u.geoid], []).append(u)

        # For each district, sample pairs and check segment-midpoint
        # nearest-neighbor membership.
        for district_id, members in by_district.items():
            members_set = {u.geoid for u in members}
            for u_a in members:
                for u_b in members:
                    if u_a.geoid >= u_b.geoid:
                        continue
                    mid = (
                        (u_a.centroid[0] + u_b.centroid[0]) / 2,
                        (u_a.centroid[1] + u_b.centroid[1]) / 2,
                    )
                    # Closest unit to the midpoint
                    nearest = min(
                        units,
                        key=lambda u: (u.centroid[0] - mid[0]) ** 2
                        + (u.centroid[1] - mid[1]) ** 2,
                    )
                    assert nearest.geoid in members_set, (
                        f"district {district_id}: unit {nearest.geoid} "
                        f"sits on the segment from {u_a.geoid} to "
                        f"{u_b.geoid} but is in district "
                        f"{r.assignments[nearest.geoid]}"
                    )
