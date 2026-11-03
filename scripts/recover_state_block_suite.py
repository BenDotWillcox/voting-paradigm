"""One bounded operational recovery for the completed national block suite.

Numerical/source modules remain frozen. Children write directly to files; the
orchestrator never polls an active benchmark report. Original terminal suite
bytes and records remain available alongside separate recovery history.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.benchmark_state_blocks import CODE_PATHS
from scripts.run_state_block_suite import HOUSE_SIZES, TERMINAL_EXCEPTIONS, generate_viewer
from scripts.state_block_execution_lock import state_execution_lock


RECOVERY_ID = "operational-recovery-2026-10-23-v1"
JOBS = (
    ("49", 10, "single_operational_retry"),
    ("34", 16, "validate_completed_result"),
    ("34", 19, "first_benchmark_attempt"),
    ("34", 28, "first_benchmark_attempt"),
    ("48", 51, "single_operational_retry"),
    ("48", 61, "first_benchmark_attempt"),
    ("48", 88, "first_benchmark_attempt"),
)
PRESERVED_TIMINGS = ("started_at", "finished_at", "elapsed_wall_seconds")
REPORT_FIELDS = (
    "final_plan", "solver", "graph_cache", "source_components", "unsupported_reason",
    "repair_move_count", "rebalance_move_count", "stop_reason", "peak_process_working_set_bytes",
)


class RecoveryAdmissionError(RuntimeError):
    """The original queue, frozen code, or one-attempt condition is unsuitable."""


class MetadataWriteError(OSError):
    """Bounded atomic metadata replacement failed; child ownership is retained."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any, *, attempts: int = 8) -> None:
    """Retry only transient sharing/permission errors, never indefinitely."""
    if attempts < 1:
        raise ValueError("Metadata write attempts must be positive.")
    data = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.partial")
    for attempt in range(attempts):
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
            return
        except OSError as error:
            transient = isinstance(error, PermissionError) or error.errno in (errno.EACCES, errno.EPERM) or getattr(error, "winerror", None) in (5, 32, 33)
            if not transient:
                raise
            if attempt + 1 == attempts:
                raise MetadataWriteError(f"Atomic metadata write failed after {attempts} attempts: {path}") from error
            time.sleep(min(0.05 * 2**attempt, 0.5))


@contextmanager
def queue_ownership(suite_dir: Path) -> Iterator[None]:
    """Use the original queue's exact OS lock, including for another recovery."""
    with (suite_dir / "queue.lock").open("a+b") as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if sys.platform == "win32":
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RecoveryAdmissionError("The main queue or another recovery still owns queue.lock.") from error
        try:
            yield
        finally:
            stream.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def find_job(suite: dict[str, Any], fips: str, count: int) -> tuple[dict[str, Any], dict[str, Any]]:
    states = [state for state in suite["states"] if state["state_fips"] == fips]
    jobs = [job for state in states for job in state["jobs"] if job["district_count"] == count]
    if len(states) != 1 or len(jobs) != 1:
        raise RecoveryAdmissionError(f"Expected one original record for {fips}/{count}.")
    return states[0], jobs[0]


def verify_frozen_code(suite: dict[str, Any], suite_dir: Path) -> dict[str, Any]:
    baseline_path: Path | None = None
    baseline: dict[str, str] | None = None
    for state in suite["states"]:
        for job in state["jobs"]:
            if job["status"] == "complete" and job.get("report"):
                candidate = (suite_dir / job["report"]).resolve()
                if not candidate.is_relative_to(suite_dir) or not candidate.is_file():
                    raise RecoveryAdmissionError("A saved complete report is missing or outside the suite.")
                saved = json.loads(candidate.read_text(encoding="utf-8"))
                if saved.get("status") == "complete" and set(saved.get("code_sha256", {})) == set(CODE_PATHS):
                    baseline_path, baseline = candidate, saved["code_sha256"]
                    break
        if baseline is not None:
            break
    if baseline is None or baseline_path is None:
        raise RecoveryAdmissionError("No completed report provides the frozen CODE_PATHS baseline.")
    current = {path: file_hash(ROOT / path) for path in CODE_PATHS}
    if current != baseline:
        changed = [path for path in CODE_PATHS if current[path] != baseline[path]]
        raise RecoveryAdmissionError(f"Frozen benchmark code differs from its recorded baseline: {changed}")
    for fips, count, _ in JOBS:
        _, job = find_job(suite, fips, count)
        report_path = suite_dir / job["relative_output"] / "benchmark.json"
        if report_path.exists():
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            if saved.get("code_sha256") != baseline:
                raise RecoveryAdmissionError(f"Saved code provenance differs for {fips}/{count}.")
    return {"report": baseline_path.relative_to(suite_dir).as_posix(), "code_sha256": baseline}


