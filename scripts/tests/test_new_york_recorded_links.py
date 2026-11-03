"""Exact-source mixed New York exceptions, provenance, and classification."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import shapefile
from shapely.geometry import box
from shapely.geometry.polygon import orient

from districting.part_connectivity import PartGraph
from scripts import new_york_recorded_links as policy
from scripts.hawaii_population_links import _great_circle_m


def _repin(diagnostic: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policy, "PINNED_EVIDENCE_SHA256", {
        name: policy._sha256(diagnostic / name) for name in policy.PINNED_EVIDENCE_SHA256
    })


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "blocks.shp"
    geoids = tuple(f"36001000100{i:04d}" for i in range(61))
    pops = (100,) * 59 + (0, 0)
    xs = [-75 + i * .01 for i in range(63)]
    geoms = [box(xs[i], 40, xs[i + 1], 40.01) for i in range(59)]
    geoms += [box(xs[60], 40, xs[61], 40.01), box(xs[58], 40.02, xs[59], 40.03)]
    with shapefile.Writer(str(source)) as writer:
        writer.field("GEOID20", "C", size=15)
        writer.field("POP20", "N", size=10)
        for g, geoid, pop in zip(geoms, geoids, pops, strict=True):
            writer.poly([list(orient(g, sign=-1).exterior.coords)])
            writer.record(geoid, pop)
    rows = [tuple(j for j in (i - 1, i + 1) if 0 <= j < 59) for i in range(59)] + [(), ()]
    graph = PartGraph(tuple(rows), tuple(range(61)))
    diagnostic = tmp_path / "diagnostic"
    diagnostic.mkdir()
    archive = tmp_path / "source.zip"
    archive.write_bytes(b"synthetic verified source")
    context_archive = tmp_path / "context.zip"
    context_archive.write_bytes(b"synthetic verified context")
    def candidate(pair, nodes, coordinates):
        return {"id": f"ny-candidate-{pair[0]:02d}-{pair[1]:02d}", "component_ids": list(pair),
                "endpoints": [{"geoid": geoids[node], "part_node": node, "part_index": 0, "coordinate": coordinate}
                              for node, coordinate in zip(nodes, coordinates, strict=True)],
                "distance_m": _great_circle_m(*coordinates), "classification": "positive_gap", "eligible_positive_gap": True,
                "source_boundaries_intersect": False, "intervening_component_ids": [], "endpoint_component_interior_crossings": []}
    midpoint = (xs[58] + xs[59]) / 2
    candidates = [candidate((0, 1), (58, 59), [[xs[59], 40.005], [xs[60], 40.005]]),
                  candidate((0, 2), (58, 60), [[midpoint, 40.01], [midpoint, 40.02]]),
                  candidate((1, 2), (59, 60), [[xs[60], 40.01], [xs[59], 40.02]])]
    diagnosis = {"state_fips": "36", "physical_component_count": 3, "blocks_spanning_components": [],
                 "status": "diagnostic_complete_no_district_plans_generated", "part_count": 61, "block_count": 61,
                 "source": {"archive_path": str(archive), "archive_sha256": policy._sha256(archive),
                            "extracted_file_sha256": {source.with_suffix(s).name: policy._sha256(source.with_suffix(s)) for s in (".shp", ".shx", ".dbf")}},
                 "links": candidates, "total_population": 5900,
                 "components": [{"population": 5900, "part_count": 59, "block_count": 59},
                                {"population": 0, "part_count": 1, "block_count": 1},
                                {"population": 0, "part_count": 1, "block_count": 1}]}
    (diagnostic / "diagnosis.json").write_text(json.dumps(diagnosis))
    (diagnostic / "candidate-links.json").write_text(json.dumps(candidates))
    surfaces = []
    for index, row in enumerate(candidates):
        water_only = index == 0
        land = 0.0 if water_only else 25.0
        surfaces.append({"candidate_id": row["id"], "candidate_endpoints": [e["coordinate"] for e in row["endpoints"]],
                         "component_ids": row["component_ids"], "distance_m": row["distance_m"],
                         "new_jersey_interior_coverage_fraction": 1.0, "water_only_under_2020_census_area_water": water_only,
                         "classification": "mapped_water_only" if water_only else "crosses_mapped_water_and_new_jersey_land",
                         "candidate_planar_length_m": row["distance_m"], "mapped_water_length_m": row["distance_m"] - land,
                         "outside_mapped_water_length_m": land,
                         "crossed_new_jersey_blocks": [{"geoid": "340179801001017", "land_area_m2": 0, "water_area_m2": 1000}] +
                         ([] if water_only else [{"geoid": "340179801001001", "land_area_m2": 1000, "water_area_m2": 0}])})
    context = {"links": surfaces, "candidate_file_sha256": policy._sha256(diagnostic / "candidate-links.json"),
               "diagnosis_file_sha256": policy._sha256(diagnostic / "diagnosis.json"), "status": "complete",
               "source_geometry_modified": False, "source_year": 2020,
               "source_archive_sha256": {str(context_archive): policy._sha256(context_archive)}, "measurement": "synthetic exact crossing audit"}
    (diagnostic / "geography-context.json").write_text(json.dumps(context))
    _repin(diagnostic, monkeypatch)
    return source, geoids, pops, graph, diagnostic


def _build(args, k=26):
    return policy.build_new_york_connections(*args[:4], district_count=k, diagnostic_dir=args[4])


@pytest.mark.parametrize("k", [26, 35, 42, 61])
def test_mixed_links_preserve_physical_graph_populations_and_evidence(tmp_path, monkeypatch, k):
    args = _fixture(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    augmented, records, audit = _build(args, k)
    assert augmented.part_to_unit == args[3].part_to_unit
    assert args[3].adjacency[59:] == ((), ())
    assert augmented.adjacency[58] == (57, 59, 60)
    assert [r["kind"] for r in records] == ["recorded-water-connection", "recorded-exclave-connection"]
    assert [r["geographic_context"]["water_only"] for r in records] == [True, False]
    assert records[1]["geographic_context"]["mapped_land_length_m"] == 25
    assert audit["physical_component_count"] == 3
    assert audit["augmented_component_count"] == 1
    assert audit["synthetic_edge_count"] == 2
    assert audit["source_population"] == 5900
    assert audit["population_selection"]["eligible_root_component_ids"] == [0]
    assert before == {p: p.read_bytes() for p in before}


def test_changed_crossing_audit_fails_pinned_hash(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    path = args[4] / "geography-context.json"
    data = json.loads(path.read_text())
    data["links"][1]["water_only_under_2020_census_area_water"] = True
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="evidence hash changed"):
        _build(args)


@pytest.mark.parametrize(("field", "value"), [("water_only_under_2020_census_area_water", True),
                                                ("classification", "mapped_water_only"),
                                                ("outside_mapped_water_length_m", 0.0)])
def test_ellis_exclave_cannot_be_reclassified_as_water(tmp_path, monkeypatch, field, value):
    args = _fixture(tmp_path, monkeypatch)
    path = args[4] / "geography-context.json"
    data = json.loads(path.read_text())
    data["links"][1][field] = value
    path.write_text(json.dumps(data))
    _repin(args[4], monkeypatch)
    with pytest.raises(ValueError, match="classification"):
        _build(args)


def test_population_redistribution_cannot_hide_in_component_total(tmp_path, monkeypatch):
    args = list(_fixture(tmp_path, monkeypatch))
    args[2] = (99, 101) + args[2][2:]
    with pytest.raises(ValueError, match="whole-block population differs"):
        _build(args)


def test_omitted_physical_edge_is_not_replaced_by_exception(tmp_path, monkeypatch):
    args = list(_fixture(tmp_path, monkeypatch))
    rows = list(args[3].adjacency)
    rows[0], rows[1] = (), (2,)
    args[3] = PartGraph(tuple(rows), args[3].part_to_unit)
    with pytest.raises(ValueError, match="exactly match source shared-edge geometry"):
        _build(args)


def test_foreign_context_archive_is_verified(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    (tmp_path / "context.zip").write_bytes(b"changed")
    with pytest.raises(ValueError, match="context source archive differs"):
        _build(args)


@pytest.mark.parametrize("k", [True, 25, 11037])
def test_only_authorized_anchor_counts_are_supported(tmp_path, monkeypatch, k):
    with pytest.raises(ValueError, match="26, 35, 42, and 61"):
        _build(_fixture(tmp_path, monkeypatch), k)
