"""
Demo 5's fallback study (R2): liquid delegation with the district
representative as default, on the 200 primary cities at every level of the
turnout dial. Declared before it was run, in
prompts/demo-5-liquid-democracy.md, "Exploratory analyses after the
freeze", item 4. Exploratory: it changes no frozen reading.

The default, on top of the frozen calibrated liquid arrangement:
  (a) a resident with no delegate for a topic (they keep it only because no
      candidate cleared the acceptance level, or they have no record) is
      represented on it by their district's representative;
  (b) a vote still uncast at close (whoever decided it did not vote) takes
      the representative's ballot.
Delegations, the acceptance level, routing, the loop rule and the turnout
draws are the frozen arrangement's, unchanged. A representative holding
default votes on a question votes on it at the larger of their own rate and
the office-holder rate, so taking on default votes never removes a ballot
they would have cast; everyone else votes as in the frozen arrangement. A
vote the representative does not cast stays uncast.

  python -m eval.delegation_fallback run [--workers N]
  python -m eval.delegation_fallback publish
  python -m eval.delegation_fallback rebuild
  python -m eval.delegation_fallback verify

The city records (cities.jsonl.gz) stay out of the repository; the
benchmark's .gitignore excludes them and metadata.json keeps their hash.
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

from delegation.comparison import NOT_CAST, Outcome, Population, compare, runner
from delegation.comparison.arrangements import DIAL_TURNOUT, _winners
from delegation.comparison.beliefs import BELIEFS_PATH
from delegation.comparison.measures import Measures, measure
from delegation.comparison.protocol import (
    FEASIBLE_SHARE,
    PRIMARY_CITIES,
    PRIMARY_SEED_BASE,
    PROTOCOL_FROZEN,
    TURNOUT_GRID,
    Interval,
    direction,
    h1_verdict,
    t_interval,
)
from delegation.comparison.runner import CAP
from delegation.comparison.sweeps import PRIMARY_POINT

from .delegation_frontier import _csv, _gzip, _num

ROOT: Final = Path(__file__).resolve().parents[1]
BENCHMARK_ID: Final = "delegation_fallback_v1"
DEFAULT_RUNS: Final = ROOT / ".cache" / "liquid-fallback"
DEFAULT_OUT: Final = ROOT / "eval" / "benchmarks" / BENCHMARK_ID
DECLARED: Final = "2026-11-20"
POINT: Final = "fallback: primary settings"
DEFAULT_ARRANGEMENT: Final = "liquid_default"
# The arrangements reported, in order: the frozen two and liquid with the default
ARRANGEMENTS: Final = ("representative", "liquid", DEFAULT_ARRANGEMENT)
# The levels the hypothesis reads
HYPOTHESIS_LEVELS: Final = (0.1, 0.2, 0.3)

CITIES: Final = "cities.jsonl.gz"
MANIFEST: Final = "manifest.json"
MEASURES: Final = "measures.csv"
LEVELS: Final = "levels.csv"
HYPOTHESIS: Final = "hypothesis.json"
METADATA: Final = "metadata.json"
SOURCES: Final = ("eval/delegation_fallback.py",)
BOUND: Final = (
    "benchmark_id",
    "commit",
    "dirty",
    "diff_sha256",
    "beliefs_sha256",
    "declared",
    "frozen_protocol",
    "turnout_grid",
    "primary_cities",
    "primary_seed_base",
    "python",
    "numpy",
    "scipy",
)
MEASURE_FIELDS: Final = tuple(f.name for f in fields(Measures) if f.name != "arrangement")


class FallbackError(ValueError):
    """A run or benchmark directory that is not the declared one."""


# ---------------------------------------------------------------------------
# The representative as default
# ---------------------------------------------------------------------------


def _counted(
    population: Population, resolver: np.ndarray[Any, Any], office: np.ndarray[Any, Any]
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """
    Each voter's counted ballot under `resolver`, and whether each person cast
    a ballot as a decider. As the frozen liquid arrangement under DIAL_TURNOUT
    (everyone at their own rate, on the shared draws), except that a person
    marked in `office` [person, question] votes at the larger of their own
    rate and the office-holder rate: holding default votes never removes a
    ballot they would have cast.
    """
    questions = population.evaluation
    people, count = questions.sincere.shape
    columns = np.arange(count)[None, :]
    voters = np.arange(people)[:, None]
    own_rate = np.broadcast_to(population.turnout[:, None], (people, count))
    rate = np.where(office, np.maximum(own_rate, DIAL_TURNOUT.office_rate), own_rate)
    would_cast = questions.turnout_draw < rate
    own = np.where(would_cast, questions.sincere, NOT_CAST)
    holds = np.zeros((people, count), dtype=np.bool_)
    others = resolver != voters
    holds[resolver[others], np.broadcast_to(columns, resolver.shape)[others]] = True
    decides = holds | (resolver == voters)
    return np.asarray(own[resolver, columns], dtype=np.int8), np.asarray(would_cast & decides, dtype=np.bool_)


def _office(resolver: np.ndarray[Any, Any], default: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """[person, question]: whether the person holds anyone's vote through the default."""
    people, count = resolver.shape
    office = np.zeros((people, count), dtype=np.bool_)
    columns = np.broadcast_to(np.arange(count)[None, :], resolver.shape)
    office[resolver[default], columns[default]] = True
    return office


