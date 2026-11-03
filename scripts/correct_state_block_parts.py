"""Correct saved block assignments using polygon-part topology in a new directory.

This is a separately measured postprocessing run, never a resume or a new power
diagram solve. Original failed artifacts are hashed before/after and untouched.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import html
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from districting.part_connectivity import PartGraph, repair_part_connectivity
from scripts.benchmark_kansas_anchors import stage_metrics
from scripts.benchmark_kansas_blocks import Measurements, process_memory, sha256
from scripts.benchmark_state_blocks import CODE_PATHS, add_part_audit, verify_saved_artifact
from scripts.district_block_part_graph import load_or_build_shared_edge_part_graph
from scripts.district_block_sources import load_units, prepare_source
from scripts.state_block_execution_lock import state_execution_lock
from scripts.state_block_map_export import export_state_block_maps


def write_json(path: Path, data: Any) -> None:
    """Bounded retries for Windows sharing conflicts; no ambiguous relaunch."""
    temporary = path.with_suffix(path.suffix + ".partial")
    text = json.dumps(data, indent=2, allow_nan=False) + "\n"
    for attempt in range(8):
        try:
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(min(0.05 * 2**attempt, 0.5))


def file_inventory(directory: Path) -> dict[str, str]:
    return {path.relative_to(directory).as_posix(): sha256(path)
            for path in sorted(directory.rglob("*")) if path.is_file()}


def validate_destination(original: Path, output: Path) -> None:
    if output.is_relative_to(original) or original.is_relative_to(output):
        raise ValueError("Correction output must be separate from the original run tree.")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Correction output must be new or empty; prior attempts are preserved.")


def block_adjacency(graph: PartGraph, block_count: int) -> tuple[tuple[int, ...], ...]:
    """Collapse real part edges for the legacy, weaker independent block audit."""
    neighbors: list[set[int]] = [set() for _ in range(block_count)]
    for part, adjacent in enumerate(graph.adjacency):
        owner = graph.part_to_unit[part]
        for other in adjacent:
            target = graph.part_to_unit[other]
            if owner != target:
                neighbors[owner].add(target)
    return tuple(tuple(sorted(row)) for row in neighbors)


def verify_unchanged_coverage(original_maps: Path, corrected_maps: Path) -> dict[str, Any]:
    from shapely import union_all
    from shapely.geometry import shape

    def read(root: Path) -> list[Any]:
        data = json.loads(gzip.decompress((root / "districts-full.geojson.gz").read_bytes()))
        return [shape(feature["geometry"]) for feature in data["features"]]

    old, new = read(original_maps), read(corrected_maps)
    old_union, new_union = union_all(old), union_all(new)
    difference = old_union.symmetric_difference(new_union)
    # Pairwise topology, rather than subtraction of rounded floating areas.
    disjoint = all(not new[left].relate_pattern(new[right], "T********")
                   for left in range(len(new)) for right in range(left + 1, len(new)))
    if not difference.is_empty or not disjoint:
        raise ValueError("Corrected full outlines changed coverage or contain overlapping interiors.")
    return {"exact_original_union_preserved": True, "symmetric_difference_empty": True,
            "all_district_interiors_disjoint": True, "source_coordinates_unchanged": True}


def write_viewer(output: Path, report: dict[str, Any]) -> None:
    template = (ROOT / "scripts/assets/state-block-viewer.html").read_text(encoding="utf-8")
    projection = report["input"]["projection"]
    replacements = {
        "__STATE_NAME__": html.escape(report["state"]),
        "__DISTRICT_COUNT__": str(report["district_count"]),
        "__RESULT_SUMMARY__": (
            f'CORRECTED · {report["district_count"]} districts pass polygon-part graph and strict polygon validation. '
            f'{report["whole_blocks_moved"]} whole block moved; {report["population_moved"]} residents reassigned. '
            'Original failed run preserved.'),
        "__ANCHOR_NAVIGATION__": '<a href="../../../">Correction results</a> <a href="../../../../../diagnostics/">Geometry diagnosis</a>',
        "__LON0__": str(projection["lon0"]), "__LAT0__": str(projection["lat0"]),
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    (output / "index.html").write_text(template, encoding="utf-8")


def correct_run(original: Path, output: Path) -> dict[str, Any]:
    original, output = original.resolve(), output.resolve()
    validate_destination(original, output)
    prior = json.loads((original / "benchmark.json").read_text(encoding="utf-8"))
    if prior["status"] != "failed":
        raise ValueError("This correction entry point requires a preserved failed run.")
    fips, count = prior["state_fips"], prior["district_count"]
    with state_execution_lock(fips):
        return _correct_locked(original, output, prior, count)


def _correct_locked(original: Path, output: Path, prior: dict[str, Any], count: int) -> dict[str, Any]:
    fips = prior["state_fips"]
    before = file_inventory(original)
    checkpoint = original / "solver-result.json"
    verify_saved_artifact(prior, checkpoint, original)
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    if saved.get("plan_kind") != "final":
        raise ValueError("Correction requires the saved final whole-block assignments.")
    archive = Path(prior["source"]["archive_path"])
    if not archive.is_file() or sha256(archive) != prior["source"]["archive_sha256"]:
        raise ValueError("Original verified source archive is missing or changed.")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "original-file-inventory.json", before)
    measurements = Measurements()
    started = time.perf_counter()
    report: dict[str, Any] = {
        "status": "running", "run_kind": "part_connectivity_correction", "state": prior["state"],
        "state_fips": fips, "district_count": count, "house_sizes": prior["house_sizes"],
        "source_year": 2020, "unit": "census_block", "started_at": datetime.now(timezone.utc).isoformat(),
        "code_sha256": {name: sha256(ROOT / name) for name in (*CODE_PATHS, "scripts/correct_state_block_parts.py")},
        "original_run": {"path": str(original), "status": prior["status"],
                         "benchmark_sha256": before["benchmark.json"], "assignments_sha256": before["solver-result.json"],
                         "timed_pipeline_wall_seconds": prior.get("timed_pipeline_wall_seconds"),
                         "peak_process_working_set_bytes": prior.get("peak_process_working_set_bytes")},
        "numerical_solver_rerun": False, "full_end_to_end_run": False,
        "measurement_notes": ["Timing covers correction, new part graph, independent audits and regenerated maps only.",
                              "Original solver runtime and failed attempt remain separate; this is not a full solver benchmark.",
                              "Whole blocks remain indivisible; no artificial edges, snapping, or buffering.",
                              "Zero-population whole-block moves may repair topology; population balance is independently checked."],
        "artifacts": {}, "artifact_sha256": {},
    }
    write_json(output / "benchmark.json", report)
    try:
        source, report["source"] = prepare_source(fips, archive.parent, measurements)
        if report["source"]["archive_sha256"] != prior["source"]["archive_sha256"]:
            raise ValueError("Prepared source differs from the original failed run.")
        with measurements.phase("load_and_validate_blocks"):
            units, population_map, report["input"] = load_units(source, fips)
            geoids = [unit.geoid for unit in units]
            populations = [unit.population for unit in units]
            if set(saved["assignments"]) != set(geoids):
                raise ValueError("Original assignments do not match the exact source universe.")
            labels = tuple(saved["assignments"][geoid] for geoid in geoids)
            del units
        with measurements.phase("load_or_build_part_graph"):
            graph, report["part_graph"], report["part_graph_cache"] = load_or_build_shared_edge_part_graph(
                source, geoids, source_sha256=report["source"]["archive_sha256"],
                cache_dir=ROOT / f".cache/state-block-benchmark/graph-cache/{fips}",
            )
            if report["part_graph"]["interior_overlap_pair_count"]:
                raise ValueError("Source parts overlap; correction cannot change source geography.")
            adjacency = block_adjacency(graph, len(geoids))
        def audit(assignments: Any) -> dict[str, Any]:
            result = stage_metrics(assignments, populations, adjacency, geoids, n_districts=count,
                                   expected_population=sum(populations), expected_blocks=len(geoids))
            add_part_audit(result, graph, assignments, count)
            return result
        with measurements.phase("audit_original_part_connectivity"):
            report["original_plan"] = audit(labels)
            if report["original_plan"]["district_populations"] != prior["final_plan"]["district_populations"]:
                raise ValueError("Original population audit differs from preserved report.")
        with measurements.phase("repair_part_connectivity"):
            corrected = repair_part_connectivity(graph, labels, populations, n_districts=count)
        with measurements.phase("audit_corrected_assignments"):
            report["final_plan"] = audit(corrected.assignments)
            if not report["final_plan"]["all_districts_part_connected"] or not report["final_plan"]["all_districts_shared_edge_connected"]:
                raise ValueError("Corrected plan failed a connectivity audit.")
            unchanged = report["final_plan"]["district_populations"] == report["original_plan"]["district_populations"]
            if not unchanged:
                raise ValueError("This geometry-only correction must preserve each district population.")
            report["district_populations_unchanged"] = unchanged
        assignments = dict(zip(geoids, corrected.assignments, strict=True))
        moves = [{**asdict(move), "geoids": [geoids[index] for index in move.units], "reason": "polygon_part_connectivity"}
                 for move in corrected.moves]
        report["whole_blocks_moved"] = sum(before != after for before, after in zip(labels, corrected.assignments, strict=True))
        report["population_moved"] = sum(populations[i] for i in range(len(labels)) if labels[i] != corrected.assignments[i])
        provenance = {"source_sha256": report["source"]["archive_sha256"], "code_sha256": report["code_sha256"],
                      "original_assignments_sha256": before["solver-result.json"], "original_benchmark_sha256": before["benchmark.json"]}
        write_json(output / "solver-result.json", {"plan_kind": "corrected_final", "provenance": provenance,
                   "assignments": assignments, "note": "Saved solver assignments plus audited whole-block topology moves; solver was not rerun."})
        write_json(output / "move-audit.json", {"provenance": provenance, "repair_moves": moves, "rebalance_moves": []})
        del graph, adjacency
        with measurements.phase("strict_geometry_validation_and_map_export"):
            report["maps"] = export_state_block_maps(source, assignments, population_map, output / "maps",
                state_fips=fips, state_name=prior["state"], n_districts=count)
        with measurements.phase("verify_exact_coverage_preserved"):
            report["coverage_validation"] = verify_unchanged_coverage(original / "maps", output / "maps")
        report["artifacts"] = {"final_checkpoint": "solver-result.json", "move_audit": "move-audit.json", "map_manifest": "maps/map-manifest.json"}
        for name in (*report["artifacts"].values(), "original-file-inventory.json"):
            report["artifact_sha256"][name] = sha256(output / name)
        with measurements.phase("verify_original_run_unchanged"):
            report["original_files_byte_identical"] = file_inventory(original) == before
            if not report["original_files_byte_identical"]:
                raise ValueError("Original run changed during correction; review before using outputs.")
        report["status"] = "complete"
        write_viewer(output, report)
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        report["failed_phase"] = measurements.active
        raise
    finally:
        measurements.close()
        if "original_files_byte_identical" not in report:
            try:
                report["original_files_byte_identical"] = file_inventory(original) == before
            except OSError as preservation_error:
                report["original_preservation_verification_error"] = str(preservation_error)
        report["phases"] = measurements.phases
        report["timed_pipeline_wall_seconds"] = time.perf_counter() - started
        report["peak_process_working_set_bytes"] = process_memory()[1]
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "benchmark.json", report)
        print(f'Correction {report["status"]}: {output}', flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    correct_run(args.original, args.output)
