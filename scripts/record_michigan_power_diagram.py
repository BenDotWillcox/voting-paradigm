"""Record Michigan K13's balanced power diagram, one snapshot per outer iteration.

The saved run kept only its final centers, weights and assignments, so the
walkthrough's time-lapse comes from a rerun. It uses the exact solver and
block loader the run recorded (checked by SHA-256 against the run's
benchmark.json), the same seed and settings, and mirrors the solver's outer
loop to keep every center, weight and cell population along the way. The
recording is written only if the rerun's final centers, weights and all
254,730 block assignments equal the saved run exactly.

Usage: python scripts/record_michigan_power_diagram.py --cache-root <BLOCK_PLAN_CACHE_ROOT> --pipeline-root <checkout that ran the plans>
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import time
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "districting-explainer" / "michigan-k13-recording.json"
RUN = Path("state-block-benchmark/suite-through-1000/states/26/districts-13")
SOURCE = Path("state-block-benchmark/source/26")
# The Michigan run predates later inner-solve scaling changes; this preserved
# copy is byte-identical to the recorded districting/algorithm.py.
BASELINE_ALGORITHM = Path("state-block-benchmark/suite-through-1000/corrections/hawaii-optimizer-v1/baseline-code/districting/algorithm.py")
STEM = "tl_2020_26_tabblock20"


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--pipeline-root", type=Path, required=True)
    args = parser.parse_args()
    cache, pipeline = args.cache_root.resolve(), args.pipeline_root.resolve()

    benchmark = json.loads((cache / RUN / "benchmark.json").read_text("utf-8"))
    saved = json.loads((cache / RUN / "initial-solver-result.json").read_text("utf-8"))
    config, code = benchmark["configuration"], benchmark["code_sha256"]
    algorithm_path = cache / BASELINE_ALGORITHM
    loader_path = pipeline / "scripts" / "district_block_sources.py"
    if sha256_file(algorithm_path) != code["districting/algorithm.py"]:
        raise SystemExit("The preserved solver is not the version the Michigan run used.")
    if sha256_file(loader_path) != code["scripts/district_block_sources.py"]:
        raise SystemExit("The block loader is not the version the Michigan run used.")

    spec = importlib.util.spec_from_file_location("recorded_algorithm", algorithm_path)
    solver = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = solver  # its dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(solver)
    sys.path.insert(0, str(pipeline))
    from scripts import district_block_sources as sources  # noqa: E402

    archive = cache / SOURCE / f"{STEM}.zip"
    if sha256_file(archive) != saved["provenance"]["source_sha256"]:
        raise SystemExit("Block source archive does not match the saved run.")
    with tempfile.TemporaryDirectory() as folder:
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(folder)
        units, _, metadata = sources.load_units(Path(folder) / f"{STEM}.shp", "26")

    coords = np.asarray([unit.centroid for unit in units], dtype=float)
    pops = np.asarray([unit.population for unit in units], dtype=float)
    geoids = [unit.geoid for unit in units]
    k, seed = config["district_count"], config["seed"]
    total = int(pops.sum())
    base, remainder = divmod(total, k)
    targets = np.full(k, base, dtype=float)
    targets[:remainder] += 1.0

    # Seeds, then the solver's outer loop with a snapshot after each inner solve.
    rng = np.random.default_rng(seed)
    centers = solver._kmeans_pp_init(coords, pops, k, rng)
    seed_indices = [int(np.flatnonzero((coords == center).all(axis=1))[0]) for center in centers]
    distances = ((coords[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    unweighted = np.bincount(distances.argmin(axis=1), weights=pops, minlength=k)
    weights = np.zeros(k)
    snapshots = []
    started = time.perf_counter()
    for iteration in range(1, config["max_outer_iterations"] + 1):
        weights, assignments = solver._balance_weights(centers, coords, pops, targets, weights_init=weights,
                                                       max_iter=config["inner_max_iterations"])
        populations = np.bincount(assignments, weights=pops, minlength=k)
        new_centers = solver._population_weighted_centroids(coords, pops, assignments, k, fallback=centers)
        max_move = float(np.max(np.linalg.norm(new_centers - centers, axis=1)))
        snapshots.append({"iteration": iteration, "centers": centers.tolist(), "weights": weights.tolist(),
                          "populations": populations.astype(int).tolist(), "maxMoveM": max_move})
        print(f"iteration {iteration:2d}  max move {max_move:12.4f} m  ({time.perf_counter() - started:6.1f} s)", flush=True)
        centers = new_centers
        if max_move < config["center_tolerance_m"]:
            break
    weights, assignments = solver._balance_weights(centers, coords, pops, targets, weights_init=weights,
                                                   max_iter=config["inner_max_iterations"])
    populations = np.bincount(assignments, weights=pops, minlength=k)

    # Only an exact reproduction of the saved run may be published.
    saved_centers = sorted(saved["centers"], key=lambda center: center["district_id"])
    for district, center in enumerate(saved_centers):
        if (centers[district, 0], centers[district, 1], weights[district]) != (center["x"], center["y"], center["weight"]):
            raise SystemExit(f"District {district} center or weight differs from the saved run.")
    if any(saved["assignments"][geoid] != int(assignments[index]) for index, geoid in enumerate(geoids)):
        raise SystemExit("Block assignments differ from the saved run.")
    if len(snapshots) != saved["solver"]["outer_iterations"]:
        raise SystemExit("Outer iteration count differs from the saved run.")

    projection = metadata["projection"]
    recording = {
        "schemaVersion": 1, "state": "Michigan", "stateFips": "26", "districts": k, "seed": seed,
        "settings": {key: config[key] for key in ("max_outer_iterations", "inner_max_iterations", "center_tolerance_m")},
        "centersConverged": saved["solver"]["centers_converged"],
        "targets": targets.astype(int).tolist(), "targetExact": total / k,
        "plane": {"kind": projection["kind"], "lon0": projection["lon0"], "lat0": projection["lat0"],
                  "metersPerDegreeLon": sources._EARTH_RADIUS_METERS * math.pi / 180 * math.cos(math.radians(projection["lat0"])),
                  "metersPerDegreeLat": sources._EARTH_RADIUS_METERS * math.pi / 180},
        "seeds": [{"order": order + 1, "block": index, "geoid": geoids[index], "x": float(coords[index, 0]), "y": float(coords[index, 1]),
                   "population": int(pops[index])} for order, index in enumerate(seed_indices)],
        "unweightedPopulations": unweighted.astype(int).tolist(),
        "iterations": snapshots,
        "final": {"centers": centers.tolist(), "weights": weights.tolist(), "populations": populations.astype(int).tolist()},
        "provenance": {
            "run": str(RUN).replace("\\", "/"), "solverSha256": code["districting/algorithm.py"],
            "loaderSha256": code["scripts/district_block_sources.py"], "sourceArchiveSha256": saved["provenance"]["source_sha256"],
            "verified": "final centers, weights and all block assignments equal the saved initial-solver-result.json",
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(recording, separators=(",", ":")), encoding="utf-8")
    print(f"Recorded {len(snapshots)} iterations; reproduction verified; wrote {OUTPUT}")


if __name__ == "__main__":
    main()
