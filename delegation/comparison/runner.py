"""
The benchmark runner for demo 5's study: it simulates the declared cities,
records what the protocol needs from each, and reads the verdicts with
`protocol.py`. Design: prompts/demo-5-liquid-democracy.md, "Research
protocol" and "Robustness sweeps".

  Primary   200 cities (protocol.primary_city_seeds), each at every level of
            the turnout dial, with the attendance frontier recounted at
            every floor
  Sweeps    every declared sweep point on its 48 cities, at every level
  Smoke     a few small cities on development seeds, to check the pipeline
            end to end; never the primary namespace

Each city's levels run in one task, so a city keeps its residents across
the dial. A task's record is appended to `records.jsonl` and synced before
the next is taken, so an interrupted run resumes where it stopped. The
manifest binds a run to one code commit; primary and sweep runs refuse a
dirty checkout unless told otherwise, and a resumed run must match the
manifest.

What each city-level records: every arrangement's matching-ballot count,
the voter-question pairs, whether liquid and the proxy meet the overhead
cap, the calibration, every arrangement's measures, and for primary cities
liquid's matches minus the representative's at each frontier floor. Signed
counts keep ties exact; the protocol converts them to fidelity.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

import numpy as np

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
from .sweeps import FRONTIER_FLOORS, PRIMARY_POINT, SWEEP_CITIES, SWEEPS, SweepPoint

RUNNER_VERSION: Final = 1
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
# Measures averaged over cities in the report
REPORTED_MEASURES: Final = (
    "fidelity",
    "contrary_share",
    "none_share",
    "overhead",
    "resolver_attendance",
    "loop_share",
    "mean_largest_share",
    "light_record_share",
    "light_record_fidelity",
    "empty_record_share",
    "empty_record_fidelity",
)

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
    small = dict(
        districts=2,
        residents_per_district=30,
        history_questions_per_topic=4,
        evaluation_questions_per_topic=3,
    )
    tasks: list[CityTask] = []
    for position in range(1, SMOKE_CITIES + 1):
        seed = SMOKE_SEED_BASE + position
        tasks.append(
            CityTask(
                "smoke: fitted",
                position,
                tuple(
                    (level, BeliefCityConfig(seed=seed, turnout_mean=level, **small))  # type: ignore[arg-type]
                    for level in SMOKE_LEVELS
                ),
                frontier=True,
            )
        )
        structural = PopulationConfig(
            seed=seed,
            districts=2,
            residents_per_district=30,
            dimensions=8,
            history_questions_per_dimension=4,
            evaluation_questions_per_dimension=3,
        )
        tasks.append(
            CityTask(
                "smoke: structural",
                position,
                tuple(
                    (level, PopulationConfig(**{**asdict(structural), "turnout_mean": level}))
                    for level in SMOKE_LEVELS
                ),
                frontier=False,
            )
        )
    return tasks


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
    matches = {
        name: int((outcome.counted == sincere).sum()) for name, outcome in result.outcomes.items()
    }
    measures = {name: asdict(m) for name, m in result.measures.items()}
    record: dict[str, Any] = {
        "seed": config.seed,
        "turnout_mean": config.turnout_mean,
        "pairs": int(sincere.size),
        "matches": matches,
        "liquid_meets_cap": bool(result.measures["liquid"].overhead <= CAP + 1e-12),
        "proxy_meets_cap": bool(result.measures["proxy"].overhead <= CAP + 1e-12),
        "liquid_acceptance": asdict(result.liquid_acceptance),
        "proxy_acceptance": asdict(result.proxy_acceptance),
        "measures": measures,
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
# Running, checkpointing and the manifest
# ---------------------------------------------------------------------------

RECORDS: Final = "records.jsonl"
MANIFEST: Final = "manifest.json"


def _git(*args: str) -> str:
    root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def code_state() -> tuple[str, bool]:
    """The commit and whether tracked files differ from it."""
    commit = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    return commit, dirty


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest(mode: str, commit: str, dirty: bool) -> dict[str, Any]:
    """What binds a run to its code, data and declared settings."""
    return {
        "runner_version": RUNNER_VERSION,
        "mode": mode,
        "commit": commit,
        "dirty": dirty,
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
    }


def done(out: Path) -> set[tuple[str, int]]:
    """The (point, position) pairs already recorded."""
    path = out / RECORDS
    if not path.exists():
        return set()
    finished = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                finished.add((row["point"], int(row["position"])))
    return finished


def _append(out: Path, row: dict[str, Any]) -> None:
    with (out / RECORDS).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _prepare(out: Path, mode: str, allow_dirty: bool, state: tuple[str, bool] | None) -> None:
    commit, dirty = state if state is not None else code_state()
    if dirty and mode != "smoke" and not allow_dirty:
        raise RuntimeError(
            "the checkout has uncommitted changes; primary and sweep runs must come from a "
            "committed state (pass allow_dirty only for development)"
        )
    out.mkdir(parents=True, exist_ok=True)
    path = out / MANIFEST
    current = manifest(mode, commit, dirty)
    if path.exists():
        recorded = json.loads(path.read_text(encoding="utf-8"))
        for key in ("runner_version", "mode", "commit", "beliefs_sha256", "protocol", "sweeps"):
            if recorded.get(key) != current[key]:
                raise RuntimeError(f"{out} holds a run with a different {key}; use another directory")
        return
    current["started"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")


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
    state: tuple[str, bool] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """
    Run every task not yet recorded in `out`, checkpointing after each.
    Returns how many tasks ran. `state` overrides the git check (tests).
    """
    _prepare(out, mode, allow_dirty, state)
    finished = done(out)
    todo = [t for t in tasks if (t.point, t.position) not in finished]
    total = len(todo)
    if workers <= 1:
        for count, task in enumerate(todo, 1):
            _append(out, run_task(task))
            if progress:
                progress(count, total)
        return total
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as pool:
        futures = [pool.submit(run_task, task) for task in todo]
        for count, future in enumerate(as_completed(futures), 1):
            _append(out, future.result())
            if progress:
                progress(count, total)
    return total


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def load_records(out: Path) -> list[dict[str, Any]]:
    with (out / RECORDS).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _interval(i: Interval) -> dict[str, float]:
    return {"estimate": i.estimate, "lower": i.lower, "upper": i.upper}


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


def _matrix(point: _Point, levels: Sequence[float], read: Callable[[dict[str, Any]], float]) -> np.ndarray:
    return np.array([[read(row[repr(level)]) for level in levels] for row in point.rows])


def _contrast(record: dict[str, Any], name: str) -> int:
    first, second = CONTRASTS[name]
    return int(record["matches"][first] - record["matches"][second])


def _contrast_column(point: _Point, level: float, name: str) -> np.ndarray:
    """One contrast's signed counts over a point's cities at one level."""
    return np.array([_contrast(row[repr(level)], name) for row in point.rows], dtype=np.float64)


def analyse_point(point: _Point, expected: int | None = None) -> dict[str, Any]:
    """Every protocol reading for one point, from its cities' records."""
    levels = sorted(float(level) for level in point.rows[0])
    if any(sorted(float(level) for level in row) != levels for row in point.rows):
        raise ValueError(f"{point.key}: cities differ in their levels")
    pairs_all = {rec["pairs"] for row in point.rows for rec in row.values()}
    if len(pairs_all) != 1:
        raise ValueError(f"{point.key}: cities differ in their voter-question pairs")
    pairs = pairs_all.pop()
    sweep = POINTS.get(point.key)
    strata = None if sweep is None else sweep.strata(point.positions)
    cities = len(point.positions)
    out: dict[str, Any] = {
        "cities": cities,
        "complete": expected is None or cities == expected,
        "levels": levels,
        "pairs": pairs,
    }
    if (expected is not None and cities != expected) or cities < 2:
        out["complete"] = False
        return out
    h1 = _matrix(point, levels, lambda r: _contrast(r, "h1"))
    cap = _matrix(point, levels, lambda r: r["liquid_meets_cap"]).astype(bool)
    proxy_cap = _matrix(point, levels, lambda r: r["proxy_meets_cap"]).astype(bool)
    out["threshold"] = _threshold(threshold(tuple(levels), h1, cap, pairs=pairs, strata=strata))

    by_level: dict[str, Any] = {}
    for j, level in enumerate(levels):
        reading: dict[str, Any] = {"cap_share": float(cap[:, j].mean())}
        meeting = cap[:, j]
        if meeting.sum() >= 2:
            all_i = t_interval(h1[:, j] / pairs)
            cap_i = t_interval(h1[meeting, j] / pairs)
            reading["h1"] = {
                "all_cities": _interval(all_i),
                "cap_meeting": _interval(cap_i),
                "direction": h1_verdict(all_i, cap_i, float(meeting.mean())),
                "size": h1_size_verdict(all_i, cap_i, float(meeting.mean())),
            }
        spec = _contrast_column(point, level, "specialisation")
        both = cap[:, j] & proxy_cap[:, j]
        share = joint_share(cap[:, j], proxy_cap[:, j])
        reading["specialisation"] = {
            "joint_share": share,
            "liquid_share": float(cap[:, j].mean()),
            "proxy_share": float(proxy_cap[:, j].mean()),
        }
        if both.sum() >= 2:
            all_s = t_interval(spec / pairs)
            both_s = t_interval(spec[both] / pairs)
            sign, size = specialisation_verdict(all_s, both_s, share)
            reading["specialisation"].update(
                all_cities=_interval(all_s), both_meet_cap=_interval(both_s), direction=sign, size=size
            )
        reading["decomposition"] = {
            name: _interval(t_interval(_contrast_column(point, level, name) / pairs))
            for name in CONTRASTS
        }
        reading["measures"] = {
            arm: {
                m: _nanmean([row[repr(level)]["measures"][arm][m] for row in point.rows])
                for m in REPORTED_MEASURES
            }
            for arm in point.rows[0][repr(level)]["measures"]
        }
        if "frontier" in point.rows[0][repr(level)]:
            counts = np.array([row[repr(level)]["frontier"] for row in point.rows])
            reading["frontier"] = asdict(frontier_reading(FRONTIER_FLOORS, counts, cap[:, j], pairs=pairs))
        by_level[repr(level)] = reading
    out["by_level"] = by_level
    if SWISS_MARKER in levels:
        out["swiss_marker"] = by_level[repr(SWISS_MARKER)]
    return out


