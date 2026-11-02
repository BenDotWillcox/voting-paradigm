"""Bounded recovery preserves original evidence and retains child ownership."""

from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import recover_state_block_suite as recovery


def original_suite() -> dict[str, Any]:
    states: dict[str, dict[str, Any]] = {}
    for fips, count, _ in recovery.JOBS:
        state = states.setdefault(fips, {"state_fips": fips, "state": f"State {fips}", "status": "failed", "error": "original state failure", "jobs": []})
        state["jobs"].append({
            "district_count": count, "house_sizes": [574], "relative_output": f"states/{fips}/districts-{count}",
            "status": "failed", "error": "original failure", "started_at": "original-start", "finished_at": "original-finish",
            "timed_pipeline_wall_seconds": 12.5, "elapsed_wall_seconds": 13.0,
            "pid": 123, "latest_progress": "old error",
        })
    for fips, count in (("24", 19), ("51", 26)):
        states[fips] = {"state_fips": fips, "state": f"State {fips}", "status": "failed", "jobs": [
            {"district_count": count, "status": "failed", "error": "geometry failure", "relative_output": f"states/{fips}/districts-{count}"},
        ]}
    return {"status": "finished_with_exceptions", "house_sizes": list(recovery.HOUSE_SIZES),
            "started_at": "suite-start", "finished_at": "suite-finish", "elapsed_wall_seconds": 99.5,
            "counts": {"failed": 9}, "states": list(states.values())}


def test_merge_preserves_original_history_timings_and_geometry_failures() -> None:
    original = original_suite()
    original_copy = deepcopy(original)
    live = recovery.prepare_live_suite(original, "recoveries/test/recovery.json", "recovery-start")
    _, old = recovery.find_job(original, "49", 10)
    state, current = recovery.find_job(live, "49", 10)
    assert current["recovery_history"][0]["original_job"] == old
    assert state["recovery_history"][0]["original_state"] == original["states"][0]
    assert live["status"] == "recovering"
    assert current["status"] == "queued_recovery"
    attempt = {"state_fips": "49", "district_count": 10, "process_exit_code": 0,
               "started_at": "new-start", "finished_at": "new-end", "wall_seconds": 88.0}
    recovery.merge_attempt(live, attempt, {"status": "complete", "timed_pipeline_wall_seconds": 80.0, "final_plan": {"district_populations": [1]}})
    assert current["status"] == "complete"
    for field in recovery.PRESERVED_TIMINGS:
        assert live[field] == original[field]
        if field in old:
            assert current[field] == old[field]
    assert current["timed_pipeline_wall_seconds"] == 80.0
    assert current["recovery_pipeline_wall_seconds"] == 88.0
    assert current["recovery_history"][0]["original_job"]["timed_pipeline_wall_seconds"] == 12.5
    assert "error" not in current
    assert "result complete" in current["latest_progress"]
    assert recovery.find_job(live, "24", 19)[1] == recovery.find_job(original, "24", 19)[1]
    assert recovery.find_job(live, "51", 26)[1] == recovery.find_job(original, "51", 26)[1]
    assert original == original_copy


def test_nonzero_child_exit_overrides_stale_complete_report() -> None:
    live = recovery.prepare_live_suite(original_suite(), "ref", "now")
    attempt = {"state_fips": "34", "district_count": 16, "process_exit_code": 1, "error": "lock refused"}
    recovery.merge_attempt(live, attempt, {"status": "complete", "timed_pipeline_wall_seconds": 365})
    job = recovery.find_job(live, "34", 16)[1]
    assert job["status"] == "failed"
    assert job["error"] == "lock refused"


def test_reused_result_distinguishes_original_runtime_from_validation() -> None:
    live = recovery.prepare_live_suite(original_suite(), "ref", "now")
    attempt = {"state_fips": "34", "district_count": 16, "process_exit_code": 0,
               "wall_seconds": 7.5, "benchmark_result_reused": True}
    recovery.merge_attempt(live, attempt, {"status": "complete", "timed_pipeline_wall_seconds": 365})
    job = recovery.find_job(live, "34", 16)[1]
    assert job["timed_pipeline_wall_seconds"] == 365
    assert job["recovery_pipeline_wall_seconds"] == 7.5
    assert job["benchmark_result_reused"] is True


def test_queue_lock_refuses_second_owner(tmp_path: Path) -> None:
    with recovery.queue_ownership(tmp_path):
        with pytest.raises(recovery.RecoveryAdmissionError, match="owns queue.lock"):
            with recovery.queue_ownership(tmp_path):
                pass
    with recovery.queue_ownership(tmp_path):
        pass


