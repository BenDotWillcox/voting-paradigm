"""The display queue must preserve exclusive ownership even on write failure."""

import json
from pathlib import Path

import pytest

from scripts import run_state_land_display as runner


@pytest.fixture
def queue(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "NAMESPACE", Path("generated"))
    monkeypatch.setattr(runner, "OUTPUT", Path("bundle"))
    monkeypatch.setattr(runner, "CATALOG", Path("catalog.json"))
    monkeypatch.setattr(runner, "validate_anchors", lambda _: ["01", "02", "26"])
    monkeypatch.setattr(runner, "runtime_hashes", lambda: {"runtime.py": "frozen"})
    (tmp_path / "bundle").mkdir()
    manifest = {"plans": {"01-1": {"stateFips": "01"}, "02-1": {"stateFips": "02"}, "26-1": {"stateFips": "26"}}}
    (tmp_path / "bundle/manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "bundle/server-index.json").write_text("{}")
    (tmp_path / "catalog.json").write_text("{}")
    cache = tmp_path / "cache"
    cache.mkdir()
    launches = []
    behavior = {"exitCode": 0, "status": "complete", "on_wait": None, "poll": 0}

    class Process:
        def __init__(self, command, **kwargs):
            self.command = command
            self.pid = 100 + len(launches)
            launches.append(self)
            self.state = command[-1]
            self.kwargs = kwargs

        def wait(self):
            directory = tmp_path / "generated/states"
            directory.mkdir(exist_ok=True)
            report = {
                "status": behavior["status"], "landDisplays": {f"{self.state}-1": {}},
                "geometryPlans": {f"{self.state}-1": {}},
                "audit": {"runtimeHashes": {"runtime.py": "frozen"}},
                "baseManifestSha256": runner.file_hash(tmp_path / "bundle/manifest.json"),
                "baseIndexSha256": runner.file_hash(tmp_path / "bundle/server-index.json"),
            }
            (directory / f"{self.state}.json").write_text(json.dumps(report))
            if behavior["on_wait"]:
                behavior["on_wait"]()
            return behavior["exitCode"]

        def poll(self):
            return behavior["poll"]

    monkeypatch.setattr(runner.subprocess, "Popen", Process)
    return tmp_path, cache, launches, behavior


def record(root):
    return json.loads((root / "generated/all-states.run.json").read_text())


def test_queue_is_serial_skips_michigan_and_pins_complete_reports(queue):
    root, cache, launches, _ = queue
    result = runner.run(root, cache)
    assert result["status"] == "complete"
    assert result["solverRuns"] == 0
    assert [process.state for process in launches] == ["02", "01"]
    assert all(process.kwargs["cwd"] == root for process in launches)
    assert all(job["status"] == "complete" and job["reportSha256"] for job in result["jobs"])
    assert result["activeState"] is None
    assert record(root) == result


def test_existing_ownership_record_refuses_second_launch(queue):
    root, cache, launches, _ = queue
    runner.run(root, cache)
    original = (root / "generated/all-states.run.json").read_bytes()
    with pytest.raises(FileExistsError):
        runner.run(root, cache)
    assert len(launches) == 2
    assert (root / "generated/all-states.run.json").read_bytes() == original


def test_failed_child_stops_queue_without_retry(queue):
    root, cache, launches, behavior = queue
    behavior["exitCode"] = 7
    with pytest.raises(RuntimeError, match="child exited 7"):
        runner.run(root, cache)
    saved = record(root)
    assert len(launches) == 1
    assert saved["status"] == "blocked"
    assert saved["jobs"][0]["status"] == "failed"
    assert saved["jobs"][1]["status"] == "pending"
    assert not saved["activeChildMayBeRunning"]


def test_terminal_report_mismatch_stops_queue_as_ambiguous(queue):
    root, cache, launches, behavior = queue
    behavior["status"] = "pending"
    with pytest.raises(ValueError, match="terminal report"):
        runner.run(root, cache)
    assert len(launches) == 1
    assert record(root)["jobs"][0]["status"] == "ambiguous"


def test_runtime_drift_stops_before_next_child(queue, monkeypatch):
    root, cache, launches, behavior = queue
    behavior["on_wait"] = lambda: monkeypatch.setattr(runner, "runtime_hashes", lambda: {"runtime.py": "changed"})
    with pytest.raises(ValueError, match="Frozen display runtime changed"):
        runner.run(root, cache)
    assert len(launches) == 1
    assert record(root)["jobs"][0]["status"] == "complete"
    assert record(root)["jobs"][1]["status"] == "pending"


def test_metadata_drift_stops_before_next_child(queue):
    root, cache, launches, behavior = queue
    behavior["on_wait"] = lambda: (root / "catalog.json").write_text('{"changed":true}')
    with pytest.raises(ValueError, match="Preserved app metadata changed"):
        runner.run(root, cache)
    assert len(launches) == 1
    assert record(root)["jobs"][1]["status"] == "pending"


def test_ownership_write_failure_preserves_live_child_and_never_duplicates(queue, monkeypatch):
    root, cache, launches, behavior = queue
    behavior["poll"] = None
    original_save = runner.save

    def fail_active(path, value):
        if value["status"] == "running" and any(job["status"] == "running" for job in value["jobs"]):
            raise PermissionError("reader collision persists")
        original_save(path, value)

    monkeypatch.setattr(runner, "save", fail_active)
    with pytest.raises(PermissionError, match="reader collision"):
        runner.run(root, cache)
    assert len(launches) == 1
    saved = record(root)
    assert saved["status"] == "blocked"
    assert saved["activeChildMayBeRunning"]
    emergency = json.loads(next((root / "generated").glob("emergency-02-*.json")).read_text())
    assert emergency["pid"] == launches[0].pid
    assert emergency["command"] == launches[0].command
    assert emergency["status"] == "child-may-be-active"
    with pytest.raises(FileExistsError):
        runner.run(root, cache)
    assert len(launches) == 1


def test_metadata_save_retries_transient_replace_collision(tmp_path, monkeypatch):
    original = Path.replace
    attempts = []

    def transient(self, target):
        attempts.append(target)
        if len(attempts) < 3:
            raise PermissionError("transient")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", transient)
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)
    runner.save(tmp_path / "run.json", {"status": "running"})
    assert len(attempts) == 3
    assert json.loads((tmp_path / "run.json").read_text()) == {"status": "running"}


def test_metadata_save_has_bounded_retry(tmp_path, monkeypatch):
    attempts = []

    def denied(self, target):
        attempts.append(target)
        raise PermissionError("persistent")

    monkeypatch.setattr(Path, "replace", denied)
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="Could not persist ownership"):
        runner.save(tmp_path / "run.json", {"status": "running"})
    assert len(attempts) == 12