def with_default(population: Population, liquid: Outcome, representative: Outcome) -> Outcome:
    """
    The frozen liquid outcome with the representative as default: (a) every
    pair a voter decides for want of a delegate goes to their representative,
    then (b) every vote still uncast takes the representative's ballot.
    """
    people = population.size
    voters = np.arange(people)[:, None]
    rep_of = np.broadcast_to(representative.resolver[:, :1], liquid.resolver.shape)
    if not (representative.resolver == rep_of).all():
        raise FallbackError("a voter's representative changes between questions")
    # The frozen arrangement under DIAL_TURNOUT, recounted here, must be itself
    counted0, cast0 = _counted(population, liquid.resolver, np.zeros_like(liquid.kept))
    if not (np.array_equal(counted0, liquid.counted) and np.array_equal(cast0, liquid.cast)):
        raise FallbackError("the recount does not reproduce the frozen liquid outcome")
    # (a) Kept for want of a delegate: deciding themself, but not on a loop
    no_delegate = (liquid.resolver == voters) & ~liquid.looped
    resolver_a = np.where(no_delegate, rep_of, liquid.resolver)
    counted_a, _ = _counted(population, resolver_a, _office(resolver_a, no_delegate))
    # (b) Still uncast at close
    uncast = counted_a == NOT_CAST
    default = no_delegate | uncast
    resolver_b = np.where(uncast, rep_of, resolver_a)
    counted_b, cast_b = _counted(population, resolver_b, _office(resolver_b, default))
    return Outcome(
        # Named liquid so measure() treats it as chosen from the record
        # (lifecycle overhead); renamed when reported
        arrangement=liquid.arrangement,
        counted=counted_b,
        resolver=np.asarray(resolver_b, dtype=liquid.resolver.dtype),
        kept=np.asarray(liquid.kept & ~no_delegate, dtype=np.bool_),
        cast=cast_b,
        winners=_winners(population, counted_b),
        delegations=liquid.delegations,
        looped=liquid.looped,
        loops=liquid.loops,
    )


def evaluate(population: Population) -> dict[str, Any]:
    """One city at one level: the representative, frozen liquid and liquid with the default."""
    result = compare(population, DIAL_TURNOUT, CAP)
    liquid = result.outcomes["liquid"]
    representative = result.outcomes["representative"]
    reference = result.outcomes["full_turnout"]
    defaulted = with_default(population, liquid, representative)
    measures = {
        "representative": result.measures["representative"],
        "liquid": result.measures["liquid"],
        DEFAULT_ARRANGEMENT: replace(measure(population, defaulted, reference), arrangement=DEFAULT_ARRANGEMENT),
    }
    outcomes = {"representative": representative, "liquid": liquid, DEFAULT_ARRANGEMENT: defaulted}
    sincere = population.evaluation.sincere
    record = {
        "pairs": int(sincere.size),
        "matches": {name: int((o.counted == sincere).sum()) for name, o in outcomes.items()},
        "liquid_acceptance": asdict(result.liquid_acceptance),
        "meets_cap": {name: bool(measures[name].overhead <= CAP + 1e-12) for name in ("liquid", DEFAULT_ARRANGEMENT)},
        "measures": {name: asdict(m) for name, m in measures.items()},
    }
    return record


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def run_city(position: int) -> dict[str, Any]:
    """One primary city at every level of the dial."""
    levels = {}
    for level in TURNOUT_GRID:
        config = PRIMARY_POINT.config(position, level)
        record = {"seed": config.seed, "turnout_mean": config.turnout_mean}
        record.update(evaluate(runner._population(config)))
        levels[repr(level)] = record
    return {"point": POINT, "position": position, "levels": levels}


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
        "turnout_grid": list(TURNOUT_GRID),
        "primary_cities": PRIMARY_CITIES,
        "primary_seed_base": PRIMARY_SEED_BASE,
        "turnout_policy": asdict(DIAL_TURNOUT),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": version("scipy"),
    }


