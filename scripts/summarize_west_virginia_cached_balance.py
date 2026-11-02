"""Verify and compare the preserved West Virginia connectivity-cache experiment.

This reads terminal evidence only. It never starts a solve, repeats balancing,
or edits an original run; only the new comparison and durable reports are written.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
from html import escape
import io
import json
import math
import os
from pathlib import Path
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import shapefile
import shapely
from shapely.geometry import shape

from scripts.district_block_graph_cache import _identity, _read_cache
from scripts.state_block_execution_lock import state_execution_lock
from scripts.summarize_florida_water import windows_pid_status

SUITE = ROOT / ".cache/state-block-benchmark/suite-through-1000"
OUTPUT = SUITE / "corrections/west-virginia-cached-balance-v1"
ORIGINAL = SUITE / "states/54/districts-3"
DIAGNOSIS = SUITE / "diagnostics/west-virginia"
ARCHIVE = ROOT / ".cache/state-block-benchmark/source/54/tl_2020_54_tabblock20.zip"
SOURCE_SHA = "04e931a5d288ed62da3b947239f3f23f8b6a8d8b4a749ec749eb90158b50f863"
REPORT = ROOT / "prompts/west-virginia-cached-balance-benchmark"
URL = "http://127.0.0.1:8770/corrections/west-virginia-cached-balance-v1/"
COUNTS = 72_558, 1_793_716
JOB_PATHS = (
    "verification/traversal-100/benchmark.json",
    "verification/cached-100/benchmark.json",
    "states/54/districts-3/benchmark.json",
)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError("Expected a nonempty relative evidence path")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError("Evidence path escapes its directory")
    return path


def finite(value, *, positive=False):
    if type(value) not in (float, int) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError("Expected a finite nonnegative measurement")
    return value


def verify_inventory(inventory: dict, *, root: Path = ROOT) -> None:
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError("A nonempty preservation/hash inventory is required")
    for name, expected in inventory.items():
        path = safe_path(root, name)
        if not isinstance(expected, str) or len(expected) != 64 or not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Preserved evidence or code changed: {name}")


def metrics(populations: list[int]) -> dict:
    if not populations or any(type(p) is not int or p < 0 for p in populations):
        raise ValueError("District populations must be nonnegative integers")
    total, k = sum(populations), len(populations)
    if total <= 0:
        raise ValueError("A positive source population is required")
    numerators = [k * p - total for p in populations]
    worst = max(map(abs, numerators))
    remainder = total % k
    minimum_numerator = max(remainder, k - remainder) if remainder else 0
    return {
        "district_populations": list(populations), "total_population": total,
        "ideal_population": total / k, "deviation_numerators": numerators,
        "max_absolute_deviation_people": worst / k,
        "max_absolute_deviation_percent": worst / total * 100,
        "squared_deviation_numerator": sum(n * n for n in numerators),
        "squared_deviation_people": sum(n * n for n in numerators) / k**2,
        "total_range_people": max(populations) - min(populations),
        "ideal_floor_population": total // k, "ideal_ceil_population": (total + k - 1) // k,
        "integer_population_lower_bound_numerator": minimum_numerator,
        "integer_population_lower_bound_denominator": k,
        "integer_population_lower_bound_people": minimum_numerator / k,
        "integer_population_lower_bound_attained": worst == minimum_numerator,
    }


def population_audit(assignments: dict, source: dict[str, int], k=3) -> dict:
    if not isinstance(assignments, dict) or set(assignments) != set(source):
        raise ValueError("Assignments do not cover every source block exactly once")
    totals, counts = [0] * k, [0] * k
    for geoid, district in assignments.items():
        if type(district) is not int or not 0 <= district < k:
            raise ValueError("Invalid whole-block district assignment")
        totals[district] += source[geoid]
        counts[district] += 1
    if not all(counts):
        raise ValueError("Empty district")
    return {**metrics(totals), "district_block_counts": counts, "all_blocks_assigned_once": True}


def verify_plan_metrics(saved: dict, audited: dict) -> None:
    aliases = {
        "district_populations": ("district_populations", "populations"),
        "max_absolute_deviation_people": ("max_absolute_deviation_people", "max_deviation_people"),
        "max_absolute_deviation_percent": ("max_absolute_deviation_percent", "max_deviation_percent"),
    }
    for key, names in aliases.items():
        supplied = [saved[n] for n in names if n in saved]
        if not supplied:
            raise ValueError(f"Missing independently checkable final metric: {key}")
        for value in supplied:
            expected = audited[key]
            if isinstance(expected, list):
                if value != expected:
                    raise ValueError(f"Population metric disagrees with source: {key}")
            elif not math.isclose(finite(value), expected, rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError(f"Population metric disagrees with source: {key}")
    for key in ("total_population", "deviation_numerators", "district_block_counts", "squared_deviation_numerator"):
        if key in saved and saved[key] != audited[key]:
            raise ValueError(f"Exact population metric disagrees with source: {key}")


def replay_moves(start: dict, moves: list[dict], source: dict[str, int], *, offset=0, require_improvement=True) -> tuple[dict, list[dict]]:
    """Independent whole-block move replay with exact lexicographic objectives."""
    labels = dict(start)
    before = population_audit(labels, source)
    pops = before["district_populations"]
    geoids = list(source)
    trace = [{"moves": offset, **metrics(pops)}]
    for number, move in enumerate(moves, 1):
        units, names = move.get("units"), move.get("geoids")
        donor, recipient = move.get("source_district"), move.get("target_district")
        if (not isinstance(units, list) or not units or len(units) != len(set(units))
                or any(type(u) is not int or not 0 <= u < len(geoids) for u in units)
                or names != [geoids[u] for u in units]
                or type(donor) is not int or type(recipient) is not int
                or not 0 <= donor < 3 or not 0 <= recipient < 3 or donor == recipient
                or any(labels[g] != donor for g in names)):
            raise ValueError("Move ordering, unit identity or district ownership is inconsistent")
        amount = sum(source[g] for g in names)
        if type(move.get("population")) is not int or move["population"] != amount:
            raise ValueError("Move population does not match original DBF records")
        previous = metrics(pops)
        for geoid in names:
            labels[geoid] = recipient
        pops[donor] -= amount
        pops[recipient] += amount
        current = metrics(pops)
        old_objective = (max(map(abs, previous["deviation_numerators"])), previous["squared_deviation_numerator"])
        new_objective = (max(map(abs, current["deviation_numerators"])), current["squared_deviation_numerator"])
        if require_improvement and not new_objective < old_objective:
            raise ValueError("A boundary move does not improve the exact lexicographic objective")
        trace.append({"moves": offset + number, **current})
    population_audit(labels, source)
    return labels, trace


def exact_equivalence(traversal: dict, cached: dict, diagnostic: dict) -> dict:
    """Compare ordered decisions, not merely equal final population totals."""
    for name in ("moves", "assignments", "stop_reason"):
        if traversal[name] != cached[name]:
            raise ValueError(f"Traversal and cached modes differ: {name}")
        if cached[name] != diagnostic[name]:
            raise ValueError(f"Fresh 100-move result differs from preserved diagnostic: {name}")
    if len(cached["moves"]) != 100:
        raise ValueError("The controlled comparison must contain exactly 100 moves")
    return {"ordered_moves_identical": True, "assignments_identical": True,
            "stop_reason_identical": True, "matches_preserved_diagnostic_100": True,
            "compared_move_count": 100}


def verify_manifest(manifest: dict) -> None:
    jobs = manifest.get("jobs", [])
    if (manifest.get("status") != "complete" or not manifest.get("finished_at")
            or manifest.get("preservation_unchanged") is not True
            or len(jobs) != 3 or [j.get("report") for j in jobs] != list(JOB_PATHS)):
        raise ValueError("Only the completed, preserved three-process experiment may be summarized")
    for job in jobs:
        if (job.get("status") != "complete" or type(job.get("returncode")) is not int
                or job["returncode"] != 0 or not job.get("started_at") or not job.get("finished_at")):
            raise ValueError("A child is incomplete, failed, or lacks a confirmed exit")
        finite(job.get("elapsed_seconds"), positive=True)


def select_report(job: dict, root: Path = OUTPUT) -> tuple[Path, dict]:
    path = safe_path(root, job["report"])
    if sha256(path) != job.get("report_sha256"):
        raise ValueError("Parent-selected terminal report changed")
    report = read(path)
    if report.get("status") != "complete":
        raise ValueError("Parent selected an incomplete or failed report")
    return path.parent, report


def process_audit(manifest: dict, reports: list[dict]) -> dict:
    records = [manifest, *manifest["jobs"], *reports]
    raw_pids = [r[key] for r in records for key in ("pid", "launcher_pid", "child_pid") if key in r]
    if (any(type(r.get("pid")) is not int for r in records)
            or not raw_pids or any(type(pid) is not int or pid <= 0 for pid in raw_pids)):
        raise ValueError("Missing or invalid recorded process identity")
    if any(job.get("child_pid") != report["pid"] for job, report in zip(manifest["jobs"], reports, strict=True)):
        raise ValueError("Parent and child process identities disagree")
    pids = sorted(set(raw_pids))
    if os.name == "nt":
        observations = windows_pid_status(pids)
    else:
        observations = []
        for pid in pids:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                observations.append({"pid": pid, "active": False})
            else:
                observations.append({"pid": pid, "active": True})
    if any(row["active"] for row in observations):
        raise ValueError("A recorded process is active or its PID was reused; inspect before summarizing")
    return {"all_recorded_processes_exited": True, "observations": observations,
            "state54_lock_held_during_validation": True}


def source_records() -> tuple[dict[str, int], list]:
    if sha256(ARCHIVE) != SOURCE_SHA:
        raise ValueError("Original source archive identity changed")
    stem = ARCHIVE.stem
    with zipfile.ZipFile(ARCHIVE) as archive:
        with shapefile.Reader(shp=io.BytesIO(archive.read(stem + ".shp")),
                              shx=io.BytesIO(archive.read(stem + ".shx")),
                              dbf=io.BytesIO(archive.read(stem + ".dbf"))) as reader:
            source, geometries = {}, []
            for row in reader.iterShapeRecords():
                geoid, population = str(row.record["GEOID20"]), row.record["POP20"]
                if (geoid in source or len(geoid) != 15 or not geoid.isdigit() or not geoid.startswith("54")
                        or type(population) is not int or population < 0):
                    raise ValueError("Invalid original source block identity or population")
                geometry = shape(row.shape.__geo_interface__)
                if geometry.geom_type != "Polygon" or geometry.is_empty or not geometry.is_valid:
                    raise ValueError("Expected unchanged valid single-part West Virginia blocks")
                source[geoid] = population
                geometries.append(geometry)
    if (len(source), sum(source.values())) != COUNTS or not bool(shapely.coverage_is_valid(geometries)):
        raise ValueError("Source population totals or polygon coverage failed")
    return source, geometries


def graph_components(graph, assignments: dict, geoids: list[str]) -> list[int]:
    labels = [assignments[g] for g in geoids]
    seen, counts = set(), [0, 0, 0]
    for start, district in enumerate(labels):
        if start in seen:
            continue
        counts[district] += 1
        seen.add(start)
        stack = [start]
        while stack:
            for node in graph[stack.pop()]:
                if node not in seen and labels[node] == district:
                    seen.add(node)
                    stack.append(node)
    return counts


def compressed_maps(directory: Path, manifest: dict, assignments: dict, source: dict, geometries: list) -> dict:
    """Verify all delivered files and reconcile county features against source."""
    artifacts = manifest.get("storage", {}).get("artifacts", [])
    if not artifacts:
        raise ValueError("No delivered compressed artifact inventory")
    seen, verified, full = set(), [], None
    source_geometry = dict(zip(source, geometries, strict=True))
    for item in artifacts:
        path = safe_path(directory / "maps", item["gzip_path"])
        raw = gzip.decompress(path.read_bytes())
        if (path.stat().st_size != item["gzip_bytes"] or len(raw) != item["raw_bytes"]
                or hashlib.sha256(raw).hexdigest() != item["raw_sha256"]):
            raise ValueError("Compressed map bytes do not match the delivered manifest")
        payload = json.loads(raw, object_pairs_hook=unique_pairs)
        verified.append(item["gzip_path"])
        if path.name == "districts-full.geojson.gz":
            full = payload
        if path.name.startswith("county-"):
            for feature in payload["features"]:
                props = feature["properties"]
                geoid = str(props.get("geoid", props.get("GEOID20", "")))
                district = props.get("district_id", props.get("district"))
                if (type(district) is not int or type(props.get("population")) is not int
                        or geoid in seen or geoid not in source or props.get("population") != source[geoid]
                        or district != assignments[geoid] or not shape(feature["geometry"]).equals(source_geometry[geoid])):
                    raise ValueError("County map feature differs from source geometry/population/assignment")
                seen.add(geoid)
    if seen != set(source) or full is None:
        raise ValueError("Delivered county coverage or full district outlines are incomplete")
    props = sorted((f["properties"] for f in full["features"]), key=lambda p: p["district_id"])
    independent = population_audit(assignments, source)
    if ([p["district_id"] for p in props] != [0, 1, 2]
            or [p["population"] for p in props] != independent["district_populations"]
            or [p["block_count"] for p in props] != independent["district_block_counts"]):
        raise ValueError("Full-map properties disagree with original DBF totals")
    delivered = {f["properties"]["district_id"]: shape(f["geometry"]) for f in full["features"]}
    for district in range(3):
        expected = shapely.union_all([g for geoid, g in source_geometry.items() if assignments[geoid] == district])
        actual = delivered[district]
        if (expected.geom_type != "Polygon" or not expected.is_valid or actual.geom_type != "Polygon"
                or not actual.is_valid or not expected.symmetric_difference(actual).is_empty):
            raise ValueError("Full district map fails independent strict polygon/assignment audit")
    if not bool(shapely.coverage_is_valid(list(delivered.values()))):
        raise ValueError("Delivered district polygon coverage is invalid")
    source_union = shapely.union_all(geometries)
    if not source_union.symmetric_difference(shapely.union_all(list(delivered.values()))).is_empty:
        raise ValueError("Delivered district map changed source coverage")
    return {"verified_compressed_artifact_count": len(verified), "verified_paths": verified,
            "all_source_county_features_verified": True, "strict_polygon_components": [1, 1, 1],
            "source_coverage_preserved_exactly": True, "source_geometry_modified": False}


def verify_trace(saved: list, derived: list[dict]) -> None:
    if not isinstance(saved, list) or len(saved) != len(derived):
        raise ValueError("Saved trace does not contain every additional boundary move")
    for actual, expected in zip(saved, derived, strict=True):
        if actual.get("moves") != expected["moves"]:
            raise ValueError("Saved trace move numbers are inconsistent")
        verify_plan_metrics(actual, expected)


def validate_run(directory: Path, report: dict, source: dict, graph, original_assignments: dict, stage: str, runtime: dict) -> dict:
    expected_config = {
        "traversal-100": {"cache_connectivity": False, "max_additional_moves": 100, "chunk_size": 100},
        "cached-100": {"cache_connectivity": True, "max_additional_moves": 100, "chunk_size": 100},
        "continuation": {"cache_connectivity": True, "max_additional_moves": 10000, "chunk_size": 500},
    }[stage]
    if (report.get("stage") != stage or report.get("state_fips") != "54" or report.get("district_count") != 3
            or report.get("house_sizes") != [574] or report.get("config") != expected_config
            or report.get("numerical_solver_rerun") is not False or report.get("full_end_to_end_run") is not False
            or report.get("preservation_unchanged") is not True or report.get("code_sha256") != runtime
            or report.get("source", {}).get("archive_sha256") != SOURCE_SHA):
        raise ValueError("Child identity, configuration, source, code or preservation differs")
    if (report.get("input", {}).get("block_count") != len(source)
            or report.get("input", {}).get("total_population") != sum(source.values())
            or report.get("graph_cache", {}).get("identity") != _identity(list(source), SOURCE_SHA)):
        raise ValueError("Reported source totals or graph identity disagree with independent inputs")
    artifacts = report.get("artifact_sha256", {})
    if not {"solver-result.json", "move-audit.json", "trace.json"}.issubset(artifacts):
        raise ValueError("Required final artifacts are absent from the terminal report")
    verify_inventory(artifacts, root=directory)
    progress = read(directory / "progress.json")
    if (progress.get("status") != "complete" or progress.get("finished_at") != report.get("finished_at")
            or progress.get("accepted_map") != report.get("accepted_map")
            or progress.get("rebalance_move_count") != report.get("rebalance_move_count")):
        raise ValueError("Final progress is stale or contradicts the parent-selected report")
    if report.get("original_run", {}).get("benchmark_sha256") != sha256(ORIGINAL / "benchmark.json"):
        raise ValueError("Original benchmark reference changed")
    initial = population_audit(original_assignments, source)
    verify_plan_metrics(report["initial_plan"], initial)
    assignment_record = read(directory / "solver-result.json")
    if (assignment_record.get("source_sha256") != SOURCE_SHA
            or assignment_record.get("original_assignments_sha256") != sha256(ORIGINAL / "solver-result.json")):
        raise ValueError("Saved assignments lost original endpoint/source provenance")
    assignments = assignment_record["assignments"]
    final = population_audit(assignments, source)
    verify_plan_metrics(report["final_plan"], final)
    audit = read(directory / "move-audit.json")
    moves = audit.get("rebalance_moves")
    if (audit.get("repair_moves") != [] or report.get("repair_move_count") != 0 or not isinstance(moves, list)
            or audit.get("original_cumulative_moves") != 1000
            or audit.get("total_cumulative_moves") != 1000 + len(moves)
            or report.get("rebalance_move_count") != len(moves)):
        raise ValueError("Continuation move audit does not start at the unchanged original endpoint")
    limit = expected_config["max_additional_moves"]
    stop = report.get("stop_reason")
    if len(moves) > limit or stop not in ("max_moves", "local_optimum") or (stop == "max_moves" and len(moves) != limit):
        raise ValueError("Move count, stopping reason and budget disagree")
    replayed, trace = replay_moves(original_assignments, moves, source)
    if replayed != assignments:
        raise ValueError("Ordered move replay does not reproduce saved assignments")
    verify_trace(read(directory / "trace.json"), trace)
    components = graph_components(graph, assignments, list(source))
    if components != [1, 1, 1] or report["final_plan"].get("shared_edge_components") != components:
        raise ValueError("Final induced shared-edge graph is disconnected")
    for key in ("rebalance_seconds", "timed_pipeline_wall_seconds", "peak_process_working_set_bytes"):
        finite(report.get(key), positive=True)
    if report["rebalance_seconds"] > report["timed_pipeline_wall_seconds"]:
        raise ValueError("Balancing time exceeds measured pipeline time")
    chunks = report.get("chunks", [])
    cumulative, elapsed = 0, 0.0
    for chunk in chunks:
        if type(chunk.get("moves")) is not int or not 0 <= chunk["moves"] <= expected_config["chunk_size"]:
            raise ValueError("Invalid checkpoint chunk move count")
        cumulative += chunk["moves"]
        elapsed += finite(chunk.get("wall_seconds"), positive=True)
        if chunk.get("cumulative_additional_moves") != cumulative:
            raise ValueError("Chunk boundaries do not reconcile with ordered moves")
        checkpoint = read(directory / f"checkpoint-{cumulative:05d}.json")
        if checkpoint.get("status") != "checkpoint_not_accepted" or checkpoint.get("additional_moves") != cumulative:
            raise ValueError("Intermediate checkpoint is mislabeled")
    if (not chunks or cumulative != len(moves) or not math.isclose(elapsed, report["rebalance_seconds"], rel_tol=1e-10)
            or chunks[-1].get("stop_reason") != stop):
        raise ValueError("Balancing-only timing or chunk termination does not reconcile")
    accepted = stage == "continuation"
    if report.get("accepted_map") is not accepted:
        raise ValueError("Verification runs must not be labelled accepted corrected maps")
    return {"stage": stage, "accepted_map": accepted, "initial": initial, "final": final,
            "additional_moves": len(moves), "total_cumulative_moves": 1000 + len(moves), "stop_reason": stop,
            "rebalance_seconds": report["rebalance_seconds"],
            "pipeline_seconds": report["timed_pipeline_wall_seconds"],
            "peak_process_working_set_bytes": report["peak_process_working_set_bytes"],
            "graph_components": components, "config": expected_config, "chunks": chunks,
            "moves": moves, "assignments": assignments, "trace": trace,
            "report_sha256": sha256(directory / "benchmark.json")}


def verify_equivalence_record(record: dict, traversal: dict, cached: dict) -> float:
    flags = ("passed", "ordered_moves_equal", "assignments_equal", "stop_reasons_equal",
             "matches_preserved_probe", "fresh_processes")
    if (any(record.get(key) is not True for key in flags) or record.get("profiling_enabled") is not False
            or record.get("move_count") != 100):
        raise ValueError("Parent equivalence certificate is incomplete")
    speedup = finite(traversal["rebalance_seconds"], positive=True) / finite(cached["rebalance_seconds"], positive=True)
    for key, expected in (("traversal_seconds", traversal["rebalance_seconds"]),
                          ("cached_seconds", cached["rebalance_seconds"]), ("measured_speedup", speedup)):
        if not math.isclose(finite(record.get(key), positive=True), expected, rel_tol=1e-10):
            raise ValueError("Parent timing comparison differs from the matched reports")
    return speedup


def collect(validation_note: str) -> dict:
    began = time.perf_counter()
    manifest = read(OUTPUT / "run.json")
    verify_manifest(manifest)
    inventory_path = safe_path(OUTPUT, manifest.get("preservation_inventory"))
    preserved = read(inventory_path)
    required = {p.relative_to(ROOT).as_posix() for folder in (SUITE / "states/54", DIAGNOSIS)
                for p in folder.rglob("*") if p.is_file()}
    if not required.issubset(preserved):
        raise ValueError("Preservation inventory does not cover all original WV runs and diagnostics")
    verify_inventory(preserved)
    runtime = manifest["code_sha256"]
    verify_inventory(runtime)
    prelaunch = OUTPUT / "prelaunch-validation.json"
    if sha256(prelaunch) != manifest.get("prelaunch_validation_sha256") or read(prelaunch).get("status") != "passed":
        raise ValueError("Prelaunch validation record changed or did not pass")
    selected = [select_report(job) for job in manifest["jobs"]]
    lifecycle = process_audit(manifest, [report for _, report in selected])
    source, geometries = source_records()
    prior = read(ORIGINAL / "benchmark.json")
    if prior.get("status") != "complete" or prior["maps"]["strict_validation"]["passed"] is not True:
        raise ValueError("Original endpoint is not a validated connected map")
    verify_inventory(prior["artifact_sha256"], root=ORIGINAL)
    original_assignments = read(ORIGINAL / "solver-result.json")["assignments"]
    original_metrics = population_audit(original_assignments, source)
    verify_plan_metrics(prior["final_plan"], original_metrics)
    identity = _identity(list(source), SOURCE_SHA)
    if identity != prior["graph_cache"]["identity"]:
        raise ValueError("Source ordering or exact graph identity changed")
    graph, info = _read_cache(Path(prior["graph_cache"]["path"]), identity)
    if info != prior["graph"] or info.get("multipart_block_count") != 0:
        raise ValueError("Expected the preserved single-part West Virginia graph")
    if graph_components(graph, original_assignments, list(source)) != [1, 1, 1]:
        raise ValueError("Original starting assignment is disconnected")
    runs = [validate_run(directory, report, source, graph, original_assignments, job["id"], runtime)
            for (directory, report), job in zip(selected, manifest["jobs"], strict=True)]
    diagnosis = read(DIAGNOSIS / "diagnosis.json")
    if (diagnosis.get("status") != "diagnosis_complete" or diagnosis["probe"].get("accepted_map") is not False
            or diagnosis["probe"].get("strict_polygon_validation_passed") is not True
            or diagnosis.get("source", {}).get("archive_sha256") != SOURCE_SHA):
        raise ValueError("Preserved diagnostic probe is incomplete or mislabeled")
    snapshot = read(OUTPUT / "baseline-code.json")
    diagnostic_code = read(DIAGNOSIS / "probe-assignments.json")["code_sha256"]
    for name, entry in snapshot.items():
        if (entry.get("sha256") != diagnostic_code.get(name)
                or sha256(safe_path(ROOT, entry.get("snapshot"))) != entry["sha256"]):
            raise ValueError("Saved pre-cache implementation differs from its diagnostic provenance")
    diagnostic = {"moves": read(DIAGNOSIS / "probe-moves.json")["moves"],
                  "assignments": read(DIAGNOSIS / "probe-assignments.json")["assignments"],
                  "stop_reason": diagnosis["probe"]["stop_reason"]}
    diagnostic_replayed, diagnostic_trace = replay_moves(original_assignments, diagnostic["moves"], source)
    if diagnostic_replayed != diagnostic["assignments"]:
        raise ValueError("Preserved diagnostic moves do not reconcile")
    equivalence = exact_equivalence(runs[0], runs[1], diagnostic)
    equivalent_record = read(OUTPUT / "verification/equivalence.json")
    if manifest.get("equivalence") != equivalent_record:
        raise ValueError("Parent and saved equivalence records disagree")
    speedup = verify_equivalence_record(equivalent_record, runs[0], runs[1])
    corrected = runs[2]
    if corrected["moves"][:100] != runs[1]["moves"]:
        raise ValueError("Long continuation does not reproduce the verified 100-move prefix")
    directory, final_report = selected[2]
    map_manifest = read(directory / "maps/map-manifest.json")
    if (map_manifest != final_report.get("maps") or map_manifest["strict_validation"]["passed"] is not True
            or final_report.get("matched_verified_prefix") is not True
            or final_report.get("coverage_validation", {}).get("exact_original_union_preserved") is not True):
        raise ValueError("Corrected map lacks terminal strict connectivity/coverage acceptance")
    maps_audit = compressed_maps(directory, map_manifest, corrected["assignments"], source, geometries)
    old_full = read_gzip_json(ORIGINAL / "maps/districts-full.geojson.gz")
    new_full = read_gzip_json(directory / "maps/districts-full.geojson.gz")
    if not shapely.union_all([shape(f["geometry"]) for f in old_full["features"]]).symmetric_difference(
            shapely.union_all([shape(f["geometry"]) for f in new_full["features"]])).is_empty:
        raise ValueError("Corrected map does not preserve the exact original district union")
    before_repair = read(ORIGINAL / "after-repair-result.json")["assignments"]
    original_audit = read(ORIGINAL / "move-audit.json")
    original_replayed, original_trace = replay_moves(before_repair, original_audit["rebalance_moves"], source)
    if original_replayed != original_assignments:
        raise ValueError("Original 1,000-move trace no longer reconciles")
    combined_trace = original_trace + [{**row, "moves": 1000 + row["moves"]} for row in corrected["trace"][1:]]
    # Repeat identity checks after expensive geometry validation.
    verify_inventory(preserved)
    verify_inventory(runtime)
    result = {
        "status": "independently_validated", "state": "West Virginia", "state_fips": "54", "district_count": 3,
        "house_sizes": [574], "source": {"block_count": len(source), "resident_population": sum(source.values()), "archive_sha256": SOURCE_SHA},
        "original": {"final": original_metrics, "balancing_moves": 1000,
                     "pipeline_seconds": prior["timed_pipeline_wall_seconds"],
                     "repair_and_rebalance_seconds": prior["phases"]["repair_and_rebalance"]["wall_seconds"],
                     "solve_seconds": prior["phases"]["solve"]["wall_seconds"],
                     "peak_process_working_set_bytes": prior["peak_process_working_set_bytes"]},
        "diagnostic_probe": {"final": population_audit(diagnostic["assignments"], source),
                             "additional_moves": len(diagnostic["moves"]), "elapsed_seconds": diagnosis["probe"]["elapsed_seconds"],
                             "guard_profile": {k: diagnosis["probe"][k] for k in ("guard_calls", "guard_failed_calls", "guard_wall_seconds")},
                             "accepted_map": False},
        "matched_equivalence": {**equivalence, "fresh_processes": True, "guard_profiling": False,
                                "traversal_seconds": runs[0]["rebalance_seconds"], "cached_seconds": runs[1]["rebalance_seconds"],
                                "measured_speedup": speedup, "measurement_scope": "One serial fresh-process measurement per mode on matched inputs; no statistical speedup interval."},
        "runs": [{k: v for k, v in run.items() if k not in ("moves", "assignments", "trace")} for run in runs],
        "correction": {**{k: v for k, v in corrected.items() if k not in ("moves", "assignments", "trace")},
                       "map_url": URL + "states/54/districts-3/", "maps_validation": maps_audit,
                       "map_payloads": map_manifest["load_scenarios"], "map_phase_seconds": final_report["phases"]["independent_polygon_validation_and_map_export"]["wall_seconds"],
                       "coverage_phase_seconds": final_report["phases"]["verify_exact_original_coverage"]["wall_seconds"]},
        "trace": combined_trace, "lifecycle": lifecycle,
        "preservation": {"all_original_and_diagnostic_files_unchanged": True, "protected_file_count": len(preserved),
                         "inventory_sha256": sha256(inventory_path)},
        "code_sha256": runtime, "prelaunch_validation": read(prelaunch),
        "validation_note": validation_note, "summary_validation_seconds": time.perf_counter() - began,
        "parent_elapsed_seconds": manifest["elapsed_seconds"], "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def read_gzip_json(path: Path):
    return json.loads(gzip.decompress(path.read_bytes()), object_pairs_hook=unique_pairs)


def markdown(data: dict) -> str:
    old, probe, new = data["original"], data["diagnostic_probe"], data["correction"]
    equivalence = data["matched_equivalence"]
    final = new["final"]
    rows = [
        "# West Virginia: cached connectivity checks and a larger balancing budget",
        "",
        f"The new three-district continuation passes independent strict shared-edge graph and unsimplified polygon validation. Its maximum population deviation is **{final['max_absolute_deviation_people']:,.3f} people ({final['max_absolute_deviation_percent']:.8f}%)**, after **{new['additional_moves']:,} additional boundary moves** from the original connected endpoint. It stopped at `{new['stop_reason']}`.",
        "",
        f"[Comparison and measured trace]({URL}) · [Validated corrected map]({new['map_url']}) · [Original map](http://127.0.0.1:8770/states/54/districts-3/) · [Preserved diagnosis](http://127.0.0.1:8770/diagnostics/west-virginia/)",
        "",
        "| Assignment | Additional moves after original endpoint | District populations | Maximum deviation |",
        "|---|---:|---|---:|",
    ]
    for name, count, m in (("Original connected plan", 0, old["final"]),
                           ("Preserved diagnostic probe", probe["additional_moves"], probe["final"]),
                           ("Validated cached continuation", new["additional_moves"], final)):
        rows.append(f"| {name} | {count:,} | {' / '.join(f'{p:,}' for p in m['district_populations'])} | {m['max_absolute_deviation_people']:,.3f} people ({m['max_absolute_deviation_percent']:.8f}%) |")
    rows.extend([
        "",
        f"All **{data['source']['block_count']:,} source blocks and {data['source']['resident_population']:,} residents** remain assigned exactly once. Every final district has one physical shared-edge graph component and one valid unsimplified polygon. Source coverage and original district-union coverage are preserved exactly, with no water connections, source-geometry edits or new numerical power-diagram solve.",
        "",
        (f"The endpoint **attains the integer-population arithmetic lower bound of {final['integer_population_lower_bound_numerator']}/{final['integer_population_lower_bound_denominator']} person** from the fractional ideal. District populations are the floor/ceiling values {final['ideal_floor_population']:,} and {final['ideal_ceil_population']:,}, with a range of {final['total_range_people']} resident. No integer district populations can have a smaller maximum deviation. This certifies the best possible maximum population balance for this total/count, not globally optimal compactness or other districting objectives."
         if final["integer_population_lower_bound_attained"] else
         f"The arithmetic lower bound, ignoring indivisible-block restrictions, is {final['integer_population_lower_bound_people']:.6f} person. It was not reached. A local optimum is local to the implemented moves, not a global-optimality certificate."),
        "",
        "## Controlled 100-move comparison",
        "",
        "Both verification runs start from the same original 1,000-move endpoint in serial fresh processes, using the same source, candidate ordering, move budget and current code. The only mode difference is cached versus traversal donor-connectivity checks. Every ordered move, final block assignment and stop reason matches, including the preserved diagnostic probe. The longer continuation reproduces this verified 100-move prefix.",
        "",
        "| Mode | Balancing only | Full verification process pipeline | Peak process working set |",
        "|---|---:|---:|---:|",
    ])
    for run in data["runs"][:2]:
        name = "Traversal checks" if run["stage"] == "traversal-100" else "Cached checks"
        rows.append(f"| {name} | {run['rebalance_seconds']:.3f} s | {run['pipeline_seconds']:.3f} s | {run['peak_process_working_set_bytes']/2**20:.1f} MiB |")
    rows.extend([
        "",
        f"The measured balancing-only speedup is **{equivalence['measured_speedup']:.2f}×** on this matched 100-move case. This is one serial measurement per mode, not a repeated statistical benchmark or a nationwide speedup claim. The earlier diagnostic probe took {probe['elapsed_seconds']:.3f} s with guard profiling enabled and is retained separately; it is not the denominator of this fresh speedup comparison.",
        "",
        "The cache records district membership and exact articulation points. Both donor and recipient caches are invalidated after each transfer. It changes how connectivity is checked, not the candidate ordering, population objective or whole-block/shared-edge constraints. The objective remains lexicographic: first maximum absolute population deviation, then squared deviations.",
        "",
        "## Larger continuation and runtime",
        "",
        f"The new budget allows 10,000 additional moves, with 500-move checkpoints. The run used {new['additional_moves']:,}, giving {new['total_cumulative_moves']:,} balancing moves including the original 1,000. The continuation starts afresh from the original endpoint; the earlier 100-move verification is not added to it.",
        "",
        "| Measured stage | Wall time |",
        "|---|---:|",
        f"| New balancing work | {new['rebalance_seconds']:.3f} s |",
        f"| New strict polygon validation and map export | {new['map_phase_seconds']:.3f} s |",
        f"| Exact old/new district-union comparison | {new['coverage_phase_seconds']:.3f} s |",
        f"| Complete correction pipeline | {new['pipeline_seconds']:.3f} s |",
        "",
        f"The corrected run's peak process working set is **{new['peak_process_working_set_bytes']/2**20:.1f} MiB**. The original pipeline took {old['pipeline_seconds']:.3f} s, including a {old['solve_seconds']:.3f} s power solve and {old['repair_and_rebalance_seconds']:.3f} s for repair plus balancing. Those original two-worker timings and the new continuation cover different work; their ratio is not a controlled algorithm-speedup result. Parent elapsed time across the three fresh child processes is {data['parent_elapsed_seconds']:.3f} s.",
        "",
        "## Delivered map and validation",
        "",
    ])
    payloads = new["map_payloads"]
    for label, key in (("National outlines", "national_state_only"), ("State entry plus detail index", "state_entry_outlines_and_detail_index"),
                       ("All county detail shards", "all_county_detail_shards"), ("Largest county shard", "largest_county_detail_shard")):
        rows.append(f"- {label}: {payloads[key]['gzip_bytes']:,} gzip bytes.")
    rows.extend([
        "",
        f"Independent summary validation checked original DBF populations, exact move replay and objective progress, source graph identity, final district graph connectivity, every full-resolution district against its assigned source blocks, original and source union preservation, all county feature geometries/populations/labels, and {new['maps_validation']['verified_compressed_artifact_count']} compressed payloads. All recorded processes exited; the state54 lock was acquired during validation.",
        "",
        f"All {data['preservation']['protected_file_count']:,} protected original/diagnostic files remain byte-identical. The original failed diagnostic audit and geometry-only finalization remain preserved. Historical runtime hashes are not assumed to equal current code; the current matched mode comparison and saved pre-cache source snapshot establish the narrower provenance. The existing K2 legacy inner-optimizer warning is unchanged and no K2 rerun was performed.",
        "",
        f"Prelaunch test evidence is preserved separately from this follow-up: {data['validation_note']} Independent summary validation took {data['summary_validation_seconds']:.3f} s and is not included in the benchmark pipeline measurements. These offline block maps do not replace the app's cached tract plans.",
        "",
    ])
    return "\n".join(rows)


PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>West Virginia · Cached balance correction</title><style>
:root{color-scheme:dark;--bg:#0d1421;--panel:#142033;--line:#31435c;--muted:#a9b8ce;--ink:#eef5ff;--green:#25d3a8;--pink:#ff7abd;--gold:#ffc65b}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1180px;margin:auto;padding:30px 24px 64px}a{color:#81d7ff;text-underline-offset:3px}nav{display:flex;gap:18px;flex-wrap:wrap;font-size:13px}.eyebrow{color:var(--green);letter-spacing:.12em;text-transform:uppercase;font-size:12px;font-weight:700;margin-top:30px}h1{font-size:clamp(32px,4vw,47px);line-height:1.12;letter-spacing:-.035em;margin:12px 0 20px}h2{font-size:22px;line-height:1.3;margin:0 0 12px}p{margin:9px 0 15px}.lede{font-size:18px;color:#d7e3f5;max-width:980px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:28px 0}.card,.panel{border:1px solid var(--line);border-radius:12px;padding:22px;background:var(--panel)}.card b{display:block;font-size:32px;letter-spacing:-.025em;margin:4px 0}.muted{color:var(--muted);font-size:13px}.panel{margin:20px 0}.cta{display:inline-block;margin:10px 10px 8px 0;padding:10px 16px;background:#214c4c;border:1px solid var(--green);border-radius:7px;color:#dcfff3;text-decoration:none;font-weight:650}.secondary{background:#20324c;border-color:#536d90;color:#dbeaff}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}th,td{padding:12px 10px;border-bottom:1px solid var(--line);white-space:nowrap;text-align:left}th{color:var(--muted);font-weight:600}th:first-child,td:first-child{padding-left:0}.highlight{background:#1c3b42}.split{display:grid;grid-template-columns:1.2fr 1fr;gap:18px}.split .panel{margin:0}.badge{display:inline-block;border:1px solid #5e7896;border-radius:5px;padding:3px 8px;color:#cedff2;font-size:12px}.chart{width:100%;height:320px;display:block}.chart-label{fill:#a9b8ce;font:12px system-ui}.grid{stroke:#31435c;stroke-width:1}.controls{display:flex;gap:9px;flex-wrap:wrap;margin:16px 0}button{background:#213550;border:1px solid #526987;color:var(--ink);border-radius:6px;padding:8px 12px;font:13px system-ui;cursor:pointer}button[aria-pressed=true]{border-color:#81d7ff;background:#2c506b}button:focus-visible,a:focus-visible{outline:3px solid var(--gold);outline-offset:3px}.legend{display:flex;gap:20px;flex-wrap:wrap;font-size:13px;color:var(--muted)}.swatch{display:inline-block;height:3px;width:22px;vertical-align:middle;margin-right:6px}.note{border-left:3px solid var(--gold);padding:12px 16px;background:#30291d}.good{color:var(--green)}ul{padding-left:22px}li{margin:8px 0}.footer{font-size:12px;color:var(--muted);margin-top:25px}@media(max-width:760px){main{padding:24px 16px}.cards,.split{grid-template-columns:1fr}.card b{font-size:28px}}
</style></head><body><main><nav><a href="../../">All state benchmarks</a><a href="../../diagnostics/west-virginia/">Preserved diagnosis</a><a href="../../states/54/districts-3/">Original K3 map</a><a href="comparison.json">Machine-readable comparison</a></nav><div class="eyebrow">West Virginia / 3 districts / House 574</div><h1>Exact connectivity checks.<br>A longer balancing run.</h1><p class="lede" id="headline"></p><a class="cta" href="states/54/districts-3/">Open validated corrected map →</a><a class="cta secondary" href="../../states/54/districts-3/">Compare original map</a>
<div class="cards"><div class="card"><span class="muted">New maximum district deviation</span><b id="new-deviation"></b><span class="muted" id="new-percent"></span></div><div class="card"><span class="muted">Matched 100-move speedup</span><b id="speedup"></b><span class="muted">Balancing only; one fresh-process trial per mode</span></div><div class="card"><span class="muted">Additional moves from original endpoint</span><b id="move-count"></b><span class="muted" id="termination"></span></div></div>
<section class="panel"><h2>Population balance, with strict connectivity retained</h2><div class="table-wrap"><table><thead><tr><th>Assignment</th><th>Additional moves</th><th>District populations</th><th>Maximum deviation</th><th>Status</th></tr></thead><tbody id="population-table"></tbody></table></div><p class="muted" id="source-summary"></p></section>
<section class="panel"><h2>Same 100 moves, faster connectivity checks</h2><p>Traversal and cached modes start from the same preserved connected assignment. Both run in fresh serial processes. Every ordered block transfer, final assignment and stop reason matches the earlier diagnostic probe. The full continuation also reproduces that 100-move prefix.</p><div class="table-wrap"><table><thead><tr><th>Mode</th><th>Balancing wall time</th><th>Verification pipeline</th><th>Peak working set</th></tr></thead><tbody id="timing-table"></tbody></table></div><p class="muted" id="old-probe"></p><div class="note">This is a single matched timing comparison, not a repeated statistical benchmark or a nationwide speedup estimate. Verification runs produce evidence; the longer continuation produces the accepted map.</div></section>
<section class="panel"><h2>Recorded balancing trajectory</h2><p>Maximum deviation is the primary objective; squared deviations break ties. The x-axis counts boundary moves after connectivity repair. The original run stops at 1,000; the new continuation starts from that same endpoint.</p><div class="controls"><button data-metric="max_absolute_deviation_people" aria-pressed="true">Worst deviation · people</button><button data-metric="squared_deviation_people" aria-pressed="false">Squared deviation · people²</button><button id="zoom-trace" aria-pressed="false">Focus on final 500 moves</button></div><div class="legend"><span><i class="swatch" style="background:#ffc65b"></i>Original 1,000 moves</span><span><i class="swatch" style="background:#25d3a8"></i>Cached continuation</span></div><svg id="trace" class="chart" role="img" aria-label="Measured population objective trajectory"></svg><p class="muted" id="chart-caption"></p></section>
<div class="split"><section class="panel"><h2>Correction runtime</h2><div class="table-wrap"><table><tbody id="pipeline-table"></tbody></table></div><p class="muted" id="memory"></p><p class="muted">The original pipeline includes a numerical solve and topology repair. This correction resumes saved assignments. Their total runtime ratio is not an isolated speedup measurement.</p></section><section class="panel"><h2>What the cache changes</h2><p>The cache identifies articulation points: blocks whose removal would disconnect their district. It invalidates both donor and recipient records after each transfer.</p><p>Candidate order, exact population objective, whole-block ownership and strict shared-edge rules stay the same. Zero-population blocks remain included. No water links or source-geometry changes are introduced.</p><p class="muted" id="bound-note"></p></section></div>
<section class="panel"><h2>Independent validation and preservation</h2><p id="validation-summary"></p><div class="table-wrap"><table><thead><tr><th>Map payload</th><th>Compressed size</th></tr></thead><tbody id="payload-table"></tbody></table></div><p class="muted" id="validation-note"></p><p class="muted">Historical runtime hashes are preserved separately from current code. The old K2 legacy optimizer warning remains unchanged; this work only corrects K3. Offline block maps remain separate from the app’s cached tract plans.</p></section><div class="footer">2020 Census residents · all source blocks retained · exact shared-edge connectivity · <a href="comparison.json">inspect measurements and provenance</a></div></main>
<script>const D=__DATA__;const el=id=>document.getElementById(id),fmt=(n,d=2)=>Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}),ns='http://www.w3.org/2000/svg';const C=D.correction,F=C.final,E=D.matched_equivalence;
el('headline').textContent=`The corrected map retains strict graph and polygon connectivity and reduces the worst population deviation from ${fmt(D.original.final.max_absolute_deviation_percent,6)}% to ${fmt(F.max_absolute_deviation_percent,8)}%. The original runs and diagnosis are preserved.`;el('new-deviation').textContent=fmt(F.max_absolute_deviation_people,3)+' people';el('new-percent').textContent=fmt(F.max_absolute_deviation_percent,8)+'% from ideal';el('speedup').textContent=fmt(E.measured_speedup,2)+'×';el('move-count').textContent=fmt(C.additional_moves,0);el('termination').textContent='Stopped at '+C.stop_reason.replaceAll('_',' ')+'; budget 10,000';
function row(target,values,highlight=false){const tr=document.createElement('tr');if(highlight)tr.className='highlight';for(const value of values){const td=document.createElement('td');td.textContent=value;tr.appendChild(td)}el(target).appendChild(tr)}
for(const[n,m,count,status,hi]of [['Original connected map',D.original.final,0,'Valid original; imbalanced',false],['Preserved diagnostic probe',D.diagnostic_probe.final,100,'Diagnostic; strict audit passed',false],['Cached continuation',F,C.additional_moves,'Validated corrected map',true]])row('population-table',[n,fmt(count,0),m.district_populations.map(x=>fmt(x,0)).join(' / '),fmt(m.max_absolute_deviation_people,3)+' people / '+fmt(m.max_absolute_deviation_percent,8)+'%',status],hi);
el('source-summary').textContent=`${fmt(D.source.block_count,0)} whole census blocks and ${fmt(D.source.resident_population,0)} residents retained. Every final district has one physical graph component and one valid unsimplified polygon. Source and original district-union coverage are unchanged.`;el('bound-note').textContent=F.integer_population_lower_bound_attained?`The endpoint reaches the integer-population arithmetic lower bound of ${fmt(F.integer_population_lower_bound_people,6)} person. District populations differ by ${fmt(F.total_range_people,0)} resident, at the floor/ceiling ${fmt(F.ideal_floor_population,0)} and ${fmt(F.ideal_ceil_population,0)}. This certifies the best possible maximum population balance for this total/count, not globally optimal compactness or other objectives.`:`The integer-population arithmetic lower bound is ${fmt(F.integer_population_lower_bound_people,6)} person and was not reached. A local optimum is local to the implemented moves; connectivity and population quality remain separate outcomes.`;
for(const r of D.runs.slice(0,2))row('timing-table',[r.stage==='traversal-100'?'Traversal':'Cached',fmt(r.rebalance_seconds,3)+' s',fmt(r.pipeline_seconds,3)+' s',fmt(r.peak_process_working_set_bytes/2**20,1)+' MiB'],r.stage==='cached-100');el('old-probe').textContent=`The earlier 100-move probe took ${fmt(D.diagnostic_probe.elapsed_seconds,3)} s with guard profiling enabled. It is historical context, not the denominator of the ${fmt(E.measured_speedup,2)}× fresh comparison.`;
for(const[n,v]of [['New balancing work',C.rebalance_seconds],['Polygon validation / map export',C.map_phase_seconds],['Original/new union comparison',C.coverage_phase_seconds],['Complete correction pipeline',C.pipeline_seconds]])row('pipeline-table',[n,fmt(v,3)+' s']);el('memory').textContent=`Correction peak: ${fmt(C.peak_process_working_set_bytes/2**20,1)} MiB. Original complete pipeline: ${fmt(D.original.pipeline_seconds/60,2)} min. Three-child parent elapsed: ${fmt(D.parent_elapsed_seconds,3)} s.`;
el('validation-summary').textContent=`Independently reconciled original DBF populations, ordered move/objective traces, final graph connectivity, full district geometries, every county feature and ${C.maps_validation.verified_compressed_artifact_count} compressed artifacts. All ${D.preservation.protected_file_count} protected original and diagnostic files are byte-identical. Recorded processes exited and the state54 lock was acquired during validation.`;for(const[label,key]of [['National outlines','national_state_only'],['State entry + detail index','state_entry_outlines_and_detail_index'],['All county detail shards','all_county_detail_shards'],['Largest county detail shard','largest_county_detail_shard']])row('payload-table',[label,fmt(C.map_payloads[key].gzip_bytes/1024,1)+' KiB gzip']);el('validation-note').textContent=D.validation_note+' Independent summary validation: '+fmt(D.summary_validation_seconds,3)+' s, separate from benchmark timings.';
let metric='max_absolute_deviation_people',tail=false;function svg(tag,attrs,parent){const n=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);parent.appendChild(n);return n}function draw(){const root=el('trace');root.replaceChildren();const W=1090,H=320,L=92,R=25,T=25,B=50;root.setAttribute('viewBox',`0 0 ${W} ${H}`);const xmax=D.trace.at(-1).moves,xmin=tail?Math.max(0,xmax-500):0,points=D.trace.filter(p=>p.moves>=xmin),ymax=Math.max(...points.map(p=>p[metric]))*1.04||1,x=n=>L+(n-xmin)/Math.max(1,xmax-xmin)*(W-L-R),y=n=>H-B-n/ymax*(H-B-T);for(let i=0;i<=4;i++){const v=ymax*i/4;svg('line',{x1:L,y1:y(v),x2:W-R,y2:y(v),class:'grid'},root);const t=svg('text',{x:L-10,y:y(v)+4,'text-anchor':'end',class:'chart-label'},root);t.textContent=v>=1e9?fmt(v/1e9,1)+'B':v>=1e6?fmt(v/1e6,1)+'M':fmt(v,v<10?2:0)}for(let i=0;i<=5;i++){const v=xmin+(xmax-xmin)*i/5,t=svg('text',{x:x(v),y:H-22,'text-anchor':'middle',class:'chart-label'},root);t.textContent=fmt(v,0)}const a=svg('text',{x:W-R,y:H-3,'text-anchor':'end',class:'chart-label'},root);a.textContent='Cumulative boundary moves after repair';for(const[subset,color]of [[points.filter(p=>p.moves<=1000),'#ffc65b'],[points.filter(p=>p.moves>=1000),'#25d3a8']])if(subset.length){svg('path',{d:subset.map((p,i)=>(i?'L':'M')+x(p.moves)+','+y(p[metric])).join(' '),stroke:color,'stroke-width':3,fill:'none'},root)}if(xmin<=1000&&1000<=xmax){svg('line',{x1:x(1000),y1:T,x2:x(1000),y2:H-B,stroke:'#b9c6da','stroke-dasharray':'5 5'},root);const label=svg('text',{x:x(1000)+7,y:T+14,class:'chart-label'},root);label.textContent='Original limit'}const p=points.at(-1),dot=svg('circle',{cx:x(p.moves),cy:y(p[metric]),r:5,fill:'#25d3a8'},root);svg('title',{},dot).textContent=fmt(p[metric],3)+' at move '+p.moves;el('chart-caption').textContent=(tail?'Final 500-move window. ':'Full recorded trajectory. ')+(metric==='max_absolute_deviation_people'?'Worst district deviation in people.':'Exact sum of squared district deviations, in people²; secondary lexicographic objective.');}
document.querySelectorAll('[data-metric]').forEach(b=>b.onclick=()=>{metric=b.dataset.metric;document.querySelectorAll('[data-metric]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));draw()});el('zoom-trace').onclick=()=>{tail=!tail;el('zoom-trace').setAttribute('aria-pressed',String(tail));draw()};draw();
</script></body></html>'''


def write_outputs(data: dict) -> None:
    if data.get("status") != "independently_validated" or data.get("correction", {}).get("accepted_map") is not True:
        raise ValueError("Refusing to publish an unvalidated or unaccepted correction")
    payload = json.dumps(data, indent=2, allow_nan=False) + "\n"
    script_payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    page = PAGE.replace("__DATA__", script_payload)
    prose = markdown(data)
    (OUTPUT / "comparison.json").write_text(payload, encoding="utf-8")
    (OUTPUT / "index.html").write_text(page, encoding="utf-8")
    REPORT.with_suffix(".json").write_text(payload, encoding="utf-8")
    REPORT.with_suffix(".md").write_text(prose, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-note", required=True,
                        help="Truthful summary-only test/review evidence; prelaunch results remain separate")
    args = parser.parse_args()
    if not args.validation_note.strip():
        raise ValueError("A nonempty validation note is required")
    with state_execution_lock("54"):
        data = collect(args.validation_note)
        write_outputs(data)
    print(json.dumps({"status": data["status"], "report": str(REPORT.with_suffix('.md')),
                      "comparison": URL, "final": data["correction"]["final"],
                      "measured_speedup": data["matched_equivalence"]["measured_speedup"]}))


if __name__ == "__main__":
    main()
