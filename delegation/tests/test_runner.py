from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

import pytest

from delegation.comparison import runner
from delegation.comparison.beliefs import BeliefCityConfig
from delegation.comparison.protocol import (
    DEVELOPMENT_SEEDS,
    PRIMARY_CITIES,
    PRIMARY_SEED_BASE,
    TURNOUT_GRID,
)
from delegation.comparison.runner import (
    CITIES,
    CONTRASTS,
    LOCK,
    MANIFEST,
    SMOKE_SEED_BASE,
    CityTask,
    CodeState,
    analyse,
    city_path,
    done,
    evaluate_level,
    load_records,
    manifest,
    point_key,
    primary_tasks,
    run,
    smoke_tasks,
    sweep_tasks,
    validate,
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
CLEAN = CodeState("0" * 40, False, None)


def _fitted(n: int = 2) -> list[CityTask]:
    return [t for t in smoke_tasks() if t.point == "smoke: fitted"][:n]


def test_one_level_records_what_the_protocol_needs():
    record = evaluate_level(TINY, frontier=True)
    assert record["pairs"] == 50 * 16
    assert set(record["matches"]) >= {first for first, _ in CONTRASTS.values()}
    assert all(0 <= v <= record["pairs"] for v in record["matches"].values())
    assert isinstance(record["liquid_meets_cap"], bool)
    assert len(record["frontier"]) == len(FRONTIER_FLOORS)
    assert record["frontier"][0] == record["matches"]["liquid"] - record["matches"]["representative"]
    assert record["frontier"] == sorted(record["frontier"])
    assert "frontier" not in evaluate_level(TINY, frontier=False)


def test_paired_attributions_add_back_to_the_differences():
    record = evaluate_level(TINY, frontier=False)
    for other in ("representative", "proxy"):
        a = record["attribution"][other]
        assert a["kept_difference"] + a["resolved_difference"] == (
            record["matches"]["liquid"] - record["matches"][other]
        )
        assert 0 <= a["kept_pairs"] <= record["pairs"]


def test_records_are_strict_json():
    record = evaluate_level(TINY, frontier=False)
    text = runner._dumps({"point": "x", "position": 1, "levels": {"0.5": record}})
    json.loads(text, parse_constant=lambda c: pytest.fail(f"non-standard constant {c}"))


def test_primary_tasks_use_the_primary_namespace_at_every_level():
    tasks = primary_tasks()
    assert len(tasks) == PRIMARY_CITIES
    assert all(t.frontier for t in tasks)
    assert tasks[0].levels[0][1].seed == PRIMARY_SEED_BASE + 1
    assert [level for level, _ in tasks[0].levels] == list(TURNOUT_GRID)


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


def test_a_run_writes_one_file_per_city_and_resumes(tmp_path):
    tasks = smoke_tasks()[:4]
    assert run(tasks, tmp_path, "smoke", state=CLEAN) == 4
    assert len(list((tmp_path / CITIES).glob("*/*.json"))) == 4
    assert done(tmp_path) == {(t.point, t.position) for t in tasks}
    assert not (tmp_path / LOCK).exists()
    assert run(tasks, tmp_path, "smoke", state=CLEAN) == 0


def test_an_interrupted_write_does_not_block_resume(tmp_path):
    tasks = _fitted(2)
    run(tasks[:1], tmp_path, "smoke", state=CLEAN)
    # A crash mid-write leaves only a temporary file behind
    stray = city_path(tmp_path, tasks[1].point, tasks[1].position).with_suffix(".tmp")
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text('{"point": "smoke: fitted", "posi')
    assert run(tasks, tmp_path, "smoke", state=CLEAN) == 1
    assert not stray.exists()
    assert len(load_records(tmp_path)) == 2


def test_a_city_is_never_recorded_twice(tmp_path):
    task = _fitted(1)[0]
    row = runner.run_task(task)
    runner._write_city(tmp_path, row)
    with pytest.raises(RuntimeError, match="already recorded"):
        runner._write_city(tmp_path, row)


def test_two_launches_cannot_share_a_directory(tmp_path):
    run([], tmp_path, "smoke", state=CLEAN)
    (tmp_path / LOCK).write_text("12345")
    with pytest.raises(RuntimeError, match="another run"):
        run(_fitted(1), tmp_path, "smoke", state=CLEAN)


def test_a_failed_city_keeps_the_others(tmp_path, monkeypatch):
    tasks = _fitted(3)
    original = runner.run_task

    def flaky(task: CityTask):  # type: ignore[no-untyped-def]
        if task.position == 2:
            raise ValueError("boom")
        return original(task)

    monkeypatch.setattr(runner, "run_task", flaky)
    with pytest.raises(RuntimeError, match="1 cities failed"):
        run(tasks, tmp_path, "smoke", state=CLEAN)
    assert done(tmp_path) == {(t.point, t.position) for t in tasks if t.position != 2}
    monkeypatch.setattr(runner, "run_task", original)
    assert run(tasks, tmp_path, "smoke", state=CLEAN) == 1


def test_a_run_is_bound_to_its_code_and_environment(tmp_path):
    run([], tmp_path, "smoke", state=CLEAN)
    assert json.loads((tmp_path / MANIFEST).read_text())["commit"] == CLEAN.commit
    with pytest.raises(RuntimeError, match="different commit"):
        run([], tmp_path, "smoke", state=CodeState("1" * 40, False, None))
    # Dirty records cannot be resumed by a clean checkout, nor the reverse
    with pytest.raises(RuntimeError, match="different dirty"):
        run([], tmp_path, "smoke", state=CodeState(CLEAN.commit, True, "a" * 64))
    dirty = tmp_path / "dirty"
    run([], dirty, "primary", allow_dirty=True, state=CodeState("2" * 40, True, "a" * 64))
    with pytest.raises(RuntimeError, match="different diff_sha256"):
        run([], dirty, "primary", allow_dirty=True, state=CodeState("2" * 40, True, "b" * 64))
    # A different numerical environment is refused too
    recorded = json.loads((tmp_path / MANIFEST).read_text())
    recorded["numpy"] = "0.0"
    (tmp_path / MANIFEST).write_text(json.dumps(recorded))
    with pytest.raises(RuntimeError, match="different numpy"):
        run([], tmp_path, "smoke", state=CLEAN)


def test_primary_and_sweep_runs_refuse_a_dirty_checkout(tmp_path):
    for mode in ("primary", "sweeps"):
        with pytest.raises(RuntimeError, match="uncommitted"):
            run([], tmp_path / mode, mode, state=CodeState("2" * 40, True, "c" * 64))


def test_analysis_rejects_undeclared_or_duplicated_cities(tmp_path):
    tasks = _fitted(2)
    rows = [runner.run_task(t) for t in tasks]
    assert set(validate(rows, "smoke")) >= {(t.point, t.position) for t in tasks}
    with pytest.raises(ValueError, match="more than once"):
        validate([rows[0], rows[0]], "smoke")
    with pytest.raises(ValueError, match="not a declared city"):
        validate(rows, "primary")
    altered = json.loads(json.dumps(rows[0]))
    first = next(iter(altered["levels"]))
    altered["levels"][first]["seed"] += 1
    with pytest.raises(ValueError, match="declared seed"):
        validate([altered], "smoke")


def test_analysis_is_bound_to_its_mode_and_code(tmp_path):
    run(_fitted(2), tmp_path, "smoke", state=CLEAN)
    with pytest.raises(ValueError, match="holds a smoke run"):
        analyse(tmp_path, "primary", state=CLEAN)
    other = CodeState("9" * 40, False, None)
    with pytest.raises(RuntimeError, match="differs from the simulation in commit"):
        analyse(tmp_path, "smoke", state=other)
    report = analyse(tmp_path, "smoke", state=other, allow_reanalysis=True)
    assert report["reanalysis"] is True
    assert report["analysis_revision"]["commit"] == other.commit


def test_analysis_reads_counts_through_the_protocol(tmp_path):
    run(smoke_tasks()[:4], tmp_path, "smoke", state=CLEAN)
    report = analyse(tmp_path, "smoke", state=CLEAN)
    point = report["points"]["smoke: fitted"]
    # Two of four declared smoke cities: incomplete, so no verdict
    assert point["complete"] is False and "threshold" not in point
    path = write_report(tmp_path, report)
    json.loads(path.read_text(), parse_constant=lambda c: pytest.fail(c))
    assert "incomplete" in (tmp_path / "report.md").read_text()


def test_a_complete_point_reports_every_reading(tmp_path):
    tasks = _fitted(4)
    run(tasks, tmp_path, "smoke", state=CLEAN)
    report = analyse(tmp_path, "smoke", state=CLEAN)
    point = report["points"]["smoke: fitted"]
    assert point["complete"] is True
    assert len(point["threshold"]["pointwise"]) == len(point["levels"])
    reading = point["by_level"][repr(point["levels"][0])]
    assert set(reading["decomposition"]) == set(CONTRASTS)
    assert "frontier" in reading
    # Gate failures are labelled, never omitted
    assert reading["h1"]["direction"] and reading["h1"]["all_cities"] is not None
    assert reading["specialisation"]["direction"]
    if reading["h1"]["cap_meeting_cities"] < 2:
        assert reading["h1"]["direction"] == "overhead condition not met"
        assert reading["specialisation"]["direction"] == "not assessable at matched overhead"
    # The paired attribution, and every secondary measure
    attribution = reading["attribution"]["liquid_minus_representative"]
    assert set(attribution) >= {"kept_contribution", "resolved_contribution", "difference", "kept_share"}
    liquid = reading["measures"]["liquid"]
    assert {"lifecycle_overhead", "delegations_per_voter", "outcome_agreement", "lost_share",
            "mean_loops", "below_half_none_share", "below_half_contrary_share"} <= set(liquid)


def test_sweeps_are_read_against_their_declared_baselines(tmp_path, monkeypatch):
    # Stand-in declared runs with small cities so the test stays quick
    small = dict(districts=2, residents_per_district=20, history_questions_per_topic=3,
                 evaluation_questions_per_topic=2)
    levels = (0.3, 0.7)

    def fitted_tasks(point: str, count: int, offset: int) -> list[CityTask]:
        return [
            CityTask(point, p, tuple((lv, BeliefCityConfig(seed=SMOKE_SEED_BASE + offset + p,
                                                          turnout_mean=lv, **small)) for lv in levels),
                     frontier=point.startswith("primary"))
            for p in range(1, count + 1)
        ]

    primary_key = point_key(runner.PRIMARY_POINT)
    structural_key = runner._structural_baseline_key()
    variant_key = next(k for k, p in runner.POINTS.items()
                       if p.population == "structural" and k != structural_key)
    history_key = next(k for k, p in runner.POINTS.items() if p.family == "history")
    monkeypatch.setattr(runner, "SWEEP_CITIES", 3)
    monkeypatch.setitem(runner.TASKS, "primary", lambda: fitted_tasks(primary_key, 4, 0))
    monkeypatch.setitem(
        runner.TASKS,
        "sweeps",
        lambda: fitted_tasks(structural_key, 3, 100) + fitted_tasks(variant_key, 3, 200)
        + fitted_tasks(history_key, 3, 300),
    )
    primary_out, sweeps_out = tmp_path / "primary", tmp_path / "sweeps"
    run(runner.TASKS["primary"](), primary_out, "primary", state=CLEAN)
    run(runner.TASKS["sweeps"](), sweeps_out, "sweeps", state=CLEAN)
    report = analyse(sweeps_out, "sweeps", primary_out=primary_out, state=CLEAN)
    reference = report["reference"]
    assert reference["status"] == "ok" and reference["reading"]["cities"] == 3
    # Fitted points against the fitted reference
    assert reference["fitted_gaps"][history_key]["baseline"] == runner.REFERENCE_KEY
    # Structural points against the structural 0.87 point, within one generator
    assert reference["structural_gaps"][variant_key]["baseline"] == structural_key
    # And the structural 0.87 point against the fitted reference
    assert reference["generator_gap"]["baseline"] == runner.REFERENCE_KEY
    write_report(sweeps_out, report)
    assert runner.REFERENCE_KEY in (sweeps_out / "report.md").read_text()


def test_sweep_gaps_are_paired_by_position():
    # The reviewer's case: 48 positions, the fitted H1 difference alternating
    # +2 and -2 (in matches over 100 pairs), the history difference 1 minus
    # the fitted one. Unpaired, the gap's interval excluded zero; paired it
    # is about [-0.17, +2.17] points
    history_key = next(k for k, p in runner.POINTS.items() if p.family == "history")

    def point(key: str, h1: list[int]) -> runner._Point:
        rows = [{"0.5": {"matches": {"liquid": d, "representative": 0}}} for d in h1]
        return runner._Point(key, list(range(1, len(h1) + 1)), rows)

    fitted = [2 if p % 2 else -2 for p in range(1, 49)]
    history = [1 - f for f in fitted]
    gap = runner._gap(point(history_key, history), point(runner.REFERENCE_KEY, fitted), 100, 100)
    interval = gap["by_level"]["0.5"]
    assert interval["estimate"] == pytest.approx(0.01)
    assert interval["lower"] < 0 < interval["upper"]
    assert interval["lower"] == pytest.approx(-0.0017, abs=0.0005)


def test_the_lock_comes_before_the_manifest(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / LOCK).write_text("12345")
    with pytest.raises(RuntimeError, match="another run"):
        run([], tmp_path, "smoke", state=CLEAN)
    assert not (tmp_path / MANIFEST).exists()


def test_no_manifest_is_created_beside_unknown_cities(tmp_path):
    row = runner.run_task(_fitted(1)[0])
    runner._write_city(tmp_path, row)
    with pytest.raises(RuntimeError, match="provenance is unknown"):
        run([], tmp_path, "smoke", state=CLEAN)


def test_analysis_is_bound_to_its_numerical_environment(tmp_path):
    run(_fitted(2), tmp_path, "smoke", state=CLEAN)
    recorded = json.loads((tmp_path / MANIFEST).read_text())
    recorded["scipy"] = "0.0"
    (tmp_path / MANIFEST).write_text(json.dumps(recorded))
    with pytest.raises(RuntimeError, match="scipy"):
        analyse(tmp_path, "smoke", state=CLEAN)
    report = analyse(tmp_path, "smoke", state=CLEAN, allow_reanalysis=True)
    assert report["reanalysis"] is True
    assert report["manifest"]["scipy"] == "0.0"
    assert report["analysis_revision"]["scipy"] != "0.0"


def test_an_interrupted_parent_keeps_finished_cities(tmp_path):
    tasks = smoke_tasks()
    calls = []

    def interrupt(count: int, total: int) -> None:
        calls.append(count)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run(tasks, tmp_path, "smoke", workers=2, state=CLEAN, progress=interrupt)
    recorded = done(tmp_path)
    # The first city and whatever was in flight are kept; queued cities never ran
    assert 1 <= len(recorded) < len(tasks)
    assert not (tmp_path / LOCK).exists()
    # A rerun repeats only what is missing
    assert run(tasks, tmp_path, "smoke", state=CLEAN) == len(tasks) - len(recorded)


def _rotating_gap(by_topic_gap):  # type: ignore[no-untyped-def]
    rotating = next(k for k, p in runner.POINTS.items() if p.family == "evaluation_mix")

    def point(key: str, h1: list[int]) -> runner._Point:
        rows = [{"0.5": {"matches": {"liquid": d, "representative": 0}}} for d in h1]
        return runner._Point(key, list(range(1, len(h1) + 1)), rows)

    gaps = [by_topic_gap(p) for p in range(1, 49)]
    return runner._gap(point(rotating, gaps), point(runner.REFERENCE_KEY, [0] * 48), 80_000, 80_000)


def test_rotating_gaps_use_satterthwaite_degrees_of_freedom():
    # The reviewer's case: seven topics with zero gap, the eighth topic's six
    # cities at [0, 0, 0, 1600, 1600, 1600] per 80,000 pairs. Only that topic
    # supplies variance, with five degrees of freedom, not 40
    eighth = {8: 0, 16: 0, 24: 0, 32: 1600, 40: 1600, 48: 1600}
    gap = _rotating_gap(lambda p: eighth.get(p, 0))["by_level"]["0.5"]
    assert gap["estimate"] == pytest.approx(0.00125)
    assert gap["lower"] < 0 < gap["upper"]
    assert gap["lower"] == pytest.approx(-0.00019, abs=0.00002)


def test_an_exactly_zero_gap_stays_zero():
    # Constant signed gaps by topic summing to exactly zero over the rotation
    by_topic = [16, -28, 1, 10, 12, -24, 16, -3]
    gap = _rotating_gap(lambda p: by_topic[(p - 1) % 8])["by_level"]["0.5"]
    assert gap["estimate"] == 0.0 and gap["lower"] == 0.0 and gap["upper"] == 0.0


def test_an_interrupt_during_submission_keeps_what_ran(tmp_path, monkeypatch):
    real = runner.ProcessPoolExecutor

    class Interrupting(real):  # type: ignore[misc, valid-type]
        submitted = 0

        def submit(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            Interrupting.submitted += 1
            if Interrupting.submitted == 4:
                raise KeyboardInterrupt
            return super().submit(*args, **kwargs)

    monkeypatch.setattr(runner, "ProcessPoolExecutor", Interrupting)
    tasks = smoke_tasks()
    with pytest.raises(KeyboardInterrupt):
        run(tasks, tmp_path, "smoke", workers=2, state=CLEAN)
    recorded = done(tmp_path)
    # The three submitted before the interrupt ran or were cancelled while
    # queued; whatever ran is kept, and nothing was lost to the interrupt
    assert 1 <= len(recorded) <= 3
    monkeypatch.setattr(runner, "ProcessPoolExecutor", real)
    assert run(tasks, tmp_path, "smoke", state=CLEAN) == len(tasks) - len(recorded)


def test_an_interrupt_before_the_rename_keeps_that_city(tmp_path, monkeypatch):
    real_replace = runner.os.replace
    state = {"raised": False}

    def replace(src, dst):  # type: ignore[no-untyped-def]
        if not state["raised"] and str(dst).endswith(".json") and CITIES in str(dst):
            state["raised"] = True
            raise KeyboardInterrupt
        return real_replace(src, dst)

    monkeypatch.setattr(runner.os, "replace", replace)
    tasks = smoke_tasks()[:4]
    with pytest.raises(KeyboardInterrupt):
        run(tasks, tmp_path, "smoke", workers=2, state=CLEAN)
    recorded = done(tmp_path)
    # The city whose rename was interrupted is written in recovery
    assert len(recorded) >= 1
    assert not list((tmp_path / CITIES).glob("*/*.tmp"))
    monkeypatch.setattr(runner.os, "replace", real_replace)
    assert run(tasks, tmp_path, "smoke", state=CLEAN) == len(tasks) - len(recorded)


def test_the_frozen_protocol_is_unchanged():
    # A tripwire for the freeze (2026-11-19): the declared constants and
    # every primary and sweep city's exact settings. A change here must come
    # with a dated amendment in the design doc, made before any result it
    # could affect is seen
    protocol = manifest("primary", CLEAN)["protocol"]
    assert protocol == {
        "frozen": "2026-11-19",
        "turnout_grid": [0.1, 0.2, 0.3, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8, 0.9],
        "swiss_marker": 0.45,
        "primary_cities": 200,
        "primary_seed_base": 1_000_000_000,
        "sweep_cities": 48,
        "frontier_floors": [0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 0.96, 1.0],
        "bootstrap_resamples": 2000,
        "bootstrap_seed": 20261118,
        "cap": 0.1,
        "feasible_share": 0.95,
        "confidence": 0.95,
        "delta": 0.02,
    }
    tasks = primary_tasks() + sweep_tasks()
    declared = [
        {
            "point": t.point,
            "position": t.position,
            "frontier": t.frontier,
            "levels": [[level, type(config).__name__, asdict(config)] for level, config in t.levels],
        }
        for t in tasks
    ]
    digest = hashlib.sha256(runner._dumps(declared, sort_keys=True).encode()).hexdigest()
    assert len(tasks) == PRIMARY_CITIES + len(SWEEPS) * SWEEP_CITIES
    assert digest == "f2a8671602e6311f91f8ea907a889139f0a50d79a24c37dc9693060f87eac857"