def _prepare(out: Path, state: runner.CodeState, allow_dirty: bool) -> None:
    if state.dirty and not allow_dirty:
        raise FallbackError("the checkout has uncommitted changes; run from a commit (or --allow-dirty)")
    path = out / MANIFEST
    current = manifest(state)
    if path.exists():
        recorded = json.loads(path.read_text(encoding="utf-8"))
        for key in BOUND:
            if recorded.get(key) != current[key]:
                raise FallbackError(f"{out} holds a run with a different {key}; use another directory")
        return
    if any((out / runner.CITIES).glob("*/*.json")):
        raise FallbackError(f"{out} holds city records but no manifest")
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
    """Simulate every city not yet recorded in `out`; returns how many were written."""
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
            raise FallbackError(f"{len(failures)} cities failed; rerun to retry them:\n" + "\n".join(failures))
        return written


# ---------------------------------------------------------------------------
# Checking a run
# ---------------------------------------------------------------------------


def check_rows(rows: Sequence[dict[str, Any]]) -> None:
    """Every declared city once, at every level, on its declared seed, with every arrangement."""
    positions = sorted(int(row["position"]) for row in rows)
    if positions != list(range(1, PRIMARY_CITIES + 1)):
        raise FallbackError(f"the run has {len(positions)} of {PRIMARY_CITIES} declared cities")
    levels = [repr(level) for level in TURNOUT_GRID]
    for row in rows:
        position = int(row["position"])
        if row["point"] != POINT or list(row["levels"]) != levels:
            raise FallbackError(f"position {position} is not the declared city")
        for level in TURNOUT_GRID:
            record = row["levels"][repr(level)]
            config = PRIMARY_POINT.config(position, level)
            if record["seed"] != config.seed or record["turnout_mean"] != level:
                raise FallbackError(f"position {position} at {level} has the wrong seed or level")
            if list(record["measures"]) != list(ARRANGEMENTS):
                raise FallbackError(f"position {position} at {level} lacks an arrangement")


def check_manifest(recorded: dict[str, Any]) -> None:
    """A run published as this benchmark: the declared settings, from a committed state."""
    expected = {
        "benchmark_id": BENCHMARK_ID,
        "declared": DECLARED,
        "frozen_protocol": PROTOCOL_FROZEN,
        "turnout_grid": list(TURNOUT_GRID),
        "primary_cities": PRIMARY_CITIES,
        "primary_seed_base": PRIMARY_SEED_BASE,
        "turnout_policy": asdict(DIAL_TURNOUT),
        "beliefs_sha256": runner._sha256(BELIEFS_PATH),
    }
    for key, value in expected.items():
        if recorded.get(key) != value:
            raise FallbackError(f"the run has {key} {recorded.get(key)!r}, not {value!r}")
    if recorded.get("dirty") is not False or recorded.get("diff_sha256") is not None:
        raise FallbackError("the run was not made from a committed state")


# ---------------------------------------------------------------------------
# Summaries and the hypothesis
# ---------------------------------------------------------------------------


def _value(raw: Any) -> float:
    if raw is None:
        return math.nan
    if isinstance(raw, str):
        return math.inf if raw == "inf" else -math.inf
    return float(raw)


