from __future__ import annotations

import json

import numpy as np
import pytest

from delegation.comparison.beliefs import BeliefCityConfig
from delegation.comparison.protocol import (
    DEVELOPMENT_SEEDS,
    PRIMARY_CITIES,
    PRIMARY_SEED_BASE,
    TURNOUT_GRID,
)
from delegation.comparison.runner import (
    CONTRASTS,
    MANIFEST,
    RECORDS,
    SMOKE_SEED_BASE,
    analyse,
    done,
    evaluate_level,
    point_key,
    primary_tasks,
    run,
    smoke_tasks,
    sweep_tasks,
    write_report,
)
from delegation.comparison.sweeps import FRONTIER_FLOORS, SWEEP_CITIES, SWEEPS

TINY = BeliefCityConfig(
    seed=SMOKE_SEED_BASE + 99,
    districts=2,
    residents_per_district=25,
    history_questions_per_topic=3,
    evaluation_questions_per_topic=2,
    turnout_mean=0.5,
)
CLEAN = ("0" * 40, False)


def test_one_level_records_what_the_protocol_needs():
    record = evaluate_level(TINY, frontier=True)
    assert record["pairs"] == 50 * 16
    assert set(record["matches"]) >= {first for first, _ in CONTRASTS.values()}
    assert all(0 <= v <= record["pairs"] for v in record["matches"].values())
    assert isinstance(record["liquid_meets_cap"], bool)
    assert len(record["frontier"]) == len(FRONTIER_FLOORS)
    # Floor 0 is the dial's own condition, and raising the floor only adds ballots
    assert record["frontier"][0] == record["matches"]["liquid"] - record["matches"]["representative"]
    assert record["frontier"] == sorted(record["frontier"])
    assert "frontier" not in evaluate_level(TINY, frontier=False)


def test_primary_tasks_use_the_primary_namespace_at_every_level():
    tasks = primary_tasks()
    assert len(tasks) == PRIMARY_CITIES
    assert all(t.frontier for t in tasks)
    assert tasks[0].levels[0][1].seed == PRIMARY_SEED_BASE + 1
    assert [level for level, _ in tasks[0].levels] == list(TURNOUT_GRID)
    assert all(config.turnout_mean == level for t in tasks[:3] for level, config in t.levels)


def test_sweep_tasks_cover_every_point_on_its_cities():
    tasks = sweep_tasks()
    assert len(tasks) == len(SWEEPS) * SWEEP_CITIES
    assert not any(t.frontier for t in tasks)
    one = sweep_tasks(point_key(SWEEPS[0]))
    assert len(one) == SWEEP_CITIES and {t.point for t in one} == {point_key(SWEEPS[0])}
    with pytest.raises(ValueError):
        sweep_tasks("no such point")


def test_smoke_never_touches_the_primary_namespace():
    seeds = {config.seed for t in smoke_tasks() for _, config in t.levels}
    assert all(seed < PRIMARY_SEED_BASE for seed in seeds)
    assert not seeds & DEVELOPMENT_SEEDS


def test_a_run_checkpoints_resumes_and_reports(tmp_path):
    # Two cities of each smoke point
    tasks = smoke_tasks()[:4]
    assert run(tasks, tmp_path, "smoke", state=CLEAN) == 4
    assert len((tmp_path / RECORDS).read_text().splitlines()) == 4
    assert done(tmp_path) == {(t.point, t.position) for t in tasks}
    # Resuming does nothing new
    assert run(tasks, tmp_path, "smoke", state=CLEAN) == 0
    report = analyse(tmp_path, "smoke")
    assert set(report["points"]) == {t.point for t in tasks}
    for point in report["points"].values():
        assert "threshold" in point and "verdict" in point["threshold"]
    path = write_report(tmp_path, report)
    reloaded = json.loads(path.read_text())
    assert reloaded["mode"] == "smoke"
    assert (tmp_path / "report.md").read_text().startswith("# Demo 5 benchmark report")


def test_a_run_is_bound_to_its_commit(tmp_path):
    run([], tmp_path, "smoke", state=CLEAN)
    assert json.loads((tmp_path / MANIFEST).read_text())["commit"] == CLEAN[0]
    with pytest.raises(RuntimeError, match="different commit"):
        run([], tmp_path, "smoke", state=("1" * 40, False))


def test_primary_and_sweep_runs_refuse_a_dirty_checkout(tmp_path):
    for mode in ("primary", "sweeps"):
        with pytest.raises(RuntimeError, match="uncommitted"):
            run([], tmp_path / mode, mode, state=("2" * 40, True))
    # Allowed explicitly for development, and recorded
    run([], tmp_path / "dev", "primary", allow_dirty=True, state=("2" * 40, True))
    assert json.loads((tmp_path / "dev" / MANIFEST).read_text())["dirty"] is True


def test_analysis_reads_counts_through_the_protocol(tmp_path):
    tasks = [t for t in smoke_tasks() if t.point == "smoke: fitted"][:2]
    run(tasks, tmp_path, "smoke", state=CLEAN)
    point = analyse(tmp_path, "smoke")["points"][tasks[0].point]
    levels = point["levels"]
    assert len(point["threshold"]["pointwise"]) == len(levels)
    reading = point["by_level"][repr(levels[0])]
    assert set(reading["decomposition"]) == set(CONTRASTS)
    assert "frontier" in reading
    assert np.isfinite(reading["measures"]["liquid"]["fidelity"])


def test_a_point_with_one_city_is_reported_incomplete(tmp_path):
    run(smoke_tasks()[:1], tmp_path, "smoke", state=CLEAN)
    point = next(iter(analyse(tmp_path, "smoke")["points"].values()))
    assert point["complete"] is False and "threshold" not in point