def refresh_counts(suite: dict[str, Any], *, active: bool) -> None:
    all_jobs = [job for state in suite["states"] for job in state["jobs"]]
    suite["counts"] = dict(sorted(Counter(job["status"] for job in all_jobs).items()))
    for state in suite["states"]:
        statuses = {job["status"] for job in state["jobs"]}
        if statuses & {"running", "queued_recovery"}:
            state["status"] = "recovering"
        elif statuses == {"complete"}:
            state["status"] = "complete"
        elif statuses <= TERMINAL_EXCEPTIONS:
            state["status"] = "unsupported_topology"
        elif any((state["state_fips"], job["district_count"]) in {(fips, count) for fips, count, _ in JOBS} for job in state["jobs"]):
            state["status"] = "finished_with_exceptions"
    suite["status"] = "recovering" if active else ("complete" if suite["counts"] == {"complete": len(all_jobs)} else "finished_with_exceptions")


def prepare_live_suite(original: dict[str, Any], recovery_reference: str, started_at: str) -> dict[str, Any]:
    """Record originals before exposing queued/running recovery work in the UI."""
    suite = deepcopy(original)
    target_states = {fips for fips, _, _ in JOBS}
    for state in suite["states"]:
        if state["state_fips"] in target_states:
            original_state = deepcopy(state)
            state.setdefault("recovery_history", []).append({
                "recovery_id": RECOVERY_ID, "original_state": original_state,
            })
            state.pop("error", None)
    for fips, count, kind in JOBS:
        _, job = find_job(suite, fips, count)
        original_job = deepcopy(job)
        job.setdefault("recovery_history", []).append({
            "recovery_id": RECOVERY_ID, "original_job": original_job, "kind": kind,
        })
        if kind != "validate_completed_result":
            job["status"] = "queued_recovery"
        job["recovery_reference"] = recovery_reference
        job.pop("error", None)
    suite["active_recovery"] = recovery_reference
    suite["recovery_started_at"] = started_at
    refresh_counts(suite, active=True)
    return suite


def merge_attempt(suite: dict[str, Any], attempt: dict[str, Any], report: dict[str, Any] | None) -> None:
    """Update current results while retaining original timestamps and records."""
    _, job = find_job(suite, attempt["state_fips"], attempt["district_count"])
    job["recovery_attempt"] = deepcopy(attempt)
    job["process_exit_code"] = attempt.get("process_exit_code")
    if attempt.get("process_exit_code") != 0:
        job["status"] = "failed"
        job["error"] = attempt.get("error", "Recovery child did not exit successfully; inspect its direct log.")
    elif report is None:
        job["status"] = "failed"
        job["error"] = "Recovery child produced no benchmark report."
    else:
        job["status"] = report["status"]
        job["report"] = f"{job['relative_output']}/benchmark.json"
        for key in REPORT_FIELDS:
            if key in report:
                job[key] = deepcopy(report[key])
        job["recovery_pipeline_wall_seconds"] = attempt.get("wall_seconds")
        job["benchmark_result_reused"] = attempt.get("benchmark_result_reused", False)
        if "timed_pipeline_wall_seconds" in report:
            job["timed_pipeline_wall_seconds"] = report["timed_pipeline_wall_seconds"]
        if report["status"] == "complete":
            job.pop("error", None)
            job.pop("failed_phase", None)
        else:
            for key in ("error", "failed_phase"):
                if key in report:
                    job[key] = report[key]
    history = job["recovery_history"][-1]
    history["attempt"] = deepcopy(attempt)
    history["result_status"] = job["status"]
    job["latest_progress"] = f"Recovery child exited {attempt.get('process_exit_code')}; result {job['status']}. See its direct recovery log."


