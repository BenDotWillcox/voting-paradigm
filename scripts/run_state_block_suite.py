"""Run the remaining states' four block-resolution anchors as a resumable queue.

Each state owns a serial series of unique district counts. A small number of
states may run concurrently; reported wall times explicitly include that load.
Kansas's existing measurements remain separate and are never overwritten.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import html
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apportionment import apportion_us_2020
from scripts.precompute_state_districts import STATE_NAMES
from scripts.state_block_execution_lock import StateExecutionLockedError, state_execution_lock

HOUSE_SIZES = (435, 574, 692, 1000)
TERMINAL_EXCEPTIONS = {"unsupported_topology", "unsupported_antimeridian_topology"}


def make_plan(states: list[str], caps: list[int]) -> list[dict[str, Any]]:
    if not states or len(states) != len(set(states)) or any(state not in STATE_NAMES for state in states):
        raise ValueError("Choose unique two-digit FIPS codes from the 50 states.")
    if not caps or len(caps) != len(set(caps)) or any(cap not in HOUSE_SIZES for cap in caps):
        raise ValueError("This suite supports unique House anchors 435, 574, 692, and 1000 only.")
    apportioned = {cap: apportion_us_2020(cap) for cap in caps}
    plan = []
    for fips in states:
        by_count: dict[int, list[int]] = {}
        for cap in caps:
            by_count.setdefault(apportioned[cap][fips], []).append(cap)
        plan.append({
            "state_fips": fips, "state": STATE_NAMES[fips], "status": "queued",
            "jobs": [{
                "district_count": count, "house_sizes": matching_caps,
                "relative_output": f"states/{fips}/districts-{count}", "status": "queued",
            } for count, matching_caps in sorted(by_count.items())],
        })
    return plan


def write_json(path: Path, data: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def clean_extracted_source(fips: str, source_root: Path) -> int:
    """Remove only the regenerated state extraction, preserving its ZIP archive."""
    # A surviving child or a different queue can use this shared state source.
    # Hold the same child-owned state lock throughout inspection and deletion.
    with state_execution_lock(fips):
        return _clean_extracted_source_locked(fips, source_root)


def _clean_extracted_source_locked(fips: str, source_root: Path) -> int:
    state_dir = (source_root / fips).resolve()
    candidate = state_dir / f"tl_2020_{fips}_tabblock20"
    target = candidate.resolve()
    archive = state_dir / f"tl_2020_{fips}_tabblock20.zip"
    if (fips not in STATE_NAMES or candidate.is_symlink() or target != candidate
            or target.parent != state_dir or not state_dir.is_relative_to(source_root.resolve())):
        raise ValueError("Extraction cleanup target escaped the source root.")
    if not target.exists():
        return 0
    if target.is_symlink() or not target.is_dir() or not archive.is_file():
        raise ValueError("Refusing extraction cleanup without a retained archive.")
    if any(item.is_symlink() or item.is_dir() for item in target.iterdir()):
        raise ValueError("Refusing unexpected nested entries in the generated extraction.")
    size = sum(item.stat().st_size for item in target.iterdir())
    shutil.rmtree(target)
    return size


def generate_viewer(run_dir: Path, report: dict[str, Any], state: dict[str, Any]) -> None:
    template_path = ROOT / "scripts/assets/state-block-viewer.html"
    if not template_path.exists() or not report.get("maps"):
        return
    template = template_path.read_text(encoding="utf-8")
    navigation = '<a href="../../../">All states</a> '
    for job in state["jobs"]:
        for cap in job["house_sizes"]:
            current = ' aria-current="page"' if job["district_count"] == report["district_count"] else ""
            if job["status"] == "complete":
                navigation += f'<a href="../districts-{job["district_count"]}/"{current}>{cap:,}</a> '
            else:
                navigation += f'<span class="muted">{cap:,} · {html.escape(job["status"].replace("_", " "))}</span> '
    deviation = report["final_plan"]["max_absolute_deviation_people"]
    projection = report["input"]["projection"]
    replacements = {
        "__STATE_NAME__": html.escape(state["state"]),
        "__DISTRICT_COUNT__": str(report["district_count"]),
        "__RESULT_SUMMARY__": f'{report["district_count"]} shared-edge-connected districts · worst population deviation {deviation:.3f} people.',
        "__ANCHOR_NAVIGATION__": navigation,
        "__LON0__": str(projection["lon0"]), "__LAT0__": str(projection["lat0"]),
    }
    for needle, value in replacements.items():
        template = template.replace(needle, value)
    map_directory = Path(report["artifacts"]["map_manifest"]).parent.as_posix()
    template = template.replace("maps/", f"{map_directory}/")
    (run_dir / "index.html").write_text(template, encoding="utf-8")


class QueueRunner:
    def __init__(self, output: Path, plan: list[dict[str, Any]], *, caps: list[int], workers: int,
                 min_free_gib: float, keep_extracted: bool) -> None:
        self.output = output.resolve()
        self.source_root = ROOT / ".cache/state-block-benchmark/source"
        self.workers = workers
        self.min_free = int(min_free_gib * 2**30)
        self.keep_extracted = keep_extracted
        self.lock = threading.Lock()
        self.started = time.perf_counter()
        self.suite: dict[str, Any] = {
            "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
            "house_sizes": caps, "state_count": len(plan),
            "distinct_plan_count": sum(len(state["jobs"]) for state in plan),
            "workers": workers, "states": plan,
            "orchestrator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "measurement_policy": "Fresh process per unique state/district count; up to two states concurrently. Wall times reflect concurrent desktop load, not isolated Kansas-comparable timings.",
            "connectivity_policy": "Strict shared-edge; exceptions are recorded, never connected with invented edges.",
            "storage_policy": "Retain source archives, validated graph caches, checkpoints, reports, and gzip map bodies; remove regenerated extraction after each state.",
        }

    def save(self) -> None:
        with self.lock:
            self.suite["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.suite["elapsed_wall_seconds"] = time.perf_counter() - self.started
            self.suite["free_disk_bytes"] = shutil.disk_usage(self.output).free
            jobs = [job for state in self.suite["states"] for job in state["jobs"]]
            self.suite["counts"] = {status: sum(job["status"] == status for job in jobs)
                                    for status in sorted({job["status"] for job in jobs})}
            write_json(self.output / "suite.json", self.suite)

    def update(self, record: dict[str, Any], **values: Any) -> None:
        with self.lock:
            record.update(values)

    def run_state(self, state: dict[str, Any]) -> None:
        fips = state["state_fips"]
        self.update(state, status="running")
        self.save()
        topology_report: str | None = None
        topology_status = "unsupported_topology"
        for job in state["jobs"]:
            if (self.output / "STOP").exists():
                self.update(job, status="not_started_stop_requested")
                continue
            if topology_report:
                self.update(job, status=topology_status, topology_report=topology_report)
                self.save()
                continue
            if shutil.disk_usage(self.output).free < self.min_free:
                self.update(job, status="not_started_low_disk", error="Available storage is below the configured reserve.")
                self.save()
                continue
            run_dir = self.output / job["relative_output"]
            run_dir.parent.mkdir(parents=True, exist_ok=True)
            log_path = run_dir.parent / f"districts-{job['district_count']}.log"
            command = [
                sys.executable, "-u", str(ROOT / "scripts/benchmark_state_blocks.py"),
                "--state-fips", fips, "--district-count", str(job["district_count"]),
                "--house-sizes", *(str(cap) for cap in self.suite["house_sizes"]),
                "--output", str(run_dir), "--resume",
            ]
            self.update(job, status="running", started_at=datetime.now(timezone.utc).isoformat(),
                       log=log_path.relative_to(self.output).as_posix())
            self.save()
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"\nQueue invocation {job['started_at']}\n")
                process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, encoding="utf-8", errors="replace", bufsize=1)
                self.update(job, pid=process.pid)
                assert process.stdout is not None
                last_save = 0.0
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    self.update(job, latest_progress=line.strip())
                    print(f"[{fips}/{job['district_count']}] {line}", end="", flush=True)
                    if time.monotonic() - last_save > 10:
                        self.save()
                        last_save = time.monotonic()
                return_code = process.wait()
            self.update(job, process_exit_code=return_code, finished_at=datetime.now(timezone.utc).isoformat())
            report_path = run_dir / "benchmark.json"
            if return_code:
                # A lock/provenance refusal can happen before the child writes
                # a report. Never propagate a prior attempt's terminal status.
                self.update(job, status="failed", error=f"Benchmark child exited with status {return_code}; inspect its log.")
                if report_path.exists():
                    self.update(job, report=report_path.relative_to(self.output).as_posix())
            elif report_path.exists():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                self.update(job, status=report["status"], report=report_path.relative_to(self.output).as_posix())
                for key in ("error", "failed_phase", "timed_pipeline_wall_seconds", "peak_process_working_set_bytes",
                            "final_plan", "solver", "graph_cache", "topology", "source_components", "unsupported_reason", "repair_move_count",
                            "rebalance_move_count", "stop_reason"):
                    if key in report:
                        self.update(job, **{key: report[key]})
                if report["status"] == "complete" and return_code == 0:
                    generate_viewer(run_dir, report, state)
                    self.update(job, viewer=f"{job['relative_output']}/")
                elif report["status"] in TERMINAL_EXCEPTIONS:
                    topology_report = job["report"]
                    topology_status = report["status"]
            else:
                self.update(job, status="failed", error="Child produced no benchmark report.")
            self.save()
            for saved_job in state["jobs"]:
                if saved_job["status"] == "complete" and saved_job.get("report"):
                    saved_report = json.loads((self.output / saved_job["report"]).read_text(encoding="utf-8"))
                    generate_viewer(self.output / saved_job["relative_output"], saved_report, state)
        statuses = {job["status"] for job in state["jobs"]}
        self.update(state, status="complete" if statuses == {"complete"} else (
            "unsupported_topology" if statuses <= TERMINAL_EXCEPTIONS else "finished_with_exceptions"))
        if not self.keep_extracted:
            try:
                removed = clean_extracted_source(fips, self.source_root)
            except StateExecutionLockedError:
                self.update(state, extraction_cleanup_status="deferred_state_busy",
                            extraction_cleanup_note="Source extraction retained because another process owns this state.")
            else:
                self.update(state, regenerable_extraction_bytes_removed=removed,
                            extraction_cleanup_status="complete")
        self.save()

    def run(self) -> None:
        self.output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "scripts/assets/state-block-progress.html", self.output / "index.html")
        self.save()
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self.run_state, state): state for state in self.suite["states"]}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as error:
                    state = futures[future]
                    self.update(state, status="failed", error=f"{type(error).__name__}: {error}")
                    for job in state["jobs"]:
                        if job["status"] in {"queued", "running"}:
                            self.update(job, status="failed", error="State worker failed; inspect the state error.")
                    self.save()
        statuses = {job["status"] for state in self.suite["states"] for job in state["jobs"]}
        self.suite["status"] = "complete" if statuses == {"complete"} else "finished_with_exceptions"
        self.suite["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/state-block-benchmark/suite-through-1000")
    parser.add_argument("--states", nargs="+", choices=sorted(STATE_NAMES))
    parser.add_argument("--house-sizes", type=int, nargs="+", choices=HOUSE_SIZES, default=list(HOUSE_SIZES))
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--min-free-gib", type=float, default=5)
    parser.add_argument("--keep-extracted", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if args.min_free_gib < 0:
        parser.error("Disk reserve cannot be negative.")
    states = args.states or [fips for fips in STATE_NAMES if fips != "20"]
    plan = make_plan(states, args.house_sizes)
    # Smaller allocations finish first, providing early geographic coverage.
    plan.sort(key=lambda state: (max(job["district_count"] for job in state["jobs"]), state["state"]))
    if args.plan_only:
        print(json.dumps(plan, indent=2))
        return
    args.output.mkdir(parents=True, exist_ok=True)
    # The OS releases the advisory lock after a crash, so stale files do not
    # prevent resuming. One process owns the queue manifest at a time.
    import msvcrt
    with (args.output / "queue.lock").open("a+b") as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            parser.error("Another process owns this queue output directory.")
        QueueRunner(args.output, plan, caps=args.house_sizes, workers=args.workers,
                    min_free_gib=args.min_free_gib, keep_extracted=args.keep_extracted).run()


if __name__ == "__main__":
    main()
