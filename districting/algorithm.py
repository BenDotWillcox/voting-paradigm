"""
Balanced power diagrams for redistricting.

Implementation of the algorithm of Cohen-Addad, Klein, and Young (2017),
arXiv:1710.03358 — *Balanced Power Diagrams for Redistricting*.

------------------------------------------------------------------------
Problem
------------------------------------------------------------------------
Given a state's population units (e.g. census tracts) — each with a 2D
centroid `x_j` and population `p_j` — partition them into `k` districts
of nearly-equal population, with cells that are convex by construction.

------------------------------------------------------------------------
Algorithm (constrained Lloyd iteration)
------------------------------------------------------------------------

Outer loop, until the cell centers stop moving:

    1. Initialize `k` centers `c_i` via population-weighted k-means++.
    2. Inner solve: find additive weights `w_i` such that the
       power-diagram assignment
           j → argmin_i (||c_i − x_j||² − w_i)
       gives every cell exactly its target population
       `target_i ≈ total_pop / k`.
    3. Move each center to the population-weighted centroid of its
       cell.
    4. Repeat from step 2.

The cells are convex polyhedra at every step because any power diagram
(additively-weighted Voronoi) is convex by construction; the
contiguity of the cells follows for free at the resolution of our
input units.

------------------------------------------------------------------------
Inner solve (semi-discrete optimal transport)
------------------------------------------------------------------------

For fixed centers, finding weights that balance populations is the
classical semi-discrete OT problem with squared-Euclidean cost.  Its
Kantorovich dual is the concave potential

    D(w) = ∑_j p_j · min_i (||c_i − x_j||² − w_i) + ∑_i target_i · w_i

with gradient (where defined)

    ∂D/∂w_i = target_i − pop_assigned_to_cell_i.

At the optimum every cell holds exactly its target.  We maximize D by
minimizing −D with `scipy.optimize.minimize(method='L-BFGS-B')`.  The
potential is piecewise linear so the gradient is piecewise constant;
L-BFGS handles this well in practice for the OT setting (it is what
Mérigot and others use in production OT solvers).

------------------------------------------------------------------------
Boundaries (what this code does *not* try to do)
------------------------------------------------------------------------

The algorithm is geometry-only.  It does NOT enforce: respect for
political boundaries (counties, municipalities), Voting Rights Act
compliance (majority-minority districts), communities of interest, or
partisan-fairness targets.  The demo's writeup is honest about this —
the point is to show what *purely geometric* fairness looks like, not
to ship a deployable plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import minimize


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    """A single population unit (census tract, block group, etc.).

    The algorithm only consumes the centroid and population.  Polygons
    are intentionally not on this dataclass: they belong to the
    presentation layer (step 4+ wires real shapefiles) and the math is
    cleaner without them.
    """

    geoid: str
    centroid: tuple[float, float]
    population: int

    def __post_init__(self) -> None:
        if self.population < 0:
            raise ValueError(
                f"Unit {self.geoid!r} has negative population {self.population}."
            )
        if len(self.centroid) != 2:
            raise ValueError(
                f"Unit {self.geoid!r} centroid must be 2D; got {self.centroid!r}."
            )


@dataclass(frozen=True)
class DistrictCenter:
    """A power-diagram cell: its center plus its additive weight."""

    district_id: int
    x: float
    y: float
    weight: float


@dataclass(frozen=True)
class DistrictingResult:
    """Full output of one districting run."""

    centers: tuple[DistrictCenter, ...]
    """One DistrictCenter per district, indexed by `district_id`."""

    assignments: Mapping[str, int]
    """Map from `Unit.geoid` to the district_id it was placed in."""

    populations: Mapping[int, int]
    """Total population per district_id.  Sums to total input population."""

    iterations: int
    """Number of outer Lloyd iterations performed."""

    converged: bool
    """True iff the outer loop stopped because centers stabilized below
    `center_tol`, rather than hitting `max_outer_iterations`."""

    max_population_imbalance: int
    """Largest |population_i − target_i| across cells, in people.  This
    is the headline quality number — the design doc target is ≤ 1 unit
    in synthetic tests, single-digit in real ones."""

    @property
    def n_districts(self) -> int:
        return len(self.centers)


class DistrictingError(ValueError):
    """Raised for invalid districting inputs."""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def balanced_power_diagram(
    units: Sequence[Unit],
    n_districts: int,
    *,
    seed: int = 0,
    max_outer_iterations: int = 50,
    center_tol: float = 1e-4,
    inner_max_iterations: int = 200,
) -> DistrictingResult:
    """
    Partition `units` into `n_districts` districts of nearly-equal
    population using the balanced-power-diagram algorithm.

    Parameters
    ----------
    units :
        Population units to partition.  Length must be ≥ ``n_districts``.
        Total population must be positive.
    n_districts :
        Number of districts to produce.  Must be ≥ 1.
    seed :
        RNG seed for the k-means++ initialization.  Everything else in
        the algorithm is deterministic, so given the same seed and the
        same input the result is byte-identical.
    max_outer_iterations :
        Cap on the outer Lloyd loop.  50 is plenty for state-sized
        inputs in practice.
    center_tol :
        Outer-loop convergence tolerance.  When the largest center
        movement (Euclidean) falls below this, we stop.
    inner_max_iterations :
        Cap on the L-BFGS-B inner balance solve, per outer iteration.

    Returns
    -------
    DistrictingResult
        See dataclass docstring for what's in it.

    Raises
    ------
    DistrictingError
        For invalid inputs (negative `n_districts`, fewer units than
        districts, zero total population, etc.).
    """
    # --- Validate ------------------------------------------------------
    if n_districts < 1:
        raise DistrictingError(
            f"n_districts must be ≥ 1; got {n_districts}."
        )
    if len(units) < n_districts:
        raise DistrictingError(
            f"Need at least n_districts={n_districts} units; got {len(units)}."
        )

    coords = np.asarray([u.centroid for u in units], dtype=float)
    pops = np.asarray([u.population for u in units], dtype=float)
    geoids = [u.geoid for u in units]
    n = len(units)
    k = n_districts

    total_pop = int(pops.sum())
    if total_pop <= 0:
        raise DistrictingError(
            f"Total population must be positive; got {total_pop}."
        )

    # Targets per cell: spread total_pop as evenly as possible.  When
    # total_pop doesn't divide evenly, the first `rem` cells get one
    # extra person.  Ordering is stable wrt district_id.
    base, rem = divmod(total_pop, k)
    targets = np.full(k, base, dtype=float)
    targets[:rem] += 1.0
    assert int(targets.sum()) == total_pop  # invariant

    # --- Initialize centers --------------------------------------------
    rng = np.random.default_rng(seed)
    centers = _kmeans_pp_init(coords, pops, k, rng)
    weights = np.zeros(k)

    # --- Outer Lloyd loop ----------------------------------------------
    converged = False
    iteration = 0
    assignments = np.zeros(n, dtype=np.int64)  # final values set by inner solve
    for iteration in range(1, max_outer_iterations + 1):
        weights, assignments = _balance_weights(
            centers,
            coords,
            pops,
            targets,
            weights_init=weights,
            max_iter=inner_max_iterations,
        )
        new_centers = _population_weighted_centroids(
            coords, pops, assignments, k, fallback=centers
        )
        max_move = float(np.max(np.linalg.norm(new_centers - centers, axis=1)))
        centers = new_centers
        if max_move < center_tol:
            converged = True
            break

    # Final balance pass at the converged centers — the centroid update
    # in the last iteration may have shifted the cell boundaries enough
    # that the previous weights are no longer optimal.
    weights, assignments = _balance_weights(
        centers, coords, pops, targets,
        weights_init=weights, max_iter=inner_max_iterations,
    )

    # --- Build result --------------------------------------------------
    pop_assigned = np.bincount(assignments, weights=pops, minlength=k).astype(int)
    max_imbalance = int(np.max(np.abs(pop_assigned - targets.astype(np.int64))))

    return DistrictingResult(
        centers=tuple(
            DistrictCenter(
                district_id=i,
                x=float(centers[i, 0]),
                y=float(centers[i, 1]),
                weight=float(weights[i]),
            )
            for i in range(k)
        ),
        assignments={geoids[j]: int(assignments[j]) for j in range(n)},
        populations={i: int(pop_assigned[i]) for i in range(k)},
        iterations=iteration,
        converged=converged,
        max_population_imbalance=max_imbalance,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _kmeans_pp_init(
    coords: np.ndarray,
    pops: np.ndarray,
    k: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Population-weighted k-means++ initialization.

    Standard k-means++ but with the first-center distribution and the
    distance-squared distribution both *weighted by population* — so a
    densely populated area is more likely to host a center, which is
    what we want for redistricting (avoids placing initial centers in
    sparsely-populated geography).
    """
    n = coords.shape[0]
    if k > n:
        raise DistrictingError(
            f"k-means++: need k ≤ n; got k={k}, n={n}."
        )

    pop_total = float(pops.sum())
    if pop_total <= 0:
        raise DistrictingError("k-means++: total population is non-positive.")

    chosen_indices: list[int] = []

    # First center: pick a unit with probability proportional to its
    # population.
    first_probs = pops / pop_total
    chosen_indices.append(int(rng.choice(n, p=first_probs)))

    # Squared distance from each unit to the nearest chosen center so
    # far.  Initialize from the first center.
    dist_sq = np.sum((coords - coords[chosen_indices[0]]) ** 2, axis=1)

    for _ in range(1, k):
        weighted = pops * dist_sq
        total = float(weighted.sum())
        if total <= 0:
            # Degenerate: every remaining unit either has population 0
            # or coincides with an already-chosen center.  Pick any
            # not-yet-chosen index uniformly to keep the algorithm
            # well-defined.
            remaining = [i for i in range(n) if i not in set(chosen_indices)]
            if not remaining:
                break  # k > n was checked above; should not happen
            chosen_indices.append(int(rng.choice(remaining)))
        else:
            probs = weighted / total
            chosen_indices.append(int(rng.choice(n, p=probs)))

        new_idx = chosen_indices[-1]
        new_dist_sq = np.sum((coords - coords[new_idx]) ** 2, axis=1)
        dist_sq = np.minimum(dist_sq, new_dist_sq)

    centers = coords[chosen_indices].astype(float)
    # Defensive copy — caller mutates centers in place each iteration.
    return centers.copy()