def measures_csv(rows: Sequence[dict[str, Any]]) -> bytes:
    """Level x arrangement: the mean over cities of every measure, with t-intervals for two."""
    rest = [name for name in MEASURE_FIELDS if name not in ("fidelity", "overhead")]
    header = ["level", "arrangement", "cities"]
    header += ["fidelity", "fidelity_lower", "fidelity_upper", "overhead", "overhead_lower", "overhead_upper"]
    header += rest
    out = []
    for level in TURNOUT_GRID:
        for arrangement in ARRANGEMENTS:
            per_city = [row["levels"][repr(level)]["measures"][arrangement] for row in rows]

            def column(name: str) -> np.ndarray[Any, np.dtype[np.float64]]:
                return np.array([_value(m[name]) for m in per_city], dtype=np.float64)

            cells = [_num(level), arrangement, str(len(per_city))]
            for name in ("fidelity", "overhead"):
                interval = t_interval(column(name))
                cells += [_num(interval.estimate), _num(interval.lower), _num(interval.upper)]
            for name in rest:
                values = column(name)
                finite = values[~np.isnan(values)]
                cells.append(_num(float(finite.mean())) if finite.size else "")
            out.append(cells)
    return _csv(header, out)


def _difference(rows: Sequence[dict[str, Any]], level: float, first: str, second: str) -> np.ndarray[Any, Any]:
    return np.array(
        [
            (row["levels"][repr(level)]["matches"][first] - row["levels"][repr(level)]["matches"][second])
            / row["levels"][repr(level)]["pairs"]
            for row in rows
        ],
        dtype=np.float64,
    )


def level_reading(rows: Sequence[dict[str, Any]], level: float) -> dict[str, Any]:
    """
    At one level: liquid with the default minus the representative (all
    cities and the cities under the cap), the share under the cap, the
    frozen per-level verdict, and the default's own effect on liquid.
    """
    h1 = _difference(rows, level, DEFAULT_ARRANGEMENT, "representative")
    meets = np.array([row["levels"][repr(level)]["meets_cap"][DEFAULT_ARRANGEMENT] for row in rows], dtype=np.bool_)
    all_cities = t_interval(h1)
    cap_meeting = t_interval(h1[meets]) if meets.sum() >= 2 else None
    share = float(meets.mean())
    verdict = (
        h1_verdict(all_cities, cap_meeting, share)
        if cap_meeting is not None
        else "overhead condition not met"
    )
    return {
        "level": level,
        "h1_all": all_cities,
        "h1_cap": cap_meeting,
        "direction": direction(all_cities),
        "cap_share": share,
        "cap_meeting_cities": int(meets.sum()),
        "verdict": verdict,
        "default_gain": t_interval(_difference(rows, level, DEFAULT_ARRANGEMENT, "liquid")),
    }


def _interval_cells(interval: Interval | None) -> list[str]:
    if interval is None:
        return ["", "", ""]
    return [_num(interval.estimate), _num(interval.lower), _num(interval.upper)]


def levels_csv(rows: Sequence[dict[str, Any]]) -> bytes:
    header = [
        "level",
        "h1_estimate",
        "h1_lower",
        "h1_upper",
        "direction",
        "cap_share",
        "cap_meeting_cities",
        "h1_cap_estimate",
        "h1_cap_lower",
        "h1_cap_upper",
        "frozen_verdict",
        "default_gain_estimate",
        "default_gain_lower",
        "default_gain_upper",
    ]
    out = []
    for level in TURNOUT_GRID:
        r = level_reading(rows, level)
        out.append(
            [
                _num(level),
                *_interval_cells(r["h1_all"]),
                r["direction"],
                _num(r["cap_share"]),
                str(r["cap_meeting_cities"]),
                *_interval_cells(r["h1_cap"]),
                r["verdict"],
                *_interval_cells(r["default_gain"]),
            ]
        )
    return _csv(header, out)


