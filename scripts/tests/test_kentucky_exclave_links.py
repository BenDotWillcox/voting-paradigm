"""Recorded Kentucky exception provenance, whole-block population, and geometry."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import shapefile
from shapely.geometry import box
from shapely.geometry.polygon import orient

from districting.part_connectivity import PartGraph
from scripts import kentucky_exclave_links as policy
from scripts.hawaii_population_links import _great_circle_m


def _fixture(tmp_path: Path):
    source = tmp_path / "blocks.shp"
    geoids = tuple(f"21001000100{i:04d}" for i in range(14))
    populations = (100,) * 13 + (1,)
    # Reuse exact grid coordinates so contiguous source boundaries match bitwise.
    xs = [-86 + i * .01 for i in range(17)]
    with shapefile.Writer(str(source)) as writer:
        writer.field("GEOID20", "C", size=15)
        writer.field("POP20", "N", size=10)
        for i, geoid in enumerate(geoids):
            index = i if i < 13 else 15
            writer.poly([list(orient(box(xs[index], 38, xs[index + 1], 38.01), sign=-1).exterior.coords)])
            writer.record(geoid, populations[i])
    rows = [tuple(j for j in (i - 1, i + 1) if 0 <= j < 13) for i in range(13)] + [()]
    graph = PartGraph(tuple(rows), tuple(range(14)))
    diagnostic = tmp_path / "diagnostic"
    diagnostic.mkdir()
    archive = tmp_path / "source.zip"
    archive.write_bytes(b"synthetic source archive for provenance validation")
    area_archive = tmp_path / "area.zip"
    area_archive.write_bytes(b"synthetic area-water evidence")
    mo_archive = tmp_path / "missouri.zip"
    mo_archive.write_bytes(b"synthetic Missouri context")
    endpoints = [
        {"geoid": geoids[12], "part_node": 12, "part_index": 0, "coordinate": [xs[13], 38.005]},
        {"geoid": geoids[13], "part_node": 13, "part_index": 0, "coordinate": [xs[15], 38.005]},
    ]
    candidate = {"id": "ky-candidate-00-01", "component_ids": [0, 1], "endpoints": endpoints,
                 "distance_m": _great_circle_m(*(e["coordinate"] for e in endpoints)),
                 "classification": "positive_gap", "eligible_positive_gap": True,
                 "source_boundaries_intersect": False, "intervening_component_ids": [],
                 "endpoint_component_interior_crossings": []}
    diagnosis = {"state_fips": "21", "physical_component_count": 2, "blocks_spanning_components": [],
                 "status": "diagnostic_complete_no_district_plans_generated", "part_count": 14, "block_count": 14,
                 "source": {"archive_path": str(archive), "archive_sha256": policy._sha256(archive),
                            "extracted_file_sha256": {source.with_suffix(s).name: policy._sha256(source.with_suffix(s))
                                                      for s in (".shp", ".shx", ".dbf")}},
                 "links": [candidate], "total_population": sum(populations),
                 "components": [{"population": 1300, "part_count": 13, "block_count": 13},
                                {"population": 1, "part_count": 1, "block_count": 1}]}
    (diagnostic / "diagnosis.json").write_text(json.dumps(diagnosis))
    (diagnostic / "candidate-links.json").write_text(json.dumps([candidate]))
    area = {"candidate_file_sha256": policy._sha256(diagnostic / "candidate-links.json"),
            "candidate_id": candidate["id"], "candidate_endpoints": [e["coordinate"] for e in endpoints],
            "water_only_under_2020_census_area_water": False, "mapped_water_length_m": 200.0,
            "outside_mapped_water_length_m": candidate["distance_m"] - 200,
            "source_archive": str(area_archive), "source_archive_sha256": policy._sha256(area_archive),
            "measurement": "synthetic test segments", "source_url": "https://example.test/area.zip"}
    (diagnostic / "area-water-audit.json").write_text(json.dumps(area))
    context = {"candidate_endpoints": area["candidate_endpoints"], "coverage_fraction": 1.0,
               "source_archive": str(mo_archive), "source_archive_sha256": policy._sha256(mo_archive)}
    (diagnostic / "missouri-connection-context.json").write_text(json.dumps(context))
    return source, geoids, populations, graph, diagnostic


def _build(args, k=6):
    return policy.build_kentucky_connections(*args[:4], district_count=k, diagnostic_dir=args[4])


@pytest.mark.parametrize("k", [6, 8, 9, 14])
def test_exclave_attachment_preserves_source_and_records_land_crossing(tmp_path: Path, k: int):
    args = _fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    graph, records, audit = _build(args, k)
    assert graph.part_to_unit == args[3].part_to_unit
    assert graph.adjacency[12] == (11, 13)
    assert graph.adjacency[13] == (12,)
    assert args[3].adjacency[13] == ()
    assert len(records) == 1
    assert records[0]["kind"] == "recorded-exclave-connection"
    assert records[0]["geographic_context"]["water_only"] is False
    assert records[0]["geographic_context"]["crossed_state"] == "Missouri"
    assert audit["physical_component_count"] == 2
    assert audit["augmented_component_count"] == 1
    assert audit["synthetic_edge_count"] == 1
    assert audit["source_population"] == 1301
    assert audit["population_selection"]["eligible_root_component_ids"] == [0]
    assert before == {p: p.read_bytes() for p in before}


def test_population_redistribution_cannot_hide_behind_unchanged_component_total(tmp_path: Path):
    args = list(_fixture(tmp_path))
    args[2] = (99, 101) + args[2][2:]
    with pytest.raises(ValueError, match="whole-block population differs"):
        _build(args)


def test_changed_source_archive_fails_before_graph_use(tmp_path: Path):
    args = _fixture(tmp_path)
    (tmp_path / "source.zip").write_bytes(b"changed")
    with pytest.raises(ValueError, match="source archive differs"):
        _build(args)


def test_omitted_physical_edge_is_not_replaced_by_exclave_policy(tmp_path: Path):
    args = list(_fixture(tmp_path))
    rows = list(args[3].adjacency)
    rows[0], rows[1] = (), (2,)
    args[3] = PartGraph(tuple(rows), args[3].part_to_unit)
    with pytest.raises(ValueError, match="exactly match source shared-edge geometry"):
        _build(args)


def test_candidate_tampering_fails_cross_evidence_check(tmp_path: Path):
    args = _fixture(tmp_path)
    path = args[4] / "candidate-links.json"
    changed = json.loads(path.read_text())
    changed[0]["endpoints"][0]["part_node"] = 11
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="candidate evidence disagrees"):
        _build(args)


def test_point_contact_cannot_be_relabelled_exclave_gap(tmp_path: Path):
    args = _fixture(tmp_path)
    path = args[4] / "diagnosis.json"
    diagnosis = json.loads(path.read_text())
    diagnosis["links"][0]["source_boundaries_intersect"] = True
    path.write_text(json.dumps(diagnosis))
    with pytest.raises(ValueError, match="eligible positive gap"):
        _build(args)


def test_water_only_relabelling_is_rejected(tmp_path: Path):
    args = _fixture(tmp_path)
    path = args[4] / "area-water-audit.json"
    area = json.loads(path.read_text())
    area["water_only_under_2020_census_area_water"] = True
    path.write_text(json.dumps(area))
    with pytest.raises(ValueError, match="cross-Missouri land/water"):
        _build(args)


@pytest.mark.parametrize("k", [True, 2, 11037])
def test_only_authorized_kentucky_anchor_counts_are_supported(tmp_path: Path, k):
    with pytest.raises(ValueError, match="6, 8, 9, and 14"):
        _build(_fixture(tmp_path), k)