def test_initialization_snapshots_exact_bytes_and_refuses_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = original_suite()
    source_bytes = json.dumps(original, indent=4).encode()
    (tmp_path / "suite.json").write_bytes(source_bytes)
    monkeypatch.setattr(recovery, "state_execution_lock", lambda *args: nullcontext())
    monkeypatch.setattr(recovery, "verify_frozen_code", lambda *args: {"report": "baseline", "code_sha256": {}})
    runner = recovery.RecoveryRunner(tmp_path)
    runner.initialize()
    assert (runner.directory / "original-suite.json").read_bytes() == source_bytes
    assert runner.manifest["original_suite_sha256"] == recovery.hashlib.sha256(source_bytes).hexdigest()
    assert json.loads((tmp_path / "suite.json").read_text())["status"] == "recovering"
    before = (runner.directory / "recovery.json").read_bytes()
    with pytest.raises(recovery.RecoveryAdmissionError, match="already exists"):
        recovery.RecoveryRunner(tmp_path).initialize()
    assert (runner.directory / "recovery.json").read_bytes() == before


def test_busy_state_refuses_admission_without_metadata_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_bytes = json.dumps(original_suite()).encode()
    (tmp_path / "suite.json").write_bytes(original_bytes)

    def busy(*args: Any) -> Any:
        raise RuntimeError("state busy")

    monkeypatch.setattr(recovery, "state_execution_lock", busy)
    with pytest.raises(RuntimeError, match="state busy"):
        recovery.RecoveryRunner(tmp_path).initialize()
    assert (tmp_path / "suite.json").read_bytes() == original_bytes
    assert not (tmp_path / "recoveries").exists()


def test_atomic_metadata_retries_permission_failure_with_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_replace = Path.replace
    calls = 0

    def transient(path: Path, target: Any) -> Path:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise PermissionError("sharing violation")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", transient)
    monkeypatch.setattr(recovery.time, "sleep", lambda _: None)
    recovery.atomic_json(tmp_path / "metadata.json", {"ok": True})
    assert calls == 3
    assert json.loads((tmp_path / "metadata.json").read_text()) == {"ok": True}
    calls = 0
    with pytest.raises(recovery.MetadataWriteError, match="2 attempts"):
        recovery.atomic_json(tmp_path / "metadata.json", {"ok": False}, attempts=2)
    assert calls == 2
    assert json.loads((tmp_path / "metadata.json").read_text()) == {"ok": True}


def test_child_is_waited_and_result_retained_when_pid_metadata_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = recovery.RecoveryRunner(tmp_path)
    runner.directory.mkdir(parents=True)
    runner.original = original_suite()
    runner.suite = recovery.prepare_live_suite(runner.original, "ref", "now")
    runner.manifest = {"metadata_warnings": []}
    attempt = {"state_fips": "49", "district_count": 10, "status": "queued", "kind": "single_operational_retry"}
    report_path = tmp_path / "states/49/districts-10/benchmark.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps({"status": "complete", "timed_pipeline_wall_seconds": 1}))
    monkeypatch.setattr(recovery, "state_execution_lock", lambda *args: nullcontext())
    monkeypatch.setattr(recovery, "verify_frozen_code", lambda *args: {})
    monkeypatch.setattr(recovery, "generate_viewer", lambda *args: None)
    save_calls = 0

    def save() -> None:
        nonlocal save_calls
        save_calls += 1
        if save_calls == 2:
            raise recovery.MetadataWriteError("persistent PID sharing error")

    monkeypatch.setattr(runner, "save", save)

    class Child:
        pid = 456
        returncode: int | None = None
        waited = False

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            self.waited = True
            self.returncode = 0
            return 0

    child = Child()

    def launch(*args: Any, **kwargs: Any) -> Child:
        assert kwargs["stdout"] != recovery.subprocess.PIPE
        assert kwargs["stderr"] == recovery.subprocess.STDOUT
        assert not kwargs["stdout"].closed
        return child

    monkeypatch.setattr(recovery.subprocess, "Popen", launch)
    runner.run_child(attempt)
    assert child.waited
    assert attempt["pid"] == 456
    assert attempt["process_exit_code"] == 0
    assert attempt["status"] == "complete"
    assert recovery.find_job(runner.suite, "49", 10)[1]["status"] == "complete"
    assert save_calls == 3
    assert runner.manifest["metadata_warnings"]
