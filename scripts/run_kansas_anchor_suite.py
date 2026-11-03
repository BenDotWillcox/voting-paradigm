"""Prepare one source-keyed graph cache, then benchmark Kansas anchors serially.

Every cap runs in a fresh Python process for independent OS peak-memory readings.
The initial graph cache preparation is measured separately from the warm runs.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

from benchmark_kansas_blocks import ROOT, Measurements, load_units, prepare_source, process_memory
from district_block_graph_cache import load_or_build_shared_edge_graph


def prepare_graph(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    measurement = Measurements()
    start = time.perf_counter()
    report = {"status": "running"}
    try:
        source, source_metadata = prepare_source(ROOT / ".cache/kansas-block-benchmark/source", measurement)
        report["source"] = source_metadata
        with measurement.phase("load_block_identifiers"):
            units, _, input_metadata = load_units(source)
            geoids = [unit.geoid for unit in units]
            del units
        report["input"] = input_metadata
        with measurement.phase("prepare_shared_edge_graph_cache"):
            adjacency, graph, cache = load_or_build_shared_edge_graph(
                source, geoids, source_sha256=source_metadata["archive_sha256"],
                cache_dir=ROOT / ".cache/kansas-block-benchmark/graph-cache",
            )
        report["graph"] = graph
        report["cache"] = cache
        report["loaded_graph_nodes"] = len(adjacency)
        report["status"] = "complete"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["phases"] = measurement.phases
        report["timed_wall_seconds"] = time.perf_counter() - start
        report["peak_process_working_set_bytes"] = process_memory()[1]
        measurement.close()
        (output / "cache-preparation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def run_logged(command: list[str], log_path: Path) -> int:
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            log.flush()
            print(line, end="", flush=True)
        return process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/kansas-block-benchmark/anchor-suite")
    parser.add_argument("--house-sizes", type=int, nargs="+", default=[435, 574, 692, 1000, 11037])
    parser.add_argument("--prepare-cache-only", action="store_true")
    args = parser.parse_args()
    if len(set(args.house_sizes)) != len(args.house_sizes):
        parser.error("House sizes must be unique.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.prepare_cache_only:
        prepare_graph(output)
        return
    if any((output / f"house-{cap}" / "benchmark.json").exists() for cap in args.house_sizes):
        parser.error("A selected cap already has a report in this output directory; choose a new --output.")
    start = time.perf_counter()
    suite = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running", "house_sizes": args.house_sizes, "runs": [],
        "measurement_policy": "sequential fresh processes; shared-edge cache prepared separately",
    }
    exit_code = run_logged(
        [sys.executable, str(Path(__file__).resolve()), "--output", str(output), "--prepare-cache-only"],
        output / "cache-preparation.log",
    )
    if exit_code:
        raise SystemExit(exit_code)
    suite["cache_preparation"] = json.loads((output / "cache-preparation.json").read_text(encoding="utf-8"))
    for cap in args.house_sizes:
        run_dir = output / f"house-{cap}"
        print(f"\nBenchmarking House size {cap:,}", flush=True)
        exit_code = run_logged(
            [sys.executable, str(ROOT / "scripts/benchmark_kansas_anchors.py"),
             "--house-size", str(cap), "--output", str(run_dir)],
            output / f"house-{cap}.log",
        )
        report_path = run_dir / "benchmark.json"
        result = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {
            "status": "failed", "house_size": cap, "error": "No benchmark report produced",
        }
        result["process_exit_code"] = exit_code
        suite["runs"].append(result)
        suite["elapsed_wall_seconds"] = time.perf_counter() - start
        (output / "suite.json").write_text(json.dumps(suite, indent=2), encoding="utf-8")
    suite["status"] = "complete" if all(
        run["status"] == "complete" and run["process_exit_code"] == 0
        for run in suite["runs"]
    ) else "completed_with_failures"
    suite["finished_at"] = datetime.now(timezone.utc).isoformat()
    suite["elapsed_wall_seconds"] = time.perf_counter() - start
    (output / "suite.json").write_text(json.dumps(suite, indent=2), encoding="utf-8")
    print(f"Suite report: {output / 'suite.json'}", flush=True)
    if suite["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