def _nanmean(values: Sequence[float]) -> float | None:
    data = np.array(values, dtype=np.float64)
    data = data[np.isfinite(data)]
    return float(data.mean()) if data.size else None


def analyse(out: Path, mode: str) -> dict[str, Any]:
    """The report for every point recorded in `out`."""
    points = _group(load_records(out))
    expected = {"primary": PRIMARY_CITIES, "sweeps": SWEEP_CITIES}.get(mode)
    return {
        "mode": mode,
        "manifest": json.loads((out / MANIFEST).read_text(encoding="utf-8")),
        "points": {key: analyse_point(point, expected) for key, point in points.items()},
    }


def _json_safe(value: Any) -> Any:
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


def write_report(out: Path, report: dict[str, Any]) -> Path:
    """report.json (every reading) and report.md (the headline lines)."""
    path = out / "report.json"
    path.write_text(json.dumps(_json_safe(report), indent=2) + "\n", encoding="utf-8")
    lines = [f"# Demo 5 benchmark report ({report['mode']})", ""]
    manifest_ = report["manifest"]
    lines.append(f"Commit `{manifest_['commit']}`{' (dirty)' if manifest_['dirty'] else ''}.")
    lines.append("")
    for key, point in report["points"].items():
        if not point.get("complete", True) or "threshold" not in point:
            lines.append(f"- **{key}**: incomplete ({point['cities']} cities)")
            continue
        t = point["threshold"]
        low, high = t["confidence"]
        claimed = t["status"] in ("crosses", "liquid ahead throughout")
        gate = ("holds" if t["gate_holds"] else "fails") if claimed else "not applicable (no lead claimed)"
        lines.append(
            f"- **{key}**: {t['verdict']}; bracket {t['bracket']}, interpolated "
            f"{t['interpolated']}, first supported {t['first_supported']}, nominal 95% set "
            f"({low}, {high}], gate {gate}, {point['cities']} cities"
        )
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path