class RecoveryRunner:
    def __init__(self, suite_dir: Path, *, min_free_gib: float = 8) -> None:
        self.suite_dir = suite_dir.resolve()
        self.directory = self.suite_dir / "recoveries" / RECOVERY_ID
        self.min_free = int(min_free_gib * 2**30)
        self.started = time.perf_counter()
        self.manifest: dict[str, Any] = {}
        self.suite: dict[str, Any] = {}
        self.original: dict[str, Any] = {}

    def initialize(self) -> None:
        if self.directory.exists():
            raise RecoveryAdmissionError("This fixed recovery attempt already exists. It is never automatically relaunched.")
        original_bytes = (self.suite_dir / "suite.json").read_bytes()
        self.original = json.loads(original_bytes)
        if self.original.get("status") not in ("complete", "finished_with_exceptions") or not self.original.get("finished_at"):
            raise RecoveryAdmissionError("The main suite has not reached a recorded terminal state.")
        if tuple(self.original.get("house_sizes", ())) != HOUSE_SIZES:
            raise RecoveryAdmissionError("The original House-size anchors differ from the fixed recovery scope.")
        # Probe every state to refuse a surviving child whose queue parent died.
        # Release before dispatch: each child owns its own state lock.
        with ExitStack() as stack:
            for state in self.original["states"]:
                stack.enter_context(state_execution_lock(state["state_fips"]))
            frozen = verify_frozen_code(self.original, self.suite_dir)
            for fips, count, _ in JOBS:
                _, job = find_job(self.original, fips, count)
                expected = f"states/{fips}/districts-{count}"
                if job.get("relative_output") != expected or job["status"] != "failed":
                    raise RecoveryAdmissionError(f"Original {fips}/{count} no longer matches the authorized failed record.")
        self.directory.mkdir(parents=True)
        with (self.directory / "original-suite.json").open("xb") as stream:
            stream.write(original_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        started_at = utc_now()
        self.manifest = {
            "id": RECOVERY_ID, "status": "running", "pid": os.getpid(), "started_at": started_at,
            "original_suite": "original-suite.json", "original_suite_sha256": hashlib.sha256(original_bytes).hexdigest(),
            "frozen_baseline": frozen, "orchestrator_sha256": file_hash(Path(__file__)),
            "disk_reserve_bytes": self.min_free, "house_sizes": list(HOUSE_SIZES),
            "policy": "One fixed attempt per listed job; direct child log files; no active-report polling; no solver/source edits; geometry failures 24/19 and 51/26 excluded.",
            "jobs": [{"state_fips": fips, "district_count": count, "kind": kind, "status": "queued", "attempt_count": 0} for fips, count, kind in JOBS],
            "metadata_warnings": [],
        }
        reference = (self.directory / "recovery.json").relative_to(self.suite_dir).as_posix()
        self.suite = prepare_live_suite(self.original, reference, started_at)
        self.save()

    def save(self) -> None:
        self.manifest["updated_at"] = utc_now()
        self.manifest["elapsed_wall_seconds"] = time.perf_counter() - self.started
        self.manifest["counts"] = dict(sorted(Counter(job["status"] for job in self.manifest["jobs"]).items()))
        self.suite["recovery_updated_at"] = self.manifest["updated_at"]
        self.suite["updated_at"] = self.manifest["updated_at"]
        self.suite["free_disk_bytes"] = shutil.disk_usage(self.suite_dir).free
        self.suite["recovery_elapsed_wall_seconds"] = self.manifest["elapsed_wall_seconds"]
        # These original timing fields must remain byte-for-byte equal values.
        for field in PRESERVED_TIMINGS:
            if self.suite.get(field) != self.original.get(field):
                raise AssertionError(f"Recovery altered the original suite timing field {field}.")
        atomic_json(self.directory / "recovery.json", self.manifest)
        atomic_json(self.suite_dir / "suite.json", self.suite)

    def emergency_save(self, error: BaseException) -> None:
        self.manifest["fatal_error"] = f"{type(error).__name__}: {error}"
        # A new direct file avoids the rename that triggered Windows sharing
        # failures; it preserves PIDs/results if the normal manifest is blocked.
        path = self.directory / f"emergency-{time.time_ns()}.json"
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump({"recovery": self.manifest, "live_suite": self.suite}, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            pass
        print(f"Recovery stopped after retaining child ownership: {error}. Emergency record: {path}", file=sys.stderr, flush=True)

    def run_child(self, attempt: dict[str, Any]) -> None:
        fips, count = attempt["state_fips"], attempt["district_count"]
        _, job = find_job(self.suite, fips, count)
        # Any unrelated writer that appeared since admission must finish first.
        with state_execution_lock(fips):
            verify_frozen_code(self.original, self.suite_dir)
            existing_report = self.suite_dir / job["relative_output"] / "benchmark.json"
            if existing_report.is_file():
                attempt["original_report_sha256"] = file_hash(existing_report)
        run_dir = self.suite_dir / job["relative_output"]
        log_path = self.directory / f"state-{fips}-districts-{count}.log"
        command = [sys.executable, "-u", str(ROOT / "scripts/benchmark_state_blocks.py"),
                   "--state-fips", fips, "--district-count", str(count),
                   "--house-sizes", *(str(cap) for cap in HOUSE_SIZES),
                   "--output", str(run_dir), "--max-moves", "1000", "--resume"]
        attempt.update(status="running", attempt_count=1, started_at=utc_now(),
                       log=log_path.relative_to(self.suite_dir).as_posix(), command=command)
        job["status"] = "running"
        job["recovery_attempt"] = deepcopy(attempt)
        job["log"] = attempt["log"]
        job["latest_progress"] = "Recovery starting; stdout/stderr go directly to the recovery log."
        refresh_counts(self.suite, active=True)
        self.save()  # If this fails, no child has been launched.
        process: subprocess.Popen[bytes] | None = None
        deferred_error: BaseException | None = None
        child_started = time.perf_counter()
        with log_path.open("ab", buffering=0) as log:
            log.write(f"Recovery invocation {attempt['started_at']}\n".encode())
            try:
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                attempt["pid"] = process.pid
                job["pid"] = process.pid
                job["latest_progress"] = f"Recovery child {process.pid} is running; follow its direct log."
                job["recovery_attempt"] = deepcopy(attempt)
                log.write(f"Recovery child PID {process.pid}\n".encode())
                try:
                    self.save()
                except (OSError, RuntimeError) as error:
                    deferred_error = error
                    self.manifest["metadata_warnings"].append(f"PID metadata write deferred while child {process.pid} runs: {error}")
                while process.poll() is None:
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        if deferred_error is None:
                            try:
                                self.save()
                            except (OSError, RuntimeError) as error:
                                deferred_error = error
                                self.manifest["metadata_warnings"].append(f"Metadata write deferred until child exit: {error}")
            finally:
                # Exceptions in logging/metadata must never abandon the valid
                # process or break its stdout stream. Keep the direct file open.
                if process is not None:
                    while process.poll() is None:
                        try:
                            process.wait(timeout=15)
                        except (subprocess.TimeoutExpired, KeyboardInterrupt):
                            continue
                    attempt["process_exit_code"] = process.returncode
                    attempt["finished_at"] = utc_now()
                    attempt["wall_seconds"] = time.perf_counter() - child_started
                    log.write(f"\nRecovery child exit {process.returncode} at {attempt['finished_at']}\n".encode())
        report: dict[str, Any] | None = None
        with state_execution_lock(fips):
            report_path = run_dir / "benchmark.json"
            if report_path.is_file():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                attempt["report"] = report_path.relative_to(self.suite_dir).as_posix()
                attempt["report_sha256"] = file_hash(report_path)
                attempt["reported_status_after_exit"] = report.get("status")
            code = attempt.get("process_exit_code")
            attempt["benchmark_result_reused"] = bool(code == 0 and report is not None and report.get("status") == "complete" and attempt.get("original_report_sha256") == attempt.get("report_sha256"))
            attempt["status"] = report["status"] if code == 0 and report is not None else "failed"
            if code != 0:
                attempt["error"] = f"Recovery child exited with status {code}; inspect its direct log."
            elif report is None:
                attempt["error"] = "Recovery child exited without a benchmark report."
            merge_attempt(self.suite, attempt, report)
            state, _ = find_job(self.suite, fips, count)
            # Read completed reports only with the state lock held after exit.
            for completed in state["jobs"]:
                if completed["status"] == "complete" and completed.get("report"):
                    saved = json.loads((self.suite_dir / completed["report"]).read_text(encoding="utf-8"))
                    generate_viewer(self.suite_dir / completed["relative_output"], saved, state)
                    completed["viewer"] = f"{completed['relative_output']}/"
        refresh_counts(self.suite, active=True)
        self.save()  # Retry after child completion; persistent errors abort safely.
        if deferred_error is not None:
            self.manifest["metadata_warnings"].append("The deferred metadata write succeeded after child exit; its result was retained.")

    def run(self) -> None:
        try:
            self.initialize()
            for attempt in self.manifest["jobs"]:
                if shutil.disk_usage(self.suite_dir).free < self.min_free or (self.suite_dir / "STOP").exists():
                    reason = "not_started_low_disk" if shutil.disk_usage(self.suite_dir).free < self.min_free else "not_started_stop_requested"
                    for pending in self.manifest["jobs"]:
                        if pending["status"] == "queued":
                            pending["status"] = reason
                            _, job = find_job(self.suite, pending["state_fips"], pending["district_count"])
                            job["status"] = reason
                    break
                self.run_child(attempt)
            self.manifest["status"] = "complete" if all(job["status"] == "complete" for job in self.manifest["jobs"]) else "finished_with_exceptions"
            self.manifest["finished_at"] = utc_now()
            self.suite["recovery_finished_at"] = self.manifest["finished_at"]
            refresh_counts(self.suite, active=False)
            self.save()
        except BaseException as error:
            if self.manifest:
                self.manifest["status"] = "aborted"
                self.manifest["finished_at"] = utc_now()
                self.emergency_save(error)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/state-block-benchmark/suite-through-1000")
    parser.add_argument("--min-free-gib", type=float, default=8)
    args = parser.parse_args()
    if args.min_free_gib < 8:
        parser.error("Recovery requires at least an 8 GiB free-space reserve.")
    with queue_ownership(args.output.resolve()):
        RecoveryRunner(args.output, min_free_gib=args.min_free_gib).run()


if __name__ == "__main__":
    main()