def hypothesis(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """
    The declared hypothesis, read: at the low levels, liquid with the default
    meets the overhead condition (at least FEASIBLE_SHARE of cities at or under
    the cap) at every level where it leads (the all-city 95% t-interval of its
    fidelity minus the representative's lies above zero).
    """
    readings = [level_reading(rows, level) for level in HYPOTHESIS_LEVELS]
    leading = [r for r in readings if r["direction"] == "positive"]
    if not leading:
        outcome = "not supported: no lead at the low levels"
    elif all(r["cap_share"] >= FEASIBLE_SHARE for r in leading):
        outcome = "supported"
    else:
        outcome = "not supported: overhead condition not met where liquid leads"
    return {
        "benchmark_id": BENCHMARK_ID,
        "label": "exploratory",
        "hypothesis": (
            "Under the frozen test's rules, liquid with the representative as default meets the overhead "
            "condition at every low level (0.1 to 0.3) where it leads."
        ),
        "rules": {"cap": CAP, "feasible_share": FEASIBLE_SHARE, "lead": "all-city 95% t-interval above zero"},
        "levels": [
            {
                "level": r["level"],
                "leads": r["direction"] == "positive",
                "h1": asdict(r["h1_all"]),
                "cap_share": r["cap_share"],
                "frozen_verdict": r["verdict"],
            }
            for r in readings
        ],
        "outcome": outcome,
    }


def _source_sha256(source: str) -> str:
    return hashlib.sha256((ROOT / source).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def metadata(directory: Path, built: dict[str, bytes]) -> bytes:
    recorded = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    outputs = {name: runner._sha256(directory / name) for name in (CITIES, MANIFEST)}
    outputs.update({name: hashlib.sha256(data).hexdigest() for name, data in built.items()})
    value = {
        "benchmark_id": BENCHMARK_ID,
        "label": "exploratory",
        "declared": DECLARED,
        "generator": "python -m eval.delegation_fallback publish",
        "commit": recorded["commit"],
        "frozen_protocol": recorded["frozen_protocol"],
        "beliefs_sha256": recorded["beliefs_sha256"],
        "environment": {k: recorded[k] for k in ("python", "numpy", "scipy")},
        "cities": PRIMARY_CITIES,
        "levels": list(TURNOUT_GRID),
        "arrangements": list(ARRANGEMENTS),
        "participant_data": False,
        "inference_provider_calls": 0,
        "source_sha256_lf_normalized": {source: _source_sha256(source) for source in SOURCES},
        "outputs": dict(sorted(outputs.items())),
    }
    return (runner._dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_cities(directory: Path) -> list[dict[str, Any]]:
    data = gzip.decompress((directory / CITIES).read_bytes())
    return [json.loads(line) for line in data.splitlines() if line]


def has_cities(directory: Path) -> bool:
    return (directory / CITIES).exists()


def build(directory: Path) -> dict[str, bytes]:
    if not has_cities(directory):
        raise FallbackError(f"the city records are not in {directory}: regenerate them with run and publish")
    rows = load_cities(directory)
    check_rows(rows)
    built = {
        MEASURES: measures_csv(rows),
        LEVELS: levels_csv(rows),
        HYPOTHESIS: (runner._dumps(hypothesis(rows), indent=2) + "\n").encode("utf-8"),
    }
    built[METADATA] = metadata(directory, built)
    return built


def publish(runs: Path = DEFAULT_RUNS, out: Path = DEFAULT_OUT) -> list[Path]:
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


def rebuild(directory: Path = DEFAULT_OUT) -> list[Path]:
    paths = []
    for name, data in build(directory).items():
        (directory / name).write_bytes(data)
        paths.append(directory / name)
    return paths


def frozen_problems(directory: Path) -> list[str]:
    """The frozen arrangements in measures.csv must be the frozen benchmark's."""
    frontier = ROOT / "eval" / "benchmarks" / "delegation_frontier_v1" / "measures.csv"
    with frontier.open(encoding="utf-8", newline="") as handle:
        frozen = {
            (float(r["level"]), r["arrangement"]): r
            for r in csv.DictReader(handle)
            if r["point"] == runner.point_key(PRIMARY_POINT)
        }
    with (directory / MEASURES).open(encoding="utf-8", newline="") as handle:
        ours = list(csv.DictReader(handle))
    problems = []
    for row in ours:
        if row["arrangement"] == DEFAULT_ARRANGEMENT:
            continue
        reference = frozen[(float(row["level"]), row["arrangement"])]
        for name in ("fidelity", "overhead", "none_share"):
            if abs(float(row[name]) - float(reference[name])) > 2e-6:
                problems.append(f"{row['arrangement']} at {row['level']} differs from the frozen benchmark in {name}")
    return problems


def verify(directory: Path = DEFAULT_OUT) -> list[str]:
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
    except FallbackError as error:
        problems.append(str(error))
    problems.extend(frozen_problems(directory))
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
            print(
                "every hash holds, the frozen arrangements match the frozen benchmark"
                + (", and the summaries rebuild" if has_cities(args.directory) else "")
            )
    except FallbackError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
