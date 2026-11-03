"""Queue scope, deduplication, and generated-source cleanup boundaries."""

from pathlib import Path
import io
import json
from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any

import pytest

from scripts.run_state_block_suite import HOUSE_SIZES, clean_extracted_source, make_plan
from scripts import run_state_block_suite as suite
from scripts.precompute_state_districts import STATE_NAMES


@pytest.fixture(autouse=True)
def isolated_state_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    # OS lock behavior has its own tests; queue tests never acquire a live
    # benchmark state's lock in the shared workspace.
    @contextmanager
    def unlocked(state_fips: str) -> Iterator[None]:
        yield

    monkeypatch.setattr(suite, "state_execution_lock", unlocked)


def test_remaining_states_skip_large_anchor_and_deduplicate_same_seats() -> None:
    states = [fips for fips in STATE_NAMES if fips != "20"]
    plan = make_plan(states, list(HOUSE_SIZES))
    assert len(plan) == 49
    assert sum(len(state["jobs"]) for state in plan) == 177
    assert all(cap <= 1000 for state in plan for job in state["jobs"] for cap in job["house_sizes"])
    assert next(state for state in plan if state["state_fips"] == "06")["jobs"][-1]["district_count"] == 120
    vermont = next(state for state in plan if state["state_fips"] == "50")
    assert vermont["jobs"][0]["house_sizes"] == [435, 574, 692]


@pytest.mark.parametrize("states,caps", [(["20", "20"], [435]), (["11"], [435]), (["20"], [11037]), (["20"], [435, 435]), ([], [435])])
def test_invalid_queue_scope_rejected(states: list[str], caps: list[int]) -> None:
    with pytest.raises(ValueError):
        make_plan(states, caps)


def test_cleanup_preserves_archive_and_other_states(tmp_path: Path) -> None:
    state = tmp_path / "10"
    target = state / "tl_2020_10_tabblock20"
    target.mkdir(parents=True)
    (target / "sample.shp").write_bytes(b"1234")
    archive = state / "tl_2020_10_tabblock20.zip"
    archive.write_bytes(b"retained")
    unrelated = tmp_path / "20"
    unrelated.mkdir()
    assert clean_extracted_source("10", tmp_path) == 4
    assert not target.exists()
    assert archive.read_bytes() == b"retained"
    assert unrelated.exists()


def test_cleanup_requires_archive_and_flat_known_generated_directory(tmp_path: Path) -> None:
    target = tmp_path / "10/tl_2020_10_tabblock20"
    target.mkdir(parents=True)
    (target / "sample.shp").write_bytes(b"source")
    with pytest.raises(ValueError, match="retained archive"):
        clean_extracted_source("10", tmp_path)
    assert target.exists()
    (target.parent / "tl_2020_10_tabblock20.zip").write_bytes(b"archive")
    (target / "unexpected").mkdir()
    with pytest.raises(ValueError, match="unexpected nested"):
        clean_extracted_source("10", tmp_path)
    assert target.exists()


def test_failed_child_does_not_propagate_prior_unsupported_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = make_plan(["10"], [435, 1000])
    calls = []

    class FailedProcess:
        pid = 123

        def __init__(self, command: list[str], **kwargs: Any) -> None:
            calls.append(command)
            self.stdout = io.StringIO("")
            output = Path(command[command.index("--output") + 1])
            output.mkdir(parents=True, exist_ok=True)
            (output / "benchmark.json").write_text(json.dumps({"status": "unsupported_topology"}))

        def wait(self) -> int:
            return 1

    monkeypatch.setattr(suite.subprocess, "Popen", FailedProcess)
    runner = suite.QueueRunner(tmp_path, plan, caps=[435, 1000], workers=1, min_free_gib=0, keep_extracted=True)
    runner.run_state(plan[0])
    assert len(calls) == len(plan[0]["jobs"])
    assert all(job["status"] == "failed" for job in plan[0]["jobs"])
    assert all("topology_report" not in job for job in plan[0]["jobs"])


def test_cleanup_never_removes_source_owned_by_another_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "10/tl_2020_10_tabblock20"
    target.mkdir(parents=True)
    original = target / "sample.shp"
    original.write_bytes(b"active source")
    (target.parent / "tl_2020_10_tabblock20.zip").write_bytes(b"archive")

    @contextmanager
    def busy(state_fips: str) -> Iterator[None]:
        raise suite.StateExecutionLockedError("active state")
        yield

    monkeypatch.setattr(suite, "state_execution_lock", busy)
    with pytest.raises(suite.StateExecutionLockedError):
        clean_extracted_source("10", tmp_path)
    assert original.read_bytes() == b"active source"
