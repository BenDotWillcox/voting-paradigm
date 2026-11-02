"""Reproduce the Kansas 2020 block-resolution districting feasibility run.

Run with the repository venv. Large source/map files stay under .cache; the
application's tract artifacts and numerical solver are never modified.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import sys
import threading
import time
from typing import Any, Iterator
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import shapefile

from districting import Unit, balanced_power_diagram

SOURCE_URL = "https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_20_tabblock20.zip"
EXPECTED_BLOCKS = 172_529
EXPECTED_POPULATION = 2_937_880


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
        (name, ctypes.c_size_t)
        for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage",
        )
    ]


def process_memory() -> tuple[int, int]:
    """Current and OS high-water resident working set, in bytes (Windows)."""
    if os.name != "nt":
        raise RuntimeError("This measurement harness currently requires Windows.")
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    api = ctypes.WinDLL("psapi", use_last_error=True)
    api.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not api.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counters.WorkingSetSize, counters.PeakWorkingSetSize


class Measurements:
    def __init__(self) -> None:
        self.phases: dict[str, Any] = {}
        self.active = "startup"
        self.sampled_peak = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()

    def _sample(self) -> None:
        last_log = time.perf_counter()
        while not self.stop.wait(0.1):
            rss, _ = process_memory()
            self.sampled_peak = max(self.sampled_peak, rss)
            if time.perf_counter() - last_log >= 20:
                print(f"  {self.active}: resident memory {rss / 2**20:.1f} MiB", flush=True)
                last_log = time.perf_counter()

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        self.active = name
        self.sampled_peak = process_memory()[0]
        wall, cpu = time.perf_counter(), time.process_time()
        print(f"Starting {name}", flush=True)
        try:
            yield
        finally:
            self.phases[name] = {
                "wall_seconds": time.perf_counter() - wall,
                "cpu_seconds": time.process_time() - cpu,
                "sampled_peak_rss_bytes": max(self.sampled_peak, process_memory()[0]),
            }
            print(f"Finished {name}: {self.phases[name]}", flush=True)

    def close(self) -> None:
        self.stop.set()
        self.thread.join()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_source(cache: Path, measurement: Measurements) -> tuple[Path, dict[str, Any]]:
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / "tl_2020_20_tabblock20.zip"
    downloaded = not archive.exists()
    with measurement.phase("source_acquisition"):
        if downloaded:
            partial = archive.with_suffix(".zip.partial")
            with urllib.request.urlopen(SOURCE_URL, timeout=120) as response, partial.open("wb") as out:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    out.write(chunk)
            partial.replace(archive)
        source_hash = sha256(archive)
    target = cache / archive.stem
    with measurement.phase("source_extraction"):
        target.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.infolist():
                if not (target / member.filename).resolve().is_relative_to(target.resolve()):
                    raise ValueError("Unsafe path in source archive")
            zipped.extractall(target)
    return target / f"{archive.stem}.shp", {
        "url": SOURCE_URL, "archive_sha256": source_hash,
        "archive_bytes": archive.stat().st_size, "downloaded_in_timed_pipeline": downloaded,
        "extracted_bytes": sum(p.stat().st_size for p in target.iterdir() if p.is_file()),
        "crs_wkt": (target / f"{archive.stem}.prj").read_text(),
    }


def load_units(source: Path) -> tuple[list[Unit], dict[str, int], dict[str, Any]]:
    records: list[tuple[str, float, float, int]] = []
    populations: dict[str, int] = {}
    tracts: set[str] = set()
    water_only = 0
    with shapefile.Reader(str(source)) as reader:
        fields = [field[0] for field in reader.fields[1:]]
        required = {"GEOID20", "POP20", "INTPTLON20", "INTPTLAT20", "ALAND20", "AWATER20"}
        if not required.issubset(fields):
            raise ValueError(f"Missing source columns: {required - set(fields)}")
        for row in reader.iterRecords():
            geoid = str(row["GEOID20"])
            population = int(row["POP20"])
            lon, lat = float(row["INTPTLON20"]), float(row["INTPTLAT20"])
            if len(geoid) != 15 or not geoid.startswith("20") or geoid in populations:
                raise ValueError(f"Invalid or duplicate GEOID: {geoid}")
            if population < 0 or not math.isfinite(lon + lat):
                raise ValueError(f"Invalid source values: {geoid}")
            populations[geoid] = population
            records.append((geoid, lon, lat, population))
            tracts.add(geoid[:11])
            water_only += int(int(row["ALAND20"]) == 0 and int(row["AWATER20"]) > 0)
    total = sum(populations.values())
    if len(records) != EXPECTED_BLOCKS or total != EXPECTED_POPULATION:
        raise ValueError(f"Source totals do not match Census: blocks={len(records)}, population={total}")
    lon0 = sum(lon * pop for _, lon, _, pop in records) / total
    lat0 = sum(lat * pop for _, _, lat, pop in records) / total
    x_scale = 6_371_000 * math.pi / 180 * math.cos(math.radians(lat0))
    y_scale = 6_371_000 * math.pi / 180
    units = [Unit(geoid, ((lon - lon0) * x_scale, (lat - lat0) * y_scale), pop)
             for geoid, lon, lat, pop in records]
    return units, populations, {
        "block_count": len(records), "populated_block_count": sum(p > 0 for p in populations.values()),
        "zero_population_block_count": sum(p == 0 for p in populations.values()),
        "water_only_block_count": water_only, "tract_count": len(tracts),
        "total_population": total, "largest_block_population": max(populations.values()),
        "projection": {"kind": "population-centered-equirectangular", "lon0": lon0, "lat0": lat0},
        "location_source": "TIGER INTPT internal points, not household locations or population centroids",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/kansas-block-benchmark/run-435")
    parser.add_argument("--seed", type=int, default=20200955)
    parser.add_argument("--max-outer-iterations", type=int, default=80)
    parser.add_argument("--inner-max-iterations", type=int, default=300)
    parser.add_argument("--solve-only", action="store_true")
    parser.add_argument("--resume-export", action="store_true", help="Reuse saved solver output; measure export separately")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    measurement = Measurements()
    start = time.perf_counter()
    report: dict[str, Any] = {
        "state": "Kansas", "source_year": 2020, "unit": "census_block", "house_size": 435, "district_count": 4,
        "environment": {"python": sys.version, "platform": platform.platform(), "processor": platform.processor(),
                        "logical_cpu_count": os.cpu_count(),
                        "packages": {p: version(p) for p in ("numpy", "scipy", "pyshp", "shapely")}},
        "configuration": {"seed": args.seed, "max_outer_iterations": args.max_outer_iterations,
                          "inner_max_iterations": args.inner_max_iterations, "center_tolerance_m": 1e-4,
                          "solver_sha256": sha256(ROOT / "districting/algorithm.py")},
        "measurement_notes": ["One local run; wall timings include instrumentation overhead.",
                              "Peak working set is OS-reported for this Python process; phase peaks sampled every 100 ms.",
                              "All blocks stay whole, including zero-population and water blocks.",
                              "Population balance refers to published Census counts.",
                              "Geometric connectivity is checked separately from numerical center convergence."],
    }
    try:
        source, report["source"] = prepare_source(ROOT / ".cache/kansas-block-benchmark/source", measurement)
        with measurement.phase("load_and_validate_block_records"):
            units, populations, report["input"] = load_units(source)
        checkpoint = args.output / "solver-result.json"
        if args.resume_export:
            saved = json.loads(checkpoint.read_text())
            if saved["configuration"] != report["configuration"] or saved["source_sha256"] != report["source"]["archive_sha256"]:
                raise ValueError("Checkpoint configuration or source hash mismatch")
            assignments = saved["assignments"]
            report["solver"] = saved["solver"]
            report["solver_measurement_from_prior_process"] = saved["measurement"]
        else:
            with measurement.phase("solve"):
                result = balanced_power_diagram(units, 4, seed=args.seed,
                    max_outer_iterations=args.max_outer_iterations, inner_max_iterations=args.inner_max_iterations)
            assignments = dict(result.assignments)
            target = EXPECTED_POPULATION // 4
            tracts: dict[str, set[int]] = {}
            actual = [0] * 4
            if set(assignments) != set(populations):
                raise ValueError("Assignments do not cover all blocks")
            for geoid, district in assignments.items():
                actual[district] += populations[geoid]
                tracts.setdefault(geoid[:11], set()).add(district)
            if any(actual[i] != result.populations[i] for i in range(4)):
                raise ValueError("Population reconciliation failed")
            report["solver"] = {
                "iterations": result.iterations, "centers_converged": result.converged,
                "target_population": target, "district_populations": actual,
                "deviations_people": [p - target for p in actual],
                "max_absolute_deviation_people": max(abs(p - target) for p in actual),
                "max_absolute_deviation_percent": 100 * max(abs(p - target) for p in actual) / target,
                "total_range_people": max(actual) - min(actual),
                "total_range_percent": 100 * (max(actual) - min(actual)) / target,
                "tracts_split_across_districts": sum(len(s) > 1 for s in tracts.values()),
                "all_blocks_assigned_once": True, "population_sum_matches_source": True,
                "centers": [asdict(c) for c in result.centers],
            }
            checkpoint.write_text(json.dumps({"configuration": report["configuration"],
                "source_sha256": report["source"]["archive_sha256"], "solver": report["solver"],
                "assignments": assignments, "measurement": measurement.phases["solve"]}, separators=(",", ":")))
            print(json.dumps(report["solver"], indent=2), flush=True)
        del units
        if not args.solve_only:
            from district_block_map_export import export_maps
            with measurement.phase("geometry_validation_and_map_export"):
                report["maps"] = export_maps(source, assignments, populations, args.output / "maps")
    finally:
        report["phases"] = measurement.phases
        report["timed_pipeline_wall_seconds"] = time.perf_counter() - start
        report["peak_process_working_set_bytes"] = process_memory()[1]
        report["script_sha256"] = sha256(Path(__file__))
        measurement.close()
        name = "export-report.json" if args.resume_export else "benchmark.json"
        (args.output / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report: {args.output / name}", flush=True)


if __name__ == "__main__":
    main()
