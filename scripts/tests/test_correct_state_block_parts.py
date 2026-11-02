"""Preserved-attempt correction workflow using real multipart geometry."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
import gzip
import json
from pathlib import Path
from typing import Any

import pytest
import shapefile
from shapely.geometry import MultiPolygon, Polygon, box, mapping
from shapely.geometry.polygon import orient

import districting
from districting import Unit, algorithm
from scripts import benchmark_state_blocks as benchmark
from scripts import correct_state_block_parts as correction
from scripts.district_block_part_graph import build_shared_edge_part_graph
from scripts.state_block_map_export import StateMapValidationError, export_state_block_maps


def fail_if_called(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("Numerical solving/export must not run on this path.")


@dataclass
class FailedRun:
    original: Path
    output: Path
    geoids: list[str]
    source: Path
    archive: Path


def install_failed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, moved_population: int = 0,
) -> FailedRun:
    """Three whole blocks, four parts: one shared node hides an actual island.

    The middle block has two separated squares on either side of the receiving
    block. Its lower square touches the donor. Transferring the whole middle
    block removes the donor island and joins both parts to the recipient.
    """
    shapes: list[Polygon | MultiPolygon] = [
        box(-100, 38, -99.99, 38.01),
        MultiPolygon([
            box(-99.99, 38, -99.98, 38.01),
            box(-99.99, 38.02, -99.98, 38.03),
        ]),
        box(-100, 38.01, -99.98, 38.02),
    ]
    source = tmp_path / "blocks.shp"
    geoids = [f"01001000100{index:04d}" for index in range(3)]
    populations = dict(zip(geoids, (10, moved_population, 10), strict=True))
    with shapefile.Writer(str(source)) as writer:
        writer.field("GEOID20", "C", size=15)
        writer.field("COUNTYFP20", "C", size=3)
        writer.field("POP20", "N", size=10)
        for geoid, geometry in zip(geoids, shapes, strict=True):
            parts = list(geometry.geoms) if isinstance(geometry, MultiPolygon) else [geometry]
            writer.poly([list(orient(part, sign=-1).exterior.coords) for part in parts])
            writer.record(geoid, "001", populations[geoid])
    original = tmp_path / "failed-original"
    original.mkdir()
    assignments = dict(zip(geoids, (0, 0, 1), strict=True))
    # Retain the same compressed failed outlines the real exporter preserves.
    with pytest.raises(StateMapValidationError, match="2 polygon components"):
        export_state_block_maps(
            source, assignments, populations, original / "maps",
            state_fips="01", state_name="Alabama", n_districts=2,
        )
    archive = tmp_path / "source.zip"
    archive.write_bytes(b"verified archive fixture; source acquisition is mocked")
    source_metadata = {"archive_path": str(archive), "archive_sha256": correction.sha256(archive)}
    checkpoint = original / "solver-result.json"
    checkpoint.write_text(json.dumps({"plan_kind": "final", "assignments": assignments}), encoding="utf-8")
    prior = {
        "status": "failed", "state": "Alabama", "state_fips": "01", "district_count": 2,
        "house_sizes": [1000], "source": source_metadata,
        "final_plan": {"district_populations": [10 + moved_population, 10]},
        "artifact_sha256": {"solver-result.json": correction.sha256(checkpoint)},
        "timed_pipeline_wall_seconds": 1234.5, "peak_process_working_set_bytes": 123456,
    }
    (original / "benchmark.json").write_text(json.dumps(prior), encoding="utf-8")
    (original / "failed-attempt.log").write_text("Strict polygon validation failed.\n", encoding="utf-8")
    units = [Unit(geoid, (float(index), 0.0), populations[geoid]) for index, geoid in enumerate(geoids)]
    monkeypatch.setattr(correction, "prepare_source", lambda *args: (source, dict(source_metadata)))
    monkeypatch.setattr(correction, "load_units", lambda *args: (
        units, populations, {"projection": {"lon0": -100.0, "lat0": 38.0}},
    ))

    def part_graph(*args: Any, **kwargs: Any) -> Any:
        graph, metadata = build_shared_edge_part_graph(source, geoids)
        return graph, metadata, {"cache_hit": False, "fixture": True}

    monkeypatch.setattr(correction, "load_or_build_shared_edge_part_graph", part_graph)
    monkeypatch.setattr(correction, "state_execution_lock", lambda *args: nullcontext())
    # A correction may never invoke the numerical solver through any existing
    # import path, even if a future orchestration refactor tries to resume it.
    monkeypatch.setattr(districting, "balanced_power_diagram", fail_if_called)
    monkeypatch.setattr(algorithm, "balanced_power_diagram", fail_if_called)
    monkeypatch.setattr(benchmark, "balanced_power_diagram", fail_if_called)
    monkeypatch.setattr(benchmark, "run_benchmark", fail_if_called)
    return FailedRun(original, tmp_path / "corrected-v1", geoids, source, archive)


@pytest.mark.parametrize("relationship", ["same", "nested", "ancestor"])
def test_rejects_destination_inside_or_above_original(tmp_path: Path, relationship: str) -> None:
    original = tmp_path / "original"
    original.mkdir()
    sentinel = original / "benchmark.json"
    sentinel.write_text("preserved", encoding="utf-8")
    output = {"same": original, "nested": original / "correction", "ancestor": tmp_path}[relationship]
    with pytest.raises(ValueError, match="separate"):
        correction.correct_run(original, output)
    assert sentinel.read_text(encoding="utf-8") == "preserved"
    assert list(original.iterdir()) == [sentinel]


def test_rejects_nonempty_destination_without_touching_prior_attempt(tmp_path: Path) -> None:
    original, output = tmp_path / "original", tmp_path / "corrected"
    original.mkdir()
    output.mkdir()
    sentinel = output / "attempt.log"
    sentinel.write_bytes(b"prior correction evidence")
    with pytest.raises(ValueError, match="new or empty"):
        correction.correct_run(original, output)
    assert sentinel.read_bytes() == b"prior correction evidence"
    assert list(output.iterdir()) == [sentinel]


def test_corrects_saved_multipart_plan_without_solving_or_mutating_failed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = install_failed_run(tmp_path, monkeypatch)
    before = correction.file_inventory(fixture.original)
    result = correction.correct_run(fixture.original, fixture.output)
    assert correction.file_inventory(fixture.original) == before
    assert result["status"] == "complete"
    assert result["numerical_solver_rerun"] is False
    assert result["full_end_to_end_run"] is False
    assert result["original_files_byte_identical"] is True
    assert result["original_run"]["timed_pipeline_wall_seconds"] == 1234.5
    assert result["original_plan"]["all_districts_shared_edge_connected"] is True
    assert result["original_plan"]["shared_edge_part_components"] == [2, 1]
    assert result["final_plan"]["shared_edge_part_components"] == [1, 1]
    assert result["final_plan"]["district_populations"] == [10, 10]
    assert result["population_moved"] == 0
    assert result["whole_blocks_moved"] == 1
    assert result["district_populations_unchanged"] is True
    assert result["maps"]["strict_validation"] == {"passed": True, "issues": []}
    assert result["coverage_validation"]["exact_original_union_preserved"] is True
    assert result["coverage_validation"]["all_district_interiors_disjoint"] is True
    checkpoint = json.loads((fixture.output / "solver-result.json").read_text(encoding="utf-8"))
    assert checkpoint["assignments"] == dict(zip(fixture.geoids, (0, 1, 1), strict=True))
    assert checkpoint["provenance"]["original_assignments_sha256"] == before["solver-result.json"]
    moves = json.loads((fixture.output / "move-audit.json").read_text(encoding="utf-8"))
    assert moves["rebalance_moves"] == []
    assert moves["repair_moves"][0]["geoids"] == [fixture.geoids[1]]
    assert moves["repair_moves"][0]["population"] == 0
    assert (fixture.output / "index.html").is_file()
    assert json.loads((fixture.original / "benchmark.json").read_text(encoding="utf-8"))["status"] == "failed"
    for name, digest in result["artifact_sha256"].items():
        assert correction.sha256(fixture.output / name) == digest


def test_population_changing_geometry_repair_is_not_exported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = install_failed_run(tmp_path, monkeypatch, moved_population=3)
    before = correction.file_inventory(fixture.original)
    monkeypatch.setattr(correction, "export_state_block_maps", fail_if_called)
    with pytest.raises(ValueError, match="preserve each district population"):
        correction.correct_run(fixture.original, fixture.output)
    report = json.loads((fixture.output / "benchmark.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["failed_phase"] == "audit_corrected_assignments"
    assert report["final_plan"]["shared_edge_part_components"] == [1, 1]
    assert report["final_plan"]["district_populations"] == [10, 13]
    assert not (fixture.output / "solver-result.json").exists()
    assert not (fixture.output / "maps").exists()
    assert correction.file_inventory(fixture.original) == before


@pytest.mark.parametrize("changed", ["checkpoint", "source_archive"])
def test_changed_source_evidence_stops_before_correction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str,
) -> None:
    fixture = install_failed_run(tmp_path, monkeypatch)
    artifact = fixture.original / "solver-result.json" if changed == "checkpoint" else fixture.archive
    artifact.write_bytes(artifact.read_bytes() + b" ")
    before = correction.file_inventory(fixture.original)
    monkeypatch.setattr(correction, "prepare_source", fail_if_called)
    with pytest.raises(ValueError, match="digest mismatch|missing or changed"):
        correction.correct_run(fixture.original, fixture.output)
    assert not fixture.output.exists()
    assert correction.file_inventory(fixture.original) == before


def write_full_map(directory: Path, geometries: list[Polygon]) -> None:
    directory.mkdir()
    raw = json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"district_id": index}, "geometry": mapping(geometry)}
        for index, geometry in enumerate(geometries)
    ]}).encode()
    (directory / "districts-full.geojson.gz").write_bytes(gzip.compress(raw))


def test_coverage_verification_allows_new_partition_of_exact_same_area(tmp_path: Path) -> None:
    old, new = tmp_path / "old", tmp_path / "new"
    write_full_map(old, [box(0, 0, 1, 2), box(1, 0, 2, 2)])
    write_full_map(new, [box(0, 0, 2, 1), box(0, 1, 2, 2)])
    result = correction.verify_unchanged_coverage(old, new)
    assert result["symmetric_difference_empty"] is True
    assert result["all_district_interiors_disjoint"] is True


@pytest.mark.parametrize("defect", ["equal_area_shift", "same_union_overlap"])
def test_coverage_verification_rejects_shape_change_or_overlapping_interiors(
    tmp_path: Path, defect: str,
) -> None:
    old, new = tmp_path / "old", tmp_path / "new"
    write_full_map(old, [box(0, 0, 1, 2), box(1, 0, 2, 2)])
    geometries = (
        [box(1, 0, 2, 2), box(2, 0, 3, 2)] if defect == "equal_area_shift"
        else [box(0, 0, 1.5, 2), box(1, 0, 2, 2)]
    )
    write_full_map(new, geometries)
    with pytest.raises(ValueError, match="changed coverage or contain overlapping interiors"):
        correction.verify_unchanged_coverage(old, new)
