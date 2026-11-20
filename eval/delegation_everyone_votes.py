"""
Demo 5's everyone-votes reference point: every frozen arrangement on the 200
primary cities with every resident, office holder and delegate voting on
every question. Declared before it was run, in
prompts/demo-5-liquid-democracy.md, "Exploratory analyses after the freeze",
item 3. It is descriptive, computes no verdict and changes no frozen
reading. The story at /liquid uses it for the idea and the basic mechanism,
before turnout enters.

  python -m eval.delegation_everyone_votes run [--workers N]
      Simulate every city into .cache/liquid-everyone-votes/, one file per
      city, resumable. Refuses an uncommitted checkout unless --allow-dirty.
  python -m eval.delegation_everyone_votes publish
      Package the run into eval/benchmarks/delegation_everyone_votes_v1/:
      the city records (kept local, see below), the run manifest, and the
      summaries. Refuses a run that is incomplete, uncommitted or not the
      declared one.
  python -m eval.delegation_everyone_votes rebuild
      Rewrite the summaries and metadata.json from the published files.
  python -m eval.delegation_everyone_votes verify
      Check every published hash and the setting's invariants; with the city
      records, also rebuild the summaries byte for byte.

The frozen code runs unchanged. Turnout has its own random stream, so the
population's legacy uniform bounds at [1, 1] (no dial mean) give every
resident a rate of 1 while keeping each city's residents, beliefs,
candidates and questions; the turnout policy puts office holders and
delegates at rate 1.

The city records (cities.jsonl.gz) stay out of the repository, like the
frozen benchmark's: the benchmark's .gitignore excludes them and
metadata.json keeps their hash.
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
from dataclasses import asdict, fields, replace
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any, Final

import numpy as np

from delegation.comparison import NOT_CAST, Population, TurnoutPolicy, compare, runner
from delegation.comparison.beliefs import BELIEFS_PATH
from delegation.comparison.measures import Measures
from delegation.comparison.protocol import (
    PRIMARY_CITIES,
    PRIMARY_SEED_BASE,
    PROTOCOL_FROZEN,
    SWISS_MARKER,
    t_interval,
)
from delegation.comparison.runner import ATTRIBUTED, CAP, CONTRASTS, CityConfig
from delegation.comparison.sweeps import PRIMARY_POINT

from .delegation_frontier import _csv, _gzip, _num

ROOT: Final = Path(__file__).resolve().parents[1]
BENCHMARK_ID: Final = "delegation_everyone_votes_v1"
DEFAULT_RUNS: Final = ROOT / ".cache" / "liquid-everyone-votes"
DEFAULT_OUT: Final = ROOT / "eval" / "benchmarks" / BENCHMARK_ID
DECLARED: Final = "2026-11-20"
POINT: Final = "everyone votes: primary settings"
SETTING: Final = "everyone votes"
# Everyone who decides for others votes on every question
EVERYONE_VOTES: Final = TurnoutPolicy(office_rate=1.0, resolver_turnout=1.0)
# Every arrangement compare() runs, in its order
ARRANGEMENTS: Final = (
    "full_turnout",
    "direct",
    "representative",
    "representative_by_record",
    "district_choice_voters",
    "district_choice",
    "proxy",
    "liquid",
)
# The arrangements calibrated by the overhead rule
CALIBRATED: Final = ("proxy", "liquid")

CITIES: Final = "cities.jsonl.gz"
MANIFEST: Final = "manifest.json"
MEASURES: Final = "measures.csv"
CONTRASTS_CSV: Final = "contrasts.csv"
CAP_CSV: Final = "cap.csv"
METADATA: Final = "metadata.json"
SOURCES: Final = ("eval/delegation_everyone_votes.py",)
# Every field a resumed or published run must match
BOUND: Final = (
    "benchmark_id",
    "commit",
    "dirty",
    "diff_sha256",
    "beliefs_sha256",
    "declared",
    "frozen_protocol",
    "setting",
    "primary_cities",
    "primary_seed_base",
    "python",
    "numpy",
    "scipy",
)
# The measures a summary row reports, in the frozen dataclass's order
MEASURE_FIELDS: Final = tuple(f.name for f in fields(Measures) if f.name != "arrangement")


class EveryoneVotesError(ValueError):
    """A run or benchmark directory that is not the declared one."""


# ---------------------------------------------------------------------------
# The setting
# ---------------------------------------------------------------------------


def config(position: int) -> CityConfig:
    """
    A primary city with every resident's turnout rate at 1. The city's seed is
    the same at every level of the dial, and turnout is drawn from its own
    stream, so this is the frozen city with only turnout changed.
    """
    frozen = PRIMARY_POINT.config(position, SWISS_MARKER)
    return replace(frozen, turnout_mean=None, min_turnout=1.0, max_turnout=1.0)


def population(position: int) -> Population:
    city = runner._population(config(position))
    if not (city.turnout == 1.0).all():
        raise EveryoneVotesError(f"position {position}: a resident's turnout rate is not 1")
    return city


def evaluate(city: Population) -> dict[str, Any]:
    """
    What the frozen runner records for one city at one level, under the
    everyone-votes policy, without the attendance frontier (every floor is 1).
    """
    result = compare(city, EVERYONE_VOTES, CAP)
    sincere = city.evaluation.sincere
    hits = {name: outcome.counted == sincere for name, outcome in result.outcomes.items()}
    matches = {name: int(hit.sum()) for name, hit in hits.items()}
    liquid_kept = result.outcomes["liquid"].kept
    attribution = {}
    for other in ATTRIBUTED:
        diff = hits["liquid"].astype(np.int64) - hits[other].astype(np.int64)
        attribution[other] = {
            "kept_pairs": int(liquid_kept.sum()),
            "kept_difference": int(diff[liquid_kept].sum()),
            "resolved_difference": int(diff[~liquid_kept].sum()),
        }
    return {
        "pairs": int(sincere.size),
        "matches": matches,
        "uncast": {name: int((o.counted == NOT_CAST).sum()) for name, o in result.outcomes.items()},
        "attribution": attribution,
        "liquid_meets_cap": bool(result.measures["liquid"].overhead <= CAP + 1e-12),
        "proxy_meets_cap": bool(result.measures["proxy"].overhead <= CAP + 1e-12),
        "liquid_acceptance": asdict(result.liquid_acceptance),
        "proxy_acceptance": asdict(result.proxy_acceptance),
        "measures": {name: asdict(m) for name, m in result.measures.items()},
    }


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def run_city(position: int) -> dict[str, Any]:
    """One primary city with everyone voting."""
    record = {"point": POINT, "position": position, "seed": config(position).seed, "setting": SETTING}
    record.update(evaluate(population(position)))
    return record


def manifest(state: runner.CodeState) -> dict[str, Any]:
    return {
        "benchmark_id": BENCHMARK_ID,
        "label": "exploratory",
        "commit": state.commit,
        "dirty": state.dirty,
        "diff_sha256": state.diff_sha256,
        "beliefs_sha256": runner._sha256(BELIEFS_PATH),
        "declared": DECLARED,
        "frozen_protocol": PROTOCOL_FROZEN,
        "setting": SETTING,
        "turnout_policy": asdict(EVERYONE_VOTES),
        "primary_cities": PRIMARY_CITIES,
        "primary_seed_base": PRIMARY_SEED_BASE,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": version("scipy"),
    }


def _prepare(out: Path, state: runner.CodeState, allow_dirty: bool) -> None:
    if state.dirty and not allow_dirty:
        raise EveryoneVotesError("the checkout has uncommitted changes; run from a commit (or --allow-dirty)")
    path = out / MANIFEST
    current = manifest(state)
    if path.exists():
        recorded = json.loads(path.read_text(encoding="utf-8"))
        for key in BOUND:
            if recorded.get(key) != current[key]:
                raise EveryoneVotesError(f"{out} holds a run with a different {key}; use another directory")
        return
    if any((out / runner.CITIES).glob("*/*.json")):
        raise EveryoneVotesError(f"{out} holds city records but no manifest")
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
            raise EveryoneVotesError(f"{len(failures)} cities failed; rerun to retry them:\n" + "\n".join(failures))
        return written


# ---------------------------------------------------------------------------
# Checking a run
# ---------------------------------------------------------------------------


def check_rows(rows: Sequence[dict[str, Any]]) -> None:
    """
    Every declared city once, on its declared seed, with the setting's
    invariants: no ballot uncast under any arrangement, and direct voting
    equal to full turnout.
    """
    positions = sorted(int(row["position"]) for row in rows)
    if positions != list(range(1, PRIMARY_CITIES + 1)):
        raise EveryoneVotesError(f"the run has {len(positions)} of {PRIMARY_CITIES} declared cities")
    pairs = {int(row["pairs"]) for row in rows}
    if len(pairs) != 1:
        raise EveryoneVotesError("the cities do not all have the same number of voter-question pairs")
    for row in rows:
        position = int(row["position"])
        if row["point"] != POINT or row["setting"] != SETTING:
            raise EveryoneVotesError(f"position {position} is not the declared city")
        if row["seed"] != PRIMARY_POINT.config(position, SWISS_MARKER).seed:
            raise EveryoneVotesError(f"position {position} has the wrong seed")
        if list(row["matches"]) != list(ARRANGEMENTS) or list(row["measures"]) != list(ARRANGEMENTS):
            raise EveryoneVotesError(f"position {position} lacks an arrangement")
        if any(row["uncast"][name] for name in ARRANGEMENTS):
            raise EveryoneVotesError(f"position {position}: a ballot went uncast with everyone voting")
        if not row["matches"]["direct"] == row["matches"]["full_turnout"] == row["pairs"]:
            raise EveryoneVotesError(f"position {position}: direct voting is not full turnout")


def check_manifest(recorded: dict[str, Any]) -> None:
    """A run published as this benchmark: the declared settings, from a committed state."""
    expected = {
        "benchmark_id": BENCHMARK_ID,
        "declared": DECLARED,
        "frozen_protocol": PROTOCOL_FROZEN,
        "setting": SETTING,
        "turnout_policy": asdict(EVERYONE_VOTES),
        "primary_cities": PRIMARY_CITIES,
        "primary_seed_base": PRIMARY_SEED_BASE,
        "beliefs_sha256": runner._sha256(BELIEFS_PATH),
    }
    for key, value in expected.items():
        if recorded.get(key) != value:
            raise EveryoneVotesError(f"the run has {key} {recorded.get(key)!r}, not {value!r}")
    if recorded.get("dirty") is not False or recorded.get("diff_sha256") is not None:
        raise EveryoneVotesError("the run was not made from a committed state")


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


def measures_csv(rows: Sequence[dict[str, Any]]) -> bytes:
    """Each arrangement: the mean over cities of every measure, with t-intervals for two."""
    rest = [name for name in MEASURE_FIELDS if name not in ("fidelity", "overhead")]
    header = ["arrangement", "cities"]
    header += ["fidelity", "fidelity_lower", "fidelity_upper", "overhead", "overhead_lower", "overhead_upper"]
    header += rest
    out = []
    for arrangement in ARRANGEMENTS:
        per_city = [row["measures"][arrangement] for row in rows]

        def column(name: str) -> np.ndarray[Any, np.dtype[np.float64]]:
            return np.array([_value(m[name]) for m in per_city], dtype=np.float64)

        cells = [arrangement, str(len(per_city))]
        for name in ("fidelity", "overhead"):
            interval = t_interval(column(name))
            cells += [_num(interval.estimate), _num(interval.lower), _num(interval.upper)]
        for name in rest:
            values = column(name)
            finite = values[~np.isnan(values)]
            cells.append(_num(float(finite.mean())) if finite.size else "")
        out.append(cells)
    return _csv(header, out)


def contrasts_csv(rows: Sequence[dict[str, Any]]) -> bytes:
    """
    The frozen runner's declared contrasts (H1, specialisation and the
    ladder's steps), as fidelity differences with 95% t-intervals over cities.
    """
    out = []
    for name, (first, second) in CONTRASTS.items():
        values = np.array(
            [(row["matches"][first] - row["matches"][second]) / row["pairs"] for row in rows], dtype=np.float64
        )
        interval = t_interval(values)
        out.append([name, first, second, _num(interval.estimate), _num(interval.lower), _num(interval.upper)])
    return _csv(["quantity", "first", "second", "estimate", "lower", "upper"], out)


def cap_csv(rows: Sequence[dict[str, Any]]) -> bytes:
    """How many cities' calibrated arrangements meet the cap, on evaluation and on history questions."""
    out = []
    for arrangement in CALIBRATED:
        meets = sum(bool(row[f"{arrangement}_meets_cap"]) for row in rows)
        feasible = sum(bool(row[f"{arrangement}_acceptance"]["feasible"]) for row in rows)
        out.append([arrangement, str(len(rows)), _num(CAP), str(meets), str(feasible)])
    return _csv(["arrangement", "cities", "cap", "meets_cap", "history_feasible"], out)


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
        "generator": "python -m eval.delegation_everyone_votes publish",
        "commit": recorded["commit"],
        "frozen_protocol": recorded["frozen_protocol"],
        "beliefs_sha256": recorded["beliefs_sha256"],
        "environment": {k: recorded[k] for k in ("python", "numpy", "scipy")},
        "setting": SETTING,
        "turnout_policy": recorded["turnout_policy"],
        "cities": PRIMARY_CITIES,
        "arrangements": list(ARRANGEMENTS),
        "participant_data": False,
        "inference_provider_calls": 0,
        "source_sha256_lf_normalized": {source: _source_sha256(source) for source in SOURCES},
        "outputs": dict(sorted(outputs.items())),
    }
    return (runner._dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build(directory: Path) -> dict[str, bytes]:
    if not has_cities(directory):
        raise EveryoneVotesError(f"the city records are not in {directory}: regenerate them with run and publish")
    rows = load_cities(directory)
    check_rows(rows)
    built = {MEASURES: measures_csv(rows), CONTRASTS_CSV: contrasts_csv(rows), CAP_CSV: cap_csv(rows)}
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


def setting_problems(directory: Path) -> list[str]:
    """The setting's invariants, read from the published measures.csv."""
    with (directory / MEASURES).open(encoding="utf-8", newline="") as handle:
        rows = {r["arrangement"]: r for r in csv.DictReader(handle)}
    problems = []
    if list(rows) != list(ARRANGEMENTS):
        problems.append("measures.csv does not list every arrangement in order")
        return problems
    for name in ARRANGEMENTS:
        if float(rows[name]["none_share"]) != 0.0:
            problems.append(f"{name} leaves ballots uncast with everyone voting")
    for name in ("full_turnout", "direct"):
        if float(rows[name]["fidelity"]) != 1.0 or float(rows[name]["overhead"]) != 1.0:
            problems.append(f"{name} is not the full-turnout corner")
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
    try:
        check_manifest(json.loads((directory / MANIFEST).read_text(encoding="utf-8")))
    except EveryoneVotesError as error:
        problems.append(str(error))
    problems.extend(setting_problems(directory))
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
                print("every hash holds, the setting's invariants hold, and the summaries rebuild")
            else:
                print(
                    "every committed hash holds and the setting's invariants hold. The city records "
                    "are not here, so the summaries were not rebuilt."
                )
    except EveryoneVotesError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
