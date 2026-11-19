"""
The benchmark runner for demo 5's study: it simulates the declared cities,
records what the protocol needs from each, and reads the verdicts with
`protocol.py`. Design: prompts/demo-5-liquid-democracy.md, "Research
protocol", "Robustness sweeps" and "Running the benchmark".

  Primary   200 cities (protocol.primary_city_seeds), each at every level of
            the turnout dial, with the attendance frontier recounted at
            every floor
  Sweeps    every declared sweep point on its 48 cities, at every level;
            analysed against the primary configuration on the same 48
            positions
  Smoke     a few small cities on development seeds, to check the pipeline
            end to end; never the primary namespace

Each city's levels run in one task, so a city keeps its residents across
the dial. Each finished city is written to its own file atomically
(temporary file, sync, rename), so an interrupted run loses at most the
cities in flight and resumes where it stopped; a lock stops two launches
writing to one directory. The manifest binds a run to one commit, its
uncommitted diff (if any), the beliefs file, the declared settings and the
numerical environment; a resumed run must match it exactly, and an analysis
must run on the same code or record both revisions.

What each city-level records: every arrangement's matching-ballot count;
the voter-question pairs; whether liquid and the proxy meet the overhead
cap; the calibration; every arrangement's measures; the H1 and
specialisation differences split over liquid's kept and resolved pairs; and,
for primary cities, liquid's matches minus the representative's at each
frontier floor. Signed counts keep ties exact; the protocol converts them
to fidelity.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import subprocess
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

import numpy as np
import scipy

from . import compare
from .arrangements import DIAL_TURNOUT, _counted_from
from .beliefs import BELIEFS_PATH, BeliefCityConfig, BeliefModel, load_beliefs, simulate_belief_city
from .population import Population, PopulationConfig, simulate_population
from .protocol import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    FEASIBLE_SHARE,
    PRIMARY_CITIES,
    PRIMARY_SEED_BASE,
    SWISS_MARKER,
    TURNOUT_GRID,
    Interval,
    Threshold,
    frontier_reading,
    h1_size_verdict,
    h1_verdict,
    joint_share,
    specialisation_verdict,
    t_interval,
    threshold,
    threshold_verdict,
)
from .sweeps import (
    CES_MATCHED_CORRELATION,
    FRONTIER_FLOORS,
    PRIMARY_POINT,
    SWEEP_CITIES,
    SWEEPS,
    SweepPoint,
)

RUNNER_VERSION: Final = 2
# The overhead cap, as in compare's calibration
CAP: Final = 0.10
# Small cities on development seeds for the smoke run, disjoint from the
# primary namespace (protocol.PRIMARY_SEED_BASE)
SMOKE_SEED_BASE: Final = 3_000_000
SMOKE_CITIES: Final = 4
SMOKE_LEVELS: Final = (0.2, 0.45, 0.8)

# Differences between arrangements, as (first, second): first minus second
CONTRASTS: Final = {
    "h1": ("liquid", "representative"),
    "specialisation": ("liquid", "proxy"),
    "cost_of_sharing": ("district_choice_voters", "representative_by_record"),
    "choice_by_non_voters": ("district_choice", "district_choice_voters"),
    "platform_against_record": ("representative", "representative_by_record"),
    "city_wide_proxy_combined": ("proxy", "district_choice"),
}
# The comparisons split over liquid's kept and resolved pairs
ATTRIBUTED: Final = ("representative", "proxy")
REFERENCE_KEY: Final = "primary: primary settings, positions 1-48"

CityConfig = BeliefCityConfig | PopulationConfig


@dataclass(frozen=True)
class CityTask:
    """One city: every level of the dial for one point and position."""

    point: str
    position: int
    levels: tuple[tuple[float, CityConfig], ...]
    frontier: bool


def point_key(point: SweepPoint) -> str:
    return f"{point.family}: {point.label}"


POINTS: Final = {point_key(p): p for p in (PRIMARY_POINT, *SWEEPS)}


def primary_tasks() -> list[CityTask]:
    """The 200 primary cities, each at every level, with the frontier."""
    key = point_key(PRIMARY_POINT)
    return [
        CityTask(
            key,
            position,
            tuple((level, PRIMARY_POINT.config(position, level)) for level in TURNOUT_GRID),
            frontier=True,
        )
        for position in range(1, PRIMARY_CITIES + 1)
    ]


def sweep_tasks(only: str | None = None) -> list[CityTask]:
    """Every declared sweep point on its 48 cities, each at every level."""
    tasks: list[CityTask] = []
    for point in SWEEPS:
        key = point_key(point)
        if only is not None and key != only:
            continue
        tasks.extend(
            CityTask(
                key,
                position,
                tuple((level, point.config(position, level)) for level in TURNOUT_GRID),
                frontier=False,
            )
            for position in range(1, SWEEP_CITIES + 1)
        )
    if only is not None and not tasks:
        raise ValueError(f"no sweep point named {only!r}")
    return tasks


def smoke_tasks() -> list[CityTask]:
    """A few small cities on development seeds, fitted and structural."""
    tasks: list[CityTask] = []
    for position in range(1, SMOKE_CITIES + 1):
        seed = SMOKE_SEED_BASE + position
        tasks.append(
            CityTask(
                "smoke: fitted",
                position,
                tuple(
                    (
                        level,
                        BeliefCityConfig(
                            seed=seed,
                            districts=2,
                            residents_per_district=30,
                            history_questions_per_topic=4,
                            evaluation_questions_per_topic=3,
                            turnout_mean=level,
                        ),
                    )
                    for level in SMOKE_LEVELS
                ),
                frontier=True,
            )
        )
        tasks.append(
            CityTask(
                "smoke: structural",
                position,
                tuple(
                    (
                        level,
                        PopulationConfig(
                            seed=seed,
                            districts=2,
                            residents_per_district=30,
                            dimensions=8,
                            history_questions_per_dimension=4,
                            evaluation_questions_per_dimension=3,
                            turnout_mean=level,
                        ),
                    )
                    for level in SMOKE_LEVELS
                ),
                frontier=False,
            )
        )
    return tasks


TASKS: Final[dict[str, Callable[[], list[CityTask]]]] = {
    "smoke": smoke_tasks,
    "primary": primary_tasks,
    "sweeps": sweep_tasks,
}


# ---------------------------------------------------------------------------
# One city
# ---------------------------------------------------------------------------

_MODEL: BeliefModel | None = None


def _model() -> BeliefModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = load_beliefs()
    return _MODEL


def _population(config: CityConfig) -> Population:
    if isinstance(config, BeliefCityConfig):
        return simulate_belief_city(_model(), config)
    return simulate_population(config)


def evaluate_level(config: CityConfig, frontier: bool) -> dict[str, Any]:
    """Everything the protocol needs from one city at one level."""
    population = _population(config)
    result = compare(population, DIAL_TURNOUT, CAP)
    sincere = population.evaluation.sincere
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
        if attribution[other]["kept_difference"] + attribution[other]["resolved_difference"] != (
            matches["liquid"] - matches[other]
        ):
            raise AssertionError("an attribution must add back to its difference")
    record: dict[str, Any] = {
        "seed": config.seed,
        "turnout_mean": config.turnout_mean,
        "pairs": int(sincere.size),
        "matches": matches,
        "attribution": attribution,
        "liquid_meets_cap": bool(result.measures["liquid"].overhead <= CAP + 1e-12),
        "proxy_meets_cap": bool(result.measures["proxy"].overhead <= CAP + 1e-12),
        "liquid_acceptance": asdict(result.liquid_acceptance),
        "proxy_acceptance": asdict(result.proxy_acceptance),
        "measures": {name: asdict(m) for name, m in result.measures.items()},
    }
    if frontier:
        liquid = result.outcomes["liquid"]
        counts = []
        for floor in FRONTIER_FLOORS:
            counted, _ = _counted_from(population, liquid.resolver, floor, fixed=False)
            counts.append(int((counted == sincere).sum()) - matches["representative"])
        # Floor 0 is the dial's own condition
        if counts[0] != matches["liquid"] - matches["representative"]:
            raise AssertionError("the frontier at floor 0 must equal the dial's liquid outcome")
        record["frontier"] = counts
    return record


def run_task(task: CityTask) -> dict[str, Any]:
    """One city at every level of its point."""
    return {
        "point": task.point,
        "position": task.position,
        "levels": {
            repr(level): evaluate_level(config, task.frontier) for level, config in task.levels
        },
    }


# ---------------------------------------------------------------------------
# Storage: one file per city, written atomically
# ---------------------------------------------------------------------------

CITIES: Final = "cities"
MANIFEST: Final = "manifest.json"
LOCK: Final = "run.lock"


def _json_safe(value: Any) -> Any:
    """Plain JSON: NaN becomes null and infinities become strings."""
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    return value


def _dumps(value: Any, **kw: Any) -> str:
    return json.dumps(_json_safe(value), allow_nan=False, **kw)


def _slug(point: str) -> str:
    readable = re.sub(r"[^a-z0-9]+", "-", point.lower()).strip("-")[:40]
    return f"{hashlib.sha256(point.encode()).hexdigest()[:10]}-{readable}"


def city_path(out: Path, point: str, position: int) -> Path:
    return out / CITIES / _slug(point) / f"{position:04d}.json"


def _write_city(out: Path, row: dict[str, Any]) -> None:
    """One city's record, atomically; an existing record is never replaced."""
    path = city_path(out, row["point"], int(row["position"]))
    if path.exists():
        raise RuntimeError(f"{row['point']} position {row['position']} is already recorded")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(_dumps(row, separators=(",", ":")))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def load_records(out: Path) -> list[dict[str, Any]]:
    """Every recorded city; a record that is not valid JSON is an error."""
    rows = []
    for path in sorted((out / CITIES).glob("*/*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if path != city_path(out, row["point"], int(row["position"])):
            raise ValueError(f"{path} does not hold the city its name says")
        rows.append(row)
    return rows


def done(out: Path) -> set[tuple[str, int]]:
    """The (point, position) pairs already recorded."""
    if not (out / CITIES).exists():
        return set()
    return {(row["point"], int(row["position"])) for row in load_records(out)}


# ---------------------------------------------------------------------------
# The manifest and the code state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodeState:
    """The commit, whether tracked files differ from it, and a hash of the difference."""

    commit: str
    dirty: bool
    diff_sha256: str | None


def _git(*args: str) -> str:
    root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout


def code_state() -> CodeState:
    commit = _git("rev-parse", "HEAD").strip()
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no").strip())
    diff = hashlib.sha256(_git("diff", "HEAD").encode()).hexdigest() if dirty else None
    return CodeState(commit, dirty, diff)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# The code and environment an analysis must share with its simulation
ANALYSIS_BOUND: Final = ("commit", "dirty", "diff_sha256", "python", "numpy", "scipy")

# Every field a resumed run must match exactly
BOUND: Final = (
    "runner_version",
    "mode",
    "commit",
    "dirty",
    "diff_sha256",
    "beliefs_sha256",
    "protocol",
    "sweeps",
    "python",
    "numpy",
    "scipy",
)


def manifest(mode: str, state: CodeState) -> dict[str, Any]:
    """What binds a run to its code, data, declared settings and environment."""
    return {
        "runner_version": RUNNER_VERSION,
        "mode": mode,
        "commit": state.commit,
        "dirty": state.dirty,
        "diff_sha256": state.diff_sha256,
        "beliefs_sha256": _sha256(BELIEFS_PATH),
        "protocol": {
            "turnout_grid": list(TURNOUT_GRID),
            "primary_cities": PRIMARY_CITIES,
            "primary_seed_base": PRIMARY_SEED_BASE,
            "sweep_cities": SWEEP_CITIES,
            "frontier_floors": list(FRONTIER_FLOORS),
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "cap": CAP,
            "feasible_share": FEASIBLE_SHARE,
        },
        "sweeps": {point_key(p): asdict(p) for p in SWEEPS},
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
    }


def _prepare(out: Path, mode: str, allow_dirty: bool, state: CodeState) -> None:
    """
    Validate the run's manifest, or create it. Called with the directory's
    lock held, so two first launches cannot both create one (second runner
    review). A manifest is never created beside existing city records,
    whose provenance would then be unknown; it is written atomically.
    """
    if state.dirty and mode != "smoke" and not allow_dirty:
        raise RuntimeError(
            "the checkout has uncommitted changes; primary and sweep runs must come from a "
            "committed state (pass allow_dirty only for development)"
        )
    path = out / MANIFEST
    current = manifest(mode, state)
    if path.exists():
        recorded = json.loads(path.read_text(encoding="utf-8"))
        for key in BOUND:
            if recorded.get(key) != current[key]:
                raise RuntimeError(
                    f"{out} holds a run with a different {key} "
                    f"({recorded.get(key)!r} against {current[key]!r}); use another directory"
                )
        return
    if (out / CITIES).exists() and any((out / CITIES).glob("*/*.json")):
        raise RuntimeError(f"{out} holds city records but no manifest; their provenance is unknown")
    current["started"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(_dumps(current, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class _Lock:
    """An exclusive lock on an output directory, so two launches cannot share it."""

    def __init__(self, out: Path) -> None:
        self.path = out / LOCK

    def __enter__(self) -> _Lock:
        try:
            handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise RuntimeError(
                f"{self.path} exists: another run is using this directory. If none is, "
                "delete the lock and resume"
            ) from None
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        return self

    def __exit__(self, *exc: object) -> None:
        self.path.unlink(missing_ok=True)


def _init_worker() -> None:
    # One BLAS thread per process
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")


def run(
    tasks: Sequence[CityTask],
    out: Path,
    mode: str,
    workers: int = 1,
    allow_dirty: bool = False,
    state: CodeState | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """
    Run every task not yet recorded in `out`, writing each city as it
    finishes. A failed city does not stop the others: every success is
    written, and the failures are raised together at the end, so a retry
    repeats only unfinished cities. Returns how many cities were written.
    `state` overrides the git check (tests).
    """
    state = state or code_state()
    out.mkdir(parents=True, exist_ok=True)
    with _Lock(out):
        _prepare(out, mode, allow_dirty, state)
        if (out / CITIES).exists():
            for stray in (out / CITIES).glob("*/*.tmp"):
                stray.unlink()
        finished = done(out)
        todo = [t for t in tasks if (t.point, t.position) not in finished]
        total = len(todo)
        written = 0
        failures: list[str] = []

        def record(task: CityTask, outcome: Callable[[], dict[str, Any]]) -> None:
            nonlocal written
            try:
                row = outcome()
            except Exception as error:  # noqa: BLE001 - reported together below
                failures.append(f"{task.point} position {task.position}: {error!r}")
                return
            _write_city(out, row)
            written += 1
            if progress:
                progress(written + len(failures), total)

        if workers <= 1:
            for task in todo:
                record(task, lambda t=task: run_task(t))  # type: ignore[misc]
        else:
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
            pool = ProcessPoolExecutor(max_workers=workers, initializer=_init_worker)
            futures: dict[Future[dict[str, Any]], CityTask] = {
                pool.submit(run_task, task): task for task in todo
            }
            handled: set[Future[dict[str, Any]]] = set()
            try:
                for future in as_completed(futures):
                    handled.add(future)
                    record(futures[future], future.result)
            except BaseException:
                # Interrupted (Ctrl-C, say): cancel the queued cities, keep the
                # ones in flight, and write every success before stopping, so
                # an interrupted sweep repeats only what never ran (second
                # runner review)
                for future in futures:
                    if not future.running() and not future.done():
                        future.cancel()
                for future in futures:
                    if future in handled or future.cancelled():
                        continue
                    try:
                        row = future.result()
                    except BaseException:  # noqa: BLE001 - interrupted or failed: not written
                        continue
                    if not city_path(out, row["point"], int(row["position"])).exists():
                        _write_city(out, row)
                pool.shutdown(wait=False, cancel_futures=True)
                raise
            pool.shutdown()
        if failures:
            raise RuntimeError(
                f"{len(failures)} cities failed; rerun to retry them:\n" + "\n".join(failures)
            )
        return written


# ---------------------------------------------------------------------------
# Validation: the exact declared cities, seeds and levels
# ---------------------------------------------------------------------------


def validate(rows: Sequence[dict[str, Any]], mode: str) -> dict[tuple[str, int], CityTask]:
    """
    Every row must be a declared city of `mode`, recorded once, with the
    declared levels and, at each, the declared seed and turnout level.
    Returns the declared tasks keyed by (point, position).
    """
    declared = {(t.point, t.position): t for t in TASKS[mode]()}
    seen: set[tuple[str, int]] = set()
    for row in rows:
        key = (row["point"], int(row["position"]))
        if key not in declared:
            raise ValueError(f"{key} is not a declared city of the {mode} run")
        if key in seen:
            raise ValueError(f"{key} is recorded more than once")
        seen.add(key)
        task = declared[key]
        expected = {repr(level): config for level, config in task.levels}
        if set(row["levels"]) != set(expected):
            raise ValueError(f"{key} has levels {sorted(row['levels'])}, not {sorted(expected)}")
        for name, config in expected.items():
            rec = row["levels"][name]
            if rec["seed"] != config.seed or rec["turnout_mean"] != config.turnout_mean:
                raise ValueError(f"{key} at {name} does not match its declared seed and turnout")
            if task.frontier != ("frontier" in rec):
                raise ValueError(f"{key} at {name} does not match its declared frontier")
    return declared


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def _interval(i: Interval | None) -> dict[str, float] | None:
    return None if i is None else {"estimate": i.estimate, "lower": i.lower, "upper": i.upper}


def _threshold(t: Threshold) -> dict[str, Any]:
    return {
        "verdict": threshold_verdict(t),
        "status": t.status,
        "bracket": t.bracket,
        "interpolated": t.interpolated,
        "first_supported": t.first_supported,
        "confidence": t.confidence,
        "all_cities": asdict(t.all_cities),
        "cap_meeting": asdict(t.cap_meeting),
        "gate_holds": t.gate_holds,
        "cap_share": t.cap_share,
        "band_critical": t.band_critical,
        "zero_spread_levels": t.zero_spread_levels,
        "pointwise": [_interval(i) for i in t.pointwise],
    }


@dataclass
class _Point:
    key: str
    positions: list[int] = field(default_factory=list)
    rows: list[dict[str, dict[str, Any]]] = field(default_factory=list)


def _group(records: Iterable[dict[str, Any]]) -> dict[str, _Point]:
    points: dict[str, _Point] = {}
    for row in sorted(records, key=lambda r: (r["point"], int(r["position"]))):
        point = points.setdefault(row["point"], _Point(row["point"]))
        point.positions.append(int(row["position"]))
        point.rows.append(row["levels"])
    return points


def _contrast(record: dict[str, Any], name: str) -> int:
    first, second = CONTRASTS[name]
    return int(record["matches"][first] - record["matches"][second])


def _column(point: _Point, level: float, read: Callable[[dict[str, Any]], Any]) -> np.ndarray:
    return np.array([read(row[repr(level)]) for row in point.rows], dtype=np.float64)


def _safe_interval(values: np.ndarray) -> Interval | None:
    return t_interval(values) if values.size >= 2 else None


def _nanmean(values: Sequence[Any]) -> float | None:
    data = np.array([np.nan if v is None else v for v in values], dtype=np.float64)
    data = data[np.isfinite(data)]
    return float(data.mean()) if data.size else None


def _attribution(point: _Point, level: float, pairs: int, other: str) -> dict[str, Any]:
    """Liquid minus `other`, split over liquid's kept and resolved pairs."""

    def read(name: str) -> np.ndarray:
        return _column(point, level, lambda r: r["attribution"][other][name])

    kept, resolved, kept_pairs = read("kept_difference"), read("resolved_difference"), read("kept_pairs")
    total_pairs = pairs * len(kept_pairs)
    return {
        # Contributions in fidelity units; per city they add back to the difference
        "kept_contribution": _interval(_safe_interval(kept / pairs)),
        "resolved_contribution": _interval(_safe_interval(resolved / pairs)),
        "difference": _interval(_safe_interval((kept + resolved) / pairs)),
        "kept_share": float(kept_pairs.sum() / total_pairs),
        # Mean match difference on liquid's kept pairs and on its resolved ones
        "kept_difference": float(kept.sum() / kept_pairs.sum()) if kept_pairs.sum() else None,
        "resolved_difference": (
            float(resolved.sum() / (total_pairs - kept_pairs.sum()))
            if total_pairs > kept_pairs.sum()
            else None
        ),
    }


def _level_reading(point: _Point, level: float, pairs: int) -> dict[str, Any]:
    """Every per-level reading the protocol reports."""
    cap = _column(point, level, lambda r: r["liquid_meets_cap"]).astype(bool)
    proxy_cap = _column(point, level, lambda r: r["proxy_meets_cap"]).astype(bool)
    share = float(cap.mean())
    h1 = _column(point, level, lambda r: _contrast(r, "h1")) / pairs
    all_i, cap_i = _safe_interval(h1), _safe_interval(h1[cap])
    if all_i is not None and cap_i is not None:
        direction, size = h1_verdict(all_i, cap_i, share), h1_size_verdict(all_i, cap_i, share)
    else:
        # Fewer than two cities meet the cap: the gate cannot hold
        direction = size = "overhead condition not met"
    reading: dict[str, Any] = {
        "cap_share": share,
        "h1": {
            "all_cities": _interval(all_i),
            "cap_meeting": _interval(cap_i),
            "cap_meeting_cities": int(cap.sum()),
            "direction": direction,
            "size": size,
        },
    }
    spec = _column(point, level, lambda r: _contrast(r, "specialisation")) / pairs
    both = cap & proxy_cap
    joint = joint_share(cap, proxy_cap)
    all_s, both_s = _safe_interval(spec), _safe_interval(spec[both])
    if all_s is not None and both_s is not None:
        sign, spec_size = specialisation_verdict(all_s, both_s, joint)
    else:
        sign = spec_size = "not assessable at matched overhead"
    reading["specialisation"] = {
        "joint_share": joint,
        "liquid_share": share,
        "proxy_share": float(proxy_cap.mean()),
        "both_meet_cap_cities": int(both.sum()),
        "all_cities": _interval(all_s),
        "both_meet_cap": _interval(both_s),
        "direction": sign,
        "size": spec_size,
    }
    reading["decomposition"] = {
        name: _interval(_safe_interval(_contrast_column(point, level, name) / pairs))
        for name in CONTRASTS
    }
    reading["attribution"] = {
        f"liquid_minus_{other}": _attribution(point, level, pairs, other) for other in ATTRIBUTED
    }
    first = point.rows[0][repr(level)]["measures"]
    reading["measures"] = {
        arm: {
            name: _nanmean([row[repr(level)]["measures"][arm][name] for row in point.rows])
            for name in fields
            if name != "arrangement"
        }
        for arm, fields in first.items()
    }
    if "frontier" in point.rows[0][repr(level)]:
        counts = np.array([row[repr(level)]["frontier"] for row in point.rows])
        reading["frontier"] = asdict(frontier_reading(FRONTIER_FLOORS, counts, cap, pairs=pairs))
    return reading


def _contrast_column(point: _Point, level: float, name: str) -> np.ndarray:
    return np.array([_contrast(row[repr(level)], name) for row in point.rows], dtype=np.float64)


def analyse_point(point: _Point, expected: set[int]) -> dict[str, Any]:
    """Every protocol reading for one point, from its validated cities."""
    levels = sorted(float(level) for level in point.rows[0])
    pairs_all = {rec["pairs"] for row in point.rows for rec in row.values()}
    if len(pairs_all) != 1:
        raise ValueError(f"{point.key}: cities differ in their voter-question pairs")
    pairs = pairs_all.pop()
    complete = set(point.positions) == expected and len(point.positions) >= 2
    out: dict[str, Any] = {
        "cities": len(point.positions),
        "expected_cities": len(expected),
        "complete": complete,
        "levels": levels,
        "pairs": pairs,
    }
    if not complete:
        return out
    sweep = POINTS.get(point.key)
    strata = None if sweep is None else sweep.strata(point.positions)
    h1 = np.array([[_contrast(row[repr(level)], "h1") for level in levels] for row in point.rows])
    cap = np.array(
        [[row[repr(level)]["liquid_meets_cap"] for level in levels] for row in point.rows], dtype=bool
    )
    out["threshold"] = _threshold(threshold(tuple(levels), h1, cap, pairs=pairs, strata=strata))
    out["by_level"] = {repr(level): _level_reading(point, level, pairs) for level in levels}
    if SWISS_MARKER in levels:
        out["swiss_marker"] = out["by_level"][repr(SWISS_MARKER)]
    return out


def _paired_interval(diff: np.ndarray, strata: np.ndarray | None) -> Interval:
    """
    A 95% interval for the mean of position-matched differences: an ordinary
    t-interval, or with strata (a fixed number of positions per heavy topic)
    the stratified one, with within-stratum variance.
    """
    from scipy.stats import t as student_t

    if strata is None:
        return t_interval(diff)
    groups = np.unique(strata)
    n = diff.size
    var = 0.0
    for h in groups:
        part = diff[strata == h]
        if part.size > 1:
            var += (part.size / n) ** 2 * float(part.var(ddof=1)) / part.size
    mean = float(diff.mean())
    half = float(student_t.ppf(0.975, max(n - groups.size, 1))) * math.sqrt(var)
    return Interval(mean, mean - half, mean + half)


def _gap(point: _Point, baseline: _Point, pairs: int, baseline_pairs: int) -> dict[str, Any]:
    """
    A point's H1 curve against a baseline's, level by level: the mean of the
    differences between cities at the same seed position, with a paired
    interval (stratified by heavy topic where the point rotates). Matching
    positions is valid whether or not the two configurations share draws,
    and it uses the shared draws where they do (the history and spread
    families keep residents and questions; second runner review).
    """
    by_position = dict(zip(baseline.positions, baseline.rows, strict=True))
    common = [p for p in point.positions if p in by_position]
    rows = dict(zip(point.positions, point.rows, strict=True))
    sweep = POINTS.get(point.key)
    strata = None if sweep is None else sweep.strata(common)
    gaps: dict[str, Any] = {}
    for level in sorted(float(level) for level in point.rows[0]):
        name = repr(level)
        if name not in baseline.rows[0]:
            continue
        mine = np.array([_contrast(rows[p][name], "h1") for p in common], dtype=np.float64) / pairs
        theirs = np.array(
            [_contrast(by_position[p][name], "h1") for p in common], dtype=np.float64
        ) / baseline_pairs
        if len(common) < 2:
            continue
        gaps[name] = _interval(_paired_interval(mine - theirs, strata))
    return {"baseline": baseline.key, "cities": len(common), "by_level": gaps}


def analyse(
    out: Path,
    mode: str,
    *,
    primary_out: Path | None = None,
    allow_reanalysis: bool = False,
    state: CodeState | None = None,
) -> dict[str, Any]:
    """
    The report for the run in `out`. The run must be of `mode`; its records
    must be declared cities of that mode; and the analysis must use the
    run's own code unless `allow_reanalysis`, in which case both revisions
    are recorded. A sweeps analysis also reads the primary run's first 48
    positions as the fitted reference, from `primary_out`.
    """
    recorded = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    if recorded["mode"] != mode:
        raise ValueError(f"{out} holds a {recorded['mode']} run, not {mode}")
    state = state or code_state()
    environment = manifest(mode, state)
    analysis = {k: environment[k] for k in ANALYSIS_BOUND}
    differs = [k for k in ANALYSIS_BOUND if recorded.get(k) != analysis[k]]
    same = not differs
    if not same and not allow_reanalysis:
        raise RuntimeError(
            f"the analysis differs from the simulation in {', '.join(differs)}; use the run's "
            "commit and environment, or pass allow_reanalysis to record both"
        )
    rows = load_records(out)
    declared = validate(rows, mode)
    expected: dict[str, set[int]] = {}
    for point, position in declared:
        expected.setdefault(point, set()).add(position)
    points = _group(rows)
    report: dict[str, Any] = {
        "mode": mode,
        "manifest": recorded,
        "analysis_revision": analysis,
        "reanalysis": not same,
        "points": {key: analyse_point(points[key], expected[key]) for key in sorted(points)},
        "missing_points": sorted(set(expected) - set(points)),
    }
    if mode == "sweeps":
        report["reference"] = _reference(primary_out, recorded, points, report["points"])
    return report


def _structural_baseline_key() -> str | None:
    return next(
        (
            key
            for key, p in POINTS.items()
            if p.population == "structural"
            and p.within_block_correlation is None
            and p.correlation == CES_MATCHED_CORRELATION
        ),
        None,
    )


def _reference(
    primary_out: Path | None,
    sweeps_manifest: dict[str, Any],
    points: dict[str, _Point],
    readings: dict[str, Any],
) -> dict[str, Any]:
    """
    The fitted primary configuration on positions 1-48, and each sweep
    point's gap to its declared baseline (second runner review):
      - fitted points against the fitted reference;
      - structural points against the structural CES-matched (0.87) point,
        within one generator;
      - the structural 0.87 point against the fitted reference, the gap
        between generators, reported first.
    """
    out: dict[str, Any] = {}
    structural = _structural_baseline_key()

    def complete(key: str) -> bool:
        return bool(readings.get(key, {}).get("complete"))

    if structural is not None and complete(structural):
        base = points[structural]
        out["structural_gaps"] = {
            key: _gap(points[key], base, readings[key]["pairs"], readings[structural]["pairs"])
            for key, sweep in POINTS.items()
            if sweep.population == "structural" and key != structural and complete(key)
        }
    else:
        out["structural_gaps"] = {"status": "structural 0.87 baseline not available"}

    if primary_out is None or not (primary_out / MANIFEST).exists():
        out["status"] = "primary run not available"
        return out
    primary_manifest = json.loads((primary_out / MANIFEST).read_text(encoding="utf-8"))
    for key in ("commit", "dirty", "diff_sha256", "beliefs_sha256", "protocol", "python", "numpy", "scipy"):
        if primary_manifest.get(key) != sweeps_manifest.get(key):
            out["status"] = f"primary run has a different {key}"
            return out
    rows = load_records(primary_out)
    validate(rows, "primary")
    group = _group(r for r in rows if int(r["position"]) <= SWEEP_CITIES)
    if not group:
        out["status"] = "primary run has no cities in positions 1-48"
        return out
    primary = next(iter(group.values()))
    primary.key = REFERENCE_KEY
    reading = analyse_point(primary, set(range(1, SWEEP_CITIES + 1)))
    out["status"] = "ok" if reading["complete"] else "incomplete"
    out["reading"] = reading
    if not reading["complete"]:
        return out
    out["fitted_gaps"] = {
        key: _gap(points[key], primary, readings[key]["pairs"], reading["pairs"])
        for key, sweep in POINTS.items()
        if sweep.population == "fitted" and key in points and complete(key)
    }
    if structural is not None and complete(structural):
        out["generator_gap"] = _gap(points[structural], primary, readings[structural]["pairs"], reading["pairs"])
    else:
        out["generator_gap"] = {"status": "structural 0.87 point not available"}
    return out


def write_report(out: Path, report: dict[str, Any]) -> Path:
    """report.json (every reading) and report.md (the headline lines)."""
    path = out / "report.json"
    path.write_text(_dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [f"# Demo 5 benchmark report ({report['mode']})", ""]
    manifest_ = report["manifest"]
    lines.append(f"Simulation commit `{manifest_['commit']}`{' (dirty)' if manifest_['dirty'] else ''}.")
    if report["reanalysis"]:
        rev = report["analysis_revision"]
        lines.append(f"Reanalysed with commit `{rev['commit']}`{' (dirty)' if rev['dirty'] else ''}.")
    lines.append("")

    def headline(key: str, point: dict[str, Any]) -> str:
        if not point.get("complete") or "threshold" not in point:
            return f"- **{key}**: incomplete ({point['cities']} of {point['expected_cities']} cities)"
        t = point["threshold"]
        low, high = t["confidence"]
        claimed = t["status"] in ("crosses", "liquid ahead throughout")
        gate = ("holds" if t["gate_holds"] else "fails") if claimed else "not applicable (no lead claimed)"
        return (
            f"- **{key}**: {t['verdict']}; bracket {t['bracket']}, interpolated "
            f"{t['interpolated']}, first supported {t['first_supported']}, nominal 95% set "
            f"({low}, {high}], gate {gate}, {point['cities']} cities"
        )

    reference = report.get("reference", {})
    if reference.get("status") == "ok":
        lines.append(headline(REFERENCE_KEY, reference["reading"]))
    elif reference:
        lines.append(f"- **reference**: {reference['status']}")
    for key, point in report["points"].items():
        lines.append(headline(key, point))
    for key in report["missing_points"]:
        lines.append(f"- **{key}**: not run")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