def _balance_weights(
    centers: np.ndarray,
    coords: np.ndarray,
    pops: np.ndarray,
    targets: np.ndarray,
    *,
    weights_init: np.ndarray | None = None,
    max_iter: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Find weights `w` such that the power-diagram assignment with
    (centers, w) gives each cell its target population, by maximizing
    the Kantorovich dual potential

        D(w) = ∑_j p_j · min_i (||c_i − x_j||² − w_i) + ∑_i target_i · w_i

    via L-BFGS-B on −D.  Returns the weights along with the assignment
    they induce.
    """
    k = centers.shape[0]
    n = coords.shape[0]

    # (n, k) squared distances unit_j → center_i.  This is the dominant
    # cost of the inner solve; computed once per outer iteration.
    sq_dist = np.sum(
        (coords[:, None, :] - centers[None, :, :]) ** 2, axis=2
    )

    if weights_init is None:
        w0 = np.zeros(k)
    else:
        w0 = np.asarray(weights_init, dtype=float).copy()

    # Closure over sq_dist, pops, targets — not held beyond the optimize call.
    def neg_dual(w: np.ndarray) -> tuple[float, np.ndarray]:
        # scores[j, i] = sq_dist[j, i] − w[i]; lower is better.
        scores = sq_dist - w[None, :]
        u_j = scores.min(axis=1)  # the dual variables for the unit side
        assignments_local = scores.argmin(axis=1)
        # D(w) = Σ_j p_j u_j + Σ_i target_i w_i
        d_value = float(np.sum(pops * u_j) + np.sum(targets * w))
        # ∂D/∂w_i = target_i − pop_assigned_to_i
        pop_assigned = np.bincount(
            assignments_local, weights=pops, minlength=k
        )
        grad = targets - pop_assigned
        # We minimize −D
        return -d_value, -grad

    # `gtol` of 1e-6 is much tighter than we need (population
    # imbalances of 0.5 person are already invisible) but cheap, and
    # the piecewise-linear nature of the objective means L-BFGS often
    # terminates on `ftol` first anyway.
    result = minimize(
        neg_dual,
        x0=w0,
        jac=True,
        method="L-BFGS-B",
        options={
            "maxiter": max_iter,
            "gtol": 1e-6,
            "ftol": 1e-12,
        },
    )

    weights = result.x
    final_scores = sq_dist - weights[None, :]
    assignments = final_scores.argmin(axis=1).astype(np.int64)
    _ = n  # (silences unused-var: kept for clarity above)
    return weights, assignments


def _population_weighted_centroids(
    coords: np.ndarray,
    pops: np.ndarray,
    assignments: np.ndarray,
    k: int,
    fallback: np.ndarray,
) -> np.ndarray:
    """
    Compute the population-weighted centroid of each cell.

    For cell `i`:  c_i = (Σ_{j ∈ cell i} p_j x_j) / Σ_{j ∈ cell i} p_j.

    If a cell ends up empty (no assigned units) or has total population
    zero, we leave its center at the fallback (the previous iteration's
    value).  Empty cells are pathological for this algorithm and don't
    happen on real inputs, but the guard keeps the math finite.
    """
    new_centers = fallback.copy()
    # Sum coords weighted by population, per cell.  Use np.add.at for
    # the scatter-add since multiple j's can map to the same i.
    weighted_sum = np.zeros((k, 2), dtype=float)
    np.add.at(weighted_sum, assignments, coords * pops[:, None])
    cell_pop = np.bincount(assignments, weights=pops, minlength=k)
    nonempty = cell_pop > 0
    new_centers[nonempty] = (
        weighted_sum[nonempty] / cell_pop[nonempty, None]
    )
    return new_centers
