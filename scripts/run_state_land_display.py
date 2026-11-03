"""Own one serial all-state display build; never rerun a district solver.

Each child owns one state and may reuse exactly pinned complete pilot fragments.
A failed or ambiguous child stops the queue. Existing ownership refuses another
launch, including after failure; investigation must precede any recovery.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.build_block_plan_bundle import CATALOG, OUTPUT, digest, encoded, safe_path
from scripts.build_state_land_display import NAMESPACE, runtime_hashes
from scripts.publish_state_explorer import file_hash, validate_anchors


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(path: Path, value: dict) -> None:
    """Short reader collisions on Windows must not abandon a running child."""
    temporary = path.with_suffix(".tmp")
    raw = encoded(value)
    for attempt in range(12):
        try:
            temporary.write_bytes(raw)
            temporary.replace(path)
            return
        except PermissionError:
            time.sleep(min(.1 * (attempt + 1), 1))
    raise RuntimeError(f"Could not persist ownership record: {path}")


def run(root: Path, cache: Path) -> dict:
    root, cache = root.resolve(), cache.resolve()
    directory = safe_path(root, NAMESPACE)
    directory.mkdir(parents=True, exist_ok=True)
    run_path = directory / "all-states.run.json"
    # Exclusive creation: a second launcher never owns the same state queue.
    with run_path.open("x", encoding="utf-8") as stream:
        json.dump({"status": "initializing", "pid": os.getpid(), "startedAt": now()}, stream)
    record = {"schemaVersion": 1, "status": "initializing", "pid": os.getpid(), "startedAt": now(),
              "root": str(root), "cacheRoot": str(cache), "jobs": [], "solverRuns": 0}
    active = None
    try:
        manifest_path = safe_path(root, OUTPUT / "manifest.json")
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw)
        index_path = safe_path(root, OUTPUT / "server-index.json")
        pins = {str(OUTPUT / "manifest.json"): digest(manifest_raw),
                str(OUTPUT / "server-index.json"): file_hash(index_path), str(CATALOG): file_hash(safe_path(root, CATALOG))}
        states = [state for state in validate_anchors(manifest) if state != "26"]
        # Small policy states and Alaska first; large states later. No parallel
        # children compete for source geometry RAM or Windows output files.
        priority = ["44", "15", "02", "36", "21", "12", "06"]
        states.sort(key=lambda state: (priority.index(state) if state in priority else len(priority), state))
        hashes = runtime_hashes()
        record.update({"status": "running", "runtimeHashes": hashes, "preservedFiles": pins,
                       "jobs": [{"stateFips": state, "status": "pending"} for state in states]})
        save(run_path, record)
        for job in record["jobs"]:
            if runtime_hashes() != hashes:
                raise ValueError("Frozen display runtime changed")
            for relative, sha in pins.items():
                if file_hash(safe_path(root, relative)) != sha:
                    raise ValueError(f"Preserved app metadata changed: {relative}")
            state = job["stateFips"]
            log_path = directory / f"state-{state}.log"
            command = [sys.executable, "-X", "utf8", str(ROOT / "scripts/build_state_land_display.py"),
                       "--bundle-root", str(root), "--cache-root", str(cache), "--state", state]
            job.update({"status": "starting", "command": command, "log": str(log_path), "startedAt": now()})
            record["activeState"] = state
            save(run_path, record)
            started = time.perf_counter()
            with log_path.open("x", encoding="utf-8") as log:
                active = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                job.update({"status": "running", "pid": active.pid})
                try:
                    save(run_path, record)
                except Exception:
                    emergency = directory / f"emergency-{state}-{active.pid}.json"
                    emergency.write_bytes(encoded({"pid": active.pid, "command": command, "status": "child-may-be-active", "createdAt": now()}))
                    raise
                exit_code = active.wait()
            active = None
            job.update({"exitCode": exit_code, "finishedAt": now(), "runtimeSeconds": time.perf_counter() - started})
            report_path = directory / "states" / f"{state}.json"
            if exit_code != 0:
                job["status"] = "failed"
                raise RuntimeError(f"State {state} child exited {exit_code}; inspect {log_path}")
            raw = report_path.read_bytes()
            report = json.loads(raw)
            expected = {key for key, p in manifest["plans"].items() if p["stateFips"] == state}
            if (report.get("status") != "complete" or set(report["landDisplays"]) != expected
                    or set(report["geometryPlans"]) != expected or report["audit"]["runtimeHashes"] != hashes
                    or report["baseManifestSha256"] != pins[str(OUTPUT / "manifest.json")]
                    or report["baseIndexSha256"] != pins[str(OUTPUT / "server-index.json")]):
                job["status"] = "ambiguous"
                raise ValueError(f"State {state} terminal report does not match ownership")
            job.update({"status": "complete", "reportPath": str(report_path), "reportSha256": digest(raw), "plans": len(expected)})
            save(run_path, record)
            print(f"Completed state {state}: {len(expected)} plans, {job['runtimeSeconds']:.1f}s", flush=True)
        record.update({"status": "complete", "activeState": None, "finishedAt": now()})
        save(run_path, record)
        return record
    except BaseException as error:
        record.update({"status": "blocked", "error": str(error), "traceback": traceback.format_exc(), "finishedAt": now(),
                       "activeChildMayBeRunning": active is not None and active.poll() is None})
        try:
            save(run_path, record)
        except Exception:
            (directory / f"emergency-parent-{os.getpid()}.json").write_bytes(encoded(record))
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.bundle_root, args.cache_root)
    print(json.dumps({"status": result["status"], "states": len(result["jobs"])}))


if __name__ == "__main__":
    main()
