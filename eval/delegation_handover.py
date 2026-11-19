"""
Demo 5's exploratory handover benchmark: liquid at every handover depth, on
the 200 primary cities at every level of the turnout dial, and how a
contrary ballot is scored. Declared before it was run, in
prompts/demo-5-liquid-democracy.md, "Exploratory analyses after the freeze".
It changes no frozen reading.

  python -m eval.delegation_handover run [--workers N]
      Simulate every city into .cache/liquid-handover/, one file per city,
      resumable. Refuses an uncommitted checkout unless --allow-dirty.
  python -m eval.delegation_handover publish
      Package the run into eval/benchmarks/delegation_handover_v1/: the
      city records (kept local, see below), the run manifest, and the
      summaries. Refuses a run that is incomplete, uncommitted or not the
      declared one.
  python -m eval.delegation_handover rebuild
      Rewrite the summaries and metadata.json from the published files.
  python -m eval.delegation_handover verify
      Check every published hash and that depth 0 reproduces the frozen
      benchmark's direct voting; with the city records, also rebuild the
      summaries byte for byte.

The city records (cities.jsonl.gz) stay out of the repository, like the
frozen benchmark's: the benchmark's .gitignore excludes them and
metadata.json keeps their hash.

Figures: python -m eval.plot_delegation_handover.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import platform
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from dataclasses import fields
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any, Final

import numpy as np

from delegation.comparison import runner
from delegation.comparison.beliefs import BELIEFS_PATH
from delegation.comparison.handover import HANDOVER_VERSION, handover_level
from delegation.comparison.measures import Measures
from delegation.comparison.protocol import (
    PRIMARY_CITIES,
    PRIMARY_SEED_BASE,
    PROTOCOL_FROZEN,
    TURNOUT_GRID,
    t_interval,
)
from delegation.comparison.sweeps import PRIMARY_POINT

from .delegation_frontier import _csv, _gzip, _num

ROOT: Final = Path(__file__).resolve().parents[1]
BENCHMARK_ID: Final = "delegation_handover_v1"
DEFAULT_RUNS: Final = ROOT / ".cache" / "liquid-handover"
DEFAULT_OUT: Final = ROOT / "eval" / "benchmarks" / BENCHMARK_ID
FRONTIER: Final = ROOT / "eval" / "benchmarks" / "delegation_frontier_v1"
DECLARED: Final = "2026-11-19"
POINT: Final = "handover: primary settings"
# Liquid's categories in the primary city: depths 0 to 8
DEPTHS: Final = tuple(range(9))

CITIES: Final = "cities.jsonl.gz"
MANIFEST: Final = "manifest.json"
CURVE: Final = "curve.csv"
WRONG_BALLOT: Final = "wrong_ballot.csv"
METADATA: Final = "metadata.json"
SOURCES: Final = ("eval/delegation_handover.py", "delegation/comparison/handover.py")
# Every field a resumed or published run must match
BOUND: Final = (
    "benchmark_id",
    "handover_version",
    "commit",
    "dirty",
    "diff_sha256",
    "beliefs_sha256",
    "declared",
    "frozen_protocol",
    "turnout_grid",
    "primary_cities",
    "primary_seed_base",
    "depths",
    "python",
    "numpy",
    "scipy",
)
# The measures a curve row reports, in the frozen dataclass's order
MEASURE_FIELDS: Final = tuple(f.name for f in fields(Measures) if f.name != "arrangement")
# The frozen arrangements scored by how a contrary ballot counts
SCORED: Final = ("full_turnout", "direct", "representative", "proxy", "liquid")
# The frozen direct arrangement's measures that depth 0 must reproduce
DIRECT_CHECK: Final = ("fidelity", "contrary_share", "none_share", "overhead", "outcome_agreement")


class HandoverError(ValueError):
    """A run or benchmark directory that is not the declared one."""


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def run_city(position: int) -> dict[str, Any]:
    """One primary city at every level of the dial, every depth at each."""
    levels = {}
    for level in TURNOUT_GRID:
        config = PRIMARY_POINT.config(position, level)
        record = {"seed": config.seed, "turnout_mean": config.turnout_mean}
        record.update(handover_level(runner._population(config)))
        levels[repr(level)] = record
    return {"point": POINT, "position": position, "levels": levels}


def manifest(state: runner.CodeState) -> dict[str, Any]:
    return {
        "benchmark_id": BENCHMARK_ID,
        "label": "exploratory",
        "handover_version": HANDOVER_VERSION,
        "commit": state.commit,
        "dirty": state.dirty,
        "diff_sha256": state.diff_sha256,
        "beliefs_sha256": runner._sha256(BELIEFS_PATH),
        "declared": DECLARED,
        "frozen_protocol": PROTOCOL_FROZEN,
        "turnout_grid": list(TURNOUT_GRID),
        "primary_cities": PRIMARY_CITIES,
        "primary_seed_base": PRIMARY_SEED_BASE,
        "depths": list(DEPTHS),
        "turnout_policy": "delegates at their own rate (DIAL_TURNOUT)",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": version("scipy"),
    }


def _prepare(out: Path, state: runner.CodeState, allow_dirty: bool) -> None:
    if state.dirty and not allow_dirty:
        raise HandoverError("the checkout has uncommitted changes; run from a commit (or --allow-dirty)")
    path = out / MANIFEST
    current = manifest(state)
    if path.exists():
        recorded = json.loads(path.read_text(encoding="utf-8"))
        for key in BOUND:
            if recorded.get(key) != current[key]:
                raise HandoverError(f"{out} holds a run with a different {key}; use another directory")
        return
    if any((out / runner.CITIES).glob("*/*.json")):
        raise HandoverError(f"{out} holds city records but no manifest")
    current["started"] = datetime.now(timezone.utc).isoformat()
    path.write_text(runner._dumps(current, indent=2) + "\n", encoding="utf-8", newline="\n")


def run(
    out: Path = DEFAULT_RUNS,
    workers: int = 1,
    allow_dirty: bool = False,
    positions: Sequence[int] | None = None,
    state: runner.CodeState | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """
    Simulate every city not yet recorded in `out`, writing each as it
    finishes; failures are raised together at the end. Returns how many
    cities were written. `positions` and `state` are for tests.
    """
    state = state or runner.code_state()
    out.mkdir(parents=True, exist_ok=True)
    with runner._Lock(out):
        _prepare(out, state, allow_dirty)
        for stray in (out / runner.CITIES).glob("*/*.tmp"):
            stray.unlink()
        recorded = {int(row["position"]) for row in runner.load_records(out)}
        wanted = range(1, PRIMARY_CITIES + 1) if positions is None else positions
        todo = [p for p in wanted if p not in recorded]
        written = 0
        failures: list[str] = []

        def record(position: int, result: Callable[[], dict[str, Any]]) -> None:
            nonlocal written
            try:
                row = result()
            except Exception as error:  # noqa: BLE001 - reported together below
                failures.append(f"position {position}: {error!r}")
                return
            runner._write_city(out, row)
            written += 1
            if progress:
                progress(written + len(failures), len(todo))

        if workers <= 1:
            for position in todo:
                record(position, lambda p=position: run_city(p))  # type: ignore[misc]
        else:
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
            with ProcessPoolExecutor(max_workers=workers, initializer=runner._init_worker) as pool:
                futures: dict[Future[dict[str, Any]], int] = {pool.submit(run_city, p): p for p in todo}
                for future in as_completed(futures):
                    record(futures[future], future.result)
        if failures:
            raise HandoverError(f"{len(failures)} cities failed; rerun to retry them:\n" + "\n".join(failures))
        return written


# ---------------------------------------------------------------------------
# Checking a run
# ---------------------------------------------------------------------------


def check_rows(rows: Sequence[dict[str, Any]]) -> None:
    """Every declared city once, at every level and depth, on its declared seed."""
    positions = sorted(int(row["position"]) for row in rows)
    if positions != list(range(1, PRIMARY_CITIES + 1)):
        raise HandoverError(f"the run has {len(positions)} of {PRIMARY_CITIES} declared cities")
    levels = [repr(level) for level in TURNOUT_GRID]
    depths = [str(d) for d in DEPTHS]
    for row in rows:
        if row["point"] != POINT or list(row["levels"]) != levels:
            raise HandoverError(f"position {row['position']} is not the declared city")
        for level in TURNOUT_GRID:
            record = row["levels"][repr(level)]
            config = PRIMARY_POINT.config(int(row["position"]), level)
            if record["seed"] != config.seed or record["turnout_mean"] != level:
                raise HandoverError(f"position {row['position']} at {level} has the wrong seed or level")
            if list(record["depths"]) != depths:
                raise HandoverError(f"position {row['position']} at {level} lacks a depth")
            if record["depths"]["0"]["matches"] != record["direct_matches"]:
                raise HandoverError(f"position {row['position']} at {level}: depth 0 is not direct voting")


def check_manifest(recorded: dict[str, Any]) -> None:
    """A run published as this benchmark: the declared settings, from a committed state."""
    expected = {
        "benchmark_id": BENCHMARK_ID,
        "handover_version": HANDOVER_VERSION,
        "declared": DECLARED,
        "frozen_protocol": PROTOCOL_FROZEN,
        "turnout_grid": list(TURNOUT_GRID),
        "primary_cities": PRIMARY_CITIES,
        "primary_seed_base": PRIMARY_SEED_BASE,
        "depths": list(DEPTHS),
        "beliefs_sha256": runner._sha256(BELIEFS_PATH),
    }
    for key, value in expected.items():
        if recorded.get(key) != value:
            raise HandoverError(f"the run has {key} {recorded.get(key)!r}, not {value!r}")
    if recorded.get("dirty") is not False or recorded.get("diff_sha256") is not None:
        raise HandoverError("the run was not made from a committed state")


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------


def publish(runs: Path = DEFAULT_RUNS, out: Path = DEFAULT_OUT) -> list[Path]:
    """Package a complete, committed run into `out`, then build the summaries."""
    recorded = json.loads((runs / MANIFEST).read_text(encoding="utf-8"))
    check_manifest(recorded)
    lines = [path.read_bytes().strip() for path in sorted((runs / runner.CITIES).glob("*/*.json"))]
    rows = [json.loads(line) for line in lines]
    check_rows(rows)
    order = sorted(range(len(rows)), key=lambda i: int(rows[i]["position"]))
    out.mkdir(parents=True, exist_ok=True)
    (out / CITIES).write_bytes(_gzip(b"".join(lines[i] + b"\n" for i in order)))
    (out / MANIFEST).write_text(runner._dumps(recorded, indent=2) + "\n", encoding="utf-8", newline="\n")
    return [out / CITIES, out / MANIFEST, *rebuild(out)]


def load_cities(directory: Path) -> list[dict[str, Any]]:
    data = gzip.decompress((directory / CITIES).read_bytes())
    return [json.loads(line) for line in data.splitlines() if line]


def has_cities(directory: Path) -> bool:
    """Whether the city records are present (they are not committed)."""
    return (directory / CITIES).exists()


def _value(raw: Any) -> float:
    if raw is None:
        return math.nan
    if isinstance(raw, str):
        return math.inf if raw == "inf" else -math.inf
    return float(raw)


def curve(rows: Sequence[dict[str, Any]]) -> bytes:
    """Level x depth: the mean over cities of every measure, with t-intervals for two."""
    rest = [name for name in MEASURE_FIELDS if name not in ("fidelity", "overhead")]
    header = ["level", "depth", "cities"]
    header += ["fidelity", "fidelity_lower", "fidelity_upper", "overhead", "overhead_lower", "overhead_upper"]
    header += rest
    out = []
    for level in TURNOUT_GRID:
        for depth in DEPTHS:
            per_city = [row["levels"][repr(level)]["depths"][str(depth)]["measures"] for row in rows]

            def column(name: str) -> np.ndarray[Any, np.dtype[np.float64]]:
                return np.array([_value(m[name]) for m in per_city], dtype=np.float64)

            cells = [_num(level), str(depth), str(len(per_city))]
            for name in ("fidelity", "overhead"):
                interval = t_interval(column(name))
                cells += [_num(interval.estimate), _num(interval.lower), _num(interval.upper)]
            for name in rest:
                values = column(name)
                finite = values[~np.isnan(values)]
                cells.append(_num(float(finite.mean())) if finite.size else "")
            out.append(cells)
    return _csv(header, out)


def _frontier_rows(frontier: Path) -> list[dict[str, str]]:
    with (frontier / "measures.csv").open(encoding="utf-8", newline="") as handle:
        return [r for r in csv.DictReader(handle) if r["point"] == runner.point_key(PRIMARY_POINT)]


def wrong_ballot(frontier: Path = FRONTIER) -> bytes:
    """
    Every frozen arrangement at every level scored as match - w x contrary,
    at w = 0 (fidelity) and w = 1, from the frozen benchmark's published
    shares. A difference of means is the mean of the differences.
    """
    by = {(float(r["level"]), r["arrangement"]): r for r in _frontier_rows(frontier)}
    out = []
    for level in TURNOUT_GRID:
        for arrangement in SCORED:
            r = by[(level, arrangement)]
            match, contrary, none = float(r["fidelity"]), float(r["contrary_share"]), float(r["none_share"])
            out.append(
                [
                    _num(level),
                    arrangement,
                    _num(match),
                    _num(contrary),
                    _num(none),
                    _num(match),
                    _num(match - contrary),
                ]
            )
    return _csv(["level", "arrangement", "match", "contrary", "none", "score_w0", "score_w1"], out)


def _source_sha256(source: str) -> str:
    return hashlib.sha256((ROOT / source).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def metadata(directory: Path, built: dict[str, bytes]) -> bytes:
    """Provenance: the run, its environment, its inputs and every file's hash."""
    recorded = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    outputs = {name: runner._sha256(directory / name) for name in (CITIES, MANIFEST)}
    outputs.update({name: hashlib.sha256(data).hexdigest() for name, data in built.items()})
    value = {
        "benchmark_id": BENCHMARK_ID,
        "label": "exploratory",
        "declared": DECLARED,
        "generator": "python -m eval.delegation_handover publish",
        "commit": recorded["commit"],
        "frozen_protocol": recorded["frozen_protocol"],
        "beliefs_sha256": recorded["beliefs_sha256"],
        "environment": {k: recorded[k] for k in ("python", "numpy", "scipy")},
        "cities": PRIMARY_CITIES,
        "levels": list(TURNOUT_GRID),
        "depths": list(DEPTHS),
        "inputs": {"frontier measures.csv": runner._sha256(FRONTIER / "measures.csv")},
        "participant_data": False,
        "inference_provider_calls": 0,
        "source_sha256_lf_normalized": {source: _source_sha256(source) for source in SOURCES},
        "outputs": dict(sorted(outputs.items())),
    }
    return (runner._dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build(directory: Path) -> dict[str, bytes]:
    if not has_cities(directory):
        raise HandoverError(f"the city records are not in {directory}: regenerate them with run and publish")
    rows = load_cities(directory)
    check_rows(rows)
    built = {CURVE: curve(rows), WRONG_BALLOT: wrong_ballot()}
    built[METADATA] = metadata(directory, built)
    return built


def rebuild(directory: Path = DEFAULT_OUT) -> list[Path]:
    """Rewrite the summaries and metadata.json from the published files."""
    paths = []
    for name, data in build(directory).items():
        (directory / name).write_bytes(data)
        paths.append(directory / name)
    return paths


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def depth_zero_problems(directory: Path, frontier: Path = FRONTIER) -> list[str]:
    """Depth 0 against the frozen benchmark's direct voting, from the two published summaries."""
    with (directory / CURVE).open(encoding="utf-8", newline="") as handle:
        zero = {float(r["level"]): r for r in csv.DictReader(handle) if r["depth"] == "0"}
    direct = {float(r["level"]): r for r in _frontier_rows(frontier) if r["arrangement"] == "direct"}
    problems = []
    for level in TURNOUT_GRID:
        for name in DIRECT_CHECK:
            if abs(float(zero[level][name]) - float(direct[level][name])) > 2e-6:
                problems.append(f"depth 0 at {level} differs from frozen direct voting in {name}")
    return problems


def verify(directory: Path = DEFAULT_OUT) -> list[str]:
    """Every problem with the published benchmark; empty when it holds."""
    problems = []
    recorded = json.loads((directory / METADATA).read_text(encoding="utf-8"))
    for name, digest in recorded["outputs"].items():
        path = directory / name
        if not path.exists():
            if name != CITIES:
                problems.append(f"{name} is missing")
        elif runner._sha256(path) != digest:
            problems.append(f"{name} does not match its recorded hash")
    if recorded["inputs"]["frontier measures.csv"] != runner._sha256(FRONTIER / "measures.csv"):
        problems.append("the frozen benchmark's measures.csv has changed")
    try:
        check_manifest(json.loads((directory / MANIFEST).read_text(encoding="utf-8")))
    except HandoverError as error:
        problems.append(str(error))
    problems.extend(depth_zero_problems(directory))
    if has_cities(directory):
        for name, data in build(directory).items():
            if (directory / name).read_bytes() != data:
                problems.append(f"{name} does not rebuild byte for byte")
    return problems


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("run")
    cmd.add_argument("--out", type=Path, default=DEFAULT_RUNS)
    cmd.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    cmd.add_argument("--allow-dirty", action="store_true")
    cmd = sub.add_parser("publish")
    cmd.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    cmd.add_argument("--out", type=Path, default=DEFAULT_OUT)
    for name in ("rebuild", "verify"):
        sub.add_parser(name).add_argument("directory", type=Path, nargs="?", default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":

            def report(finished: int, total: int) -> None:
                print(f"{finished}/{total} cities", flush=True)

            written = run(args.out, args.workers, args.allow_dirty, progress=report)
            print(f"wrote {written} cities to {args.out}")
        elif args.command == "publish":
            for path in publish(args.runs, args.out):
                print(f"wrote {path}")
        elif args.command == "rebuild":
            for path in rebuild(args.directory):
                print(f"wrote {path}")
        else:
            problems = verify(args.directory)
            for problem in problems:
                print(problem)
            if problems:
                sys.exit(1)
            if has_cities(args.directory):
                print("every hash holds, depth 0 reproduces direct voting, and the summaries rebuild")
            else:
                print(
                    "every committed hash holds and depth 0 reproduces direct voting. The city records "
                    "are not here, so the summaries were not rebuilt."
                )
    except HandoverError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
