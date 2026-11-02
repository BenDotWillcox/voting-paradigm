"""Florida's recorded edge preserves physical geometry and actual-count policy."""
from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path

import pytest
import shapefile
from shapely.geometry import MultiPolygon, box
from shapely.geometry.polygon import orient

from districting.part_connectivity import PartGraph
from scripts import florida_recorded_links as policy
from scripts.hawaii_population_links import _great_circle_m, select_population_aware_forest


def _repin(diagnostic: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policy, "PINNED_EVIDENCE_SHA256", {
        name: policy._sha256(diagnostic / name) for name in policy.PINNED_EVIDENCE_SHA256
    })


def _write_source(source, geoms, geoids, pops):
    with shapefile.Writer(str(source)) as writer:
        writer.field("GEOID20", "C", size=15)
        writer.field("POP20", "N", size=10)
        for geom, geoid, population in zip(geoms, geoids, pops, strict=True):
            parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
            writer.poly([list(orient(part, sign=-1).exterior.coords) for part in parts])
            writer.record(geoid, population)


def _source_hashes(source):
    return {source.with_suffix(suffix).name: policy._sha256(source.with_suffix(suffix))
            for suffix in (".shp", ".shx", ".dbf")}


def _fixture(tmp_path, monkeypatch):
    source = tmp_path / "blocks.shp"
    geoids = tuple(f"12001000100{i:04d}" for i in range(66))
    pops = (100,) * 65 + (3,)
    xs = [-82 + i * .01 for i in range(66)]
    geoms = [box(xs[i], 27, xs[i + 1], 27.01) for i in range(65)]
    geoms.append(box(xs[30], 27.02, xs[31], 27.03))
    _write_source(source, geoms, geoids, pops)
    rows = [tuple(j for j in (i - 1, i + 1) if 0 <= j < 65) for i in range(65)] + [()]
    graph = PartGraph(tuple(rows), tuple(range(66)))
    diagnostic = tmp_path / "diagnostic"
    diagnostic.mkdir()
    archive = tmp_path / "source.zip"
    archive.write_bytes(b"synthetic verified Florida fixture")
    monkeypatch.setattr(policy, "SOURCE_ARCHIVE_SHA256", policy._sha256(archive))
    middle = (xs[30] + xs[31]) / 2
    coordinates = [[middle, 27.01], [middle, 27.02]]
    candidates = [{"id": "fl-candidate-00-01", "component_ids": [0, 1],
                   "endpoints": [{"geoid": geoids[node], "part_node": node,
                                  "part_index": 0, "coordinate": coordinate}
                                 for node, coordinate in zip((30, 65), coordinates, strict=True)],
                   "distance_m": _great_circle_m(*coordinates), "classification": "positive_gap",
                   "eligible_positive_gap": True, "source_boundaries_intersect": False,
                   "intervening_component_ids": [], "endpoint_component_interior_crossings": [],
                   "selected_k": [28, 37, 45, 65]}]
    plans = []
    for k in policy.SUPPORTED_DISTRICT_COUNTS:
        selected = select_population_aware_forest([6500, 3], candidates, k)
        plans.append({"district_count": k, "selected_link_ids": selected["selected_link_ids"],
                      "actual_district_plan_generated": False, "augmented_component_count": 1,
                      "policy": selected, "policy_population_bound": selected["population_bound"]})
    diagnosis = {"state_fips": "12", "physical_component_count": 2, "blocks_spanning_components": [],
                 "status": "diagnostic_complete_no_district_plans_generated", "part_count": 66,
                 "block_count": 66, "total_population": sum(pops), "links": candidates, "plans": plans,
                 "source": {"archive_path": str(archive), "archive_sha256": policy._sha256(archive),
                            "extracted_file_sha256": _source_hashes(source)},
                 "components": [{"population": 6500, "part_count": 65, "block_count": 65},
                                {"population": 3, "part_count": 1, "block_count": 1}]}
    (diagnostic / "diagnosis.json").write_text(json.dumps(diagnosis))
    (diagnostic / "candidate-links.json").write_text(json.dumps(candidates))
    context = {"sources": [{"title": "Synthetic regional geography", "url": "https://example.invalid/map"}],
               "links": [{"candidate_id": "fl-candidate-00-01", "summary": "Regional geography; no land-mask certificate."}],
               "water_context_validation": {"source_component_clearance_verified": True,
                                            "official_regional_geography_reviewed": True,
                                            "independent_global_land_mask_tested": False,
                                            "foreign_land_exclave_identified": False,
                                            "connection_kind": "proposed recorded-water-connection"}}
    (diagnostic / "geography-context.json").write_text(json.dumps(context))
    _repin(diagnostic, monkeypatch)
    return source, geoids, pops, graph, diagnostic, geoms


def _build(args, k=28):
    return policy.build_florida_connections(*args[:4], district_count=k, diagnostic_dir=args[4])


def _change_diagnosis(args, monkeypatch, change):
    path = args[4] / "diagnosis.json"
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))
    _repin(args[4], monkeypatch)


def _change_candidate(args, monkeypatch, change):
    path = args[4] / "candidate-links.json"
    candidates = json.loads(path.read_text())
    change(candidates[0])
    path.write_text(json.dumps(candidates))
    _change_diagnosis(args, monkeypatch, lambda data: data.update(links=candidates))


def test_all_actual_counts_use_same_records_and_preserve_exact_geometry(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    baseline_records = None
    for k in policy.SUPPORTED_DISTRICT_COUNTS:
        augmented, records, audit = _build(args, k)
        assert args[3].adjacency[-1] == ()
        assert augmented.part_to_unit == args[3].part_to_unit
        assert augmented.adjacency[30] == (29, 31, 65)
        assert augmented.adjacency[65] == (30,)
        assert [r["id"] for r in records] == ["fl-water-001"]
        assert [r["candidate_id"] for r in records] == list(policy.AUTHORIZED_CANDIDATE_IDS)
        assert records == (baseline_records or records)
        baseline_records = records
        assert audit["physical_component_count"] == 2
        assert audit["augmented_component_count"] == 1
        assert audit["synthetic_edge_count"] == 1
        assert audit["source_population"] == 6503
        assert audit["population_selection"]["eligible_root_component_ids"] == [0]
        assert audit["population_selection"]["district_count"] == k
        assert audit["population_selection"]["ideal_population"] == 6503 / k
        assert audit["population_selection"]["minimum_root_population"] == float(Fraction(6503 * 99, k * 100))
        assert audit["population_selection"]["population_bound"]["seat_counts"] == [k]
        assert audit["groups"][0]["district_count"] == k
        assert audit["target_selection_verified_against_diagnosis"] is True
        assert audit["source_geometry_modified"] is False
        assert audit["synthetic_ownership_edges"] is False
        assert records[0]["geographic_context"]["independent_global_land_mask_tested"] is False
        assert "mapped_water_length_m" not in records[0]["geographic_context"]
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize("k", [True, 28.0, 0, 29, 52, 11037])
def test_unsupported_or_noninteger_count_rejected(tmp_path, monkeypatch, k):
    with pytest.raises(ValueError, match="counts 28, 37, 45, and 65 only"):
        _build(_fixture(tmp_path, monkeypatch), k)


def test_more_districts_than_blocks_rejected_before_source_access(tmp_path, monkeypatch):
    args = list(_fixture(tmp_path, monkeypatch))
    args[1], args[2] = args[1][:27], args[2][:27]
    args[3] = PartGraph(tuple(tuple(n for n in row if n < 27) for row in args[3].adjacency[:27]), tuple(range(27)))
    with pytest.raises(ValueError, match="at least one block per district"):
        _build(args)


@pytest.mark.parametrize("geoid", ["060010001000000", "12001000100000", "12001000100000x"])
def test_other_state_or_invalid_geoid_rejected(tmp_path, monkeypatch, geoid):
    args = list(_fixture(tmp_path, monkeypatch))
    args[1] = (geoid, *args[1][1:])
    with pytest.raises(ValueError, match="15-digit Florida"):
        _build(args)


def test_changed_evidence_cannot_silently_redefine_policy(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    with (args[4] / "geography-context.json").open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="evidence hash changed"):
        _build(args)


@pytest.mark.parametrize("file", ["source.zip", "blocks.shp", "blocks.dbf"])
def test_changed_source_rejected(tmp_path, monkeypatch, file):
    args = _fixture(tmp_path, monkeypatch)
    with (tmp_path / file).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="differs from the preserved"):
        _build(args)


def test_repinning_diagnosis_cannot_replace_authorized_archive(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    _change_diagnosis(args, monkeypatch, lambda data: data["source"].update(archive_sha256="0" * 64))
    with pytest.raises(ValueError, match="authorized source archive"):
        _build(args)


def test_population_redistribution_cannot_hide_in_component_total(tmp_path, monkeypatch):
    args = list(_fixture(tmp_path, monkeypatch))
    args[2] = (99, 101, *args[2][2:])
    with pytest.raises(ValueError, match="whole-block population differs"):
        _build(args)


def test_physical_edge_cannot_be_omitted(tmp_path, monkeypatch):
    args = list(_fixture(tmp_path, monkeypatch))
    rows = list(args[3].adjacency)
    rows[0], rows[1] = (), (2,)
    args[3] = PartGraph(tuple(rows), args[3].part_to_unit)
    with pytest.raises(ValueError, match="exactly match source shared-edge geometry"):
        _build(args)


@pytest.mark.parametrize(("field", "value"), [("independent_global_land_mask_tested", True),
                                               ("foreign_land_exclave_identified", True),
                                               ("official_regional_geography_reviewed", False)])
def test_regional_water_attribution_cannot_be_strengthened_or_reclassified(tmp_path, monkeypatch, field, value):
    args = _fixture(tmp_path, monkeypatch)
    path = args[4] / "geography-context.json"
    context = json.loads(path.read_text())
    context["water_context_validation"][field] = value
    path.write_text(json.dumps(context))
    _repin(args[4], monkeypatch)
    with pytest.raises(ValueError, match="Water attribution"):
        _build(args)


@pytest.mark.parametrize(("field", "value", "match"), [("geoid", "120010001009999", "ownership/component"),
                                                         ("part_node", True, "endpoint node"),
                                                         ("part_index", 1, "ownership/component"),
                                                         ("coordinate", [-82, 28], "unchanged source part boundary")])
def test_endpoint_identity_and_boundary_rechecked(tmp_path, monkeypatch, field, value, match):
    args = _fixture(tmp_path, monkeypatch)
    _change_candidate(args, monkeypatch, lambda row: row["endpoints"][0].update({field: value}))
    with pytest.raises(ValueError, match=match):
        _build(args)


@pytest.mark.parametrize("distance", [0, -1, float("nan"), True])
def test_positive_finite_gap_required(tmp_path, monkeypatch, distance):
    args = _fixture(tmp_path, monkeypatch)
    _change_candidate(args, monkeypatch, lambda row: row.update(distance_m=distance))
    with pytest.raises(ValueError, match="positive finite gap"):
        _build(args)


def test_segment_cannot_cross_endpoint_part_interior(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    def change(row):
        row["endpoints"][0]["coordinate"][1] = 27
        row["distance_m"] = _great_circle_m(*(e["coordinate"] for e in row["endpoints"]))
    _change_candidate(args, monkeypatch, change)
    with pytest.raises(ValueError, match="crosses a Florida source part interior"):
        _build(args)


def test_segment_cannot_cross_nonendpoint_source_parts(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    def change(row):
        row["endpoints"][0].update(geoid=args[1][0], part_node=0, coordinate=[-81.99, 27.005])
        row["distance_m"] = _great_circle_m(*(e["coordinate"] for e in row["endpoints"]))
    _change_candidate(args, monkeypatch, change)
    with pytest.raises(ValueError, match="crosses a Florida source part interior"):
        _build(args)


@pytest.mark.parametrize("population", [0, 100])
def test_multipart_owner_never_bridges_components_or_splits_population(tmp_path, monkeypatch, population):
    args = list(_fixture(tmp_path, monkeypatch))
    source, geoids, pops, graph, diagnostic, geoms = args
    new_geoids, new_pops = geoids[:-1], (population, *pops[1:-1])
    new_geoms = [MultiPolygon([geoms[0], geoms[-1]]), *geoms[1:-1]]
    _write_source(source, new_geoms, new_geoids, new_pops)
    remap = {0: 0, 65: 1, **{i: i + 1 for i in range(1, 65)}}
    rows = [()] * 66
    for node, neighbors in enumerate(graph.adjacency):
        rows[remap[node]] = tuple(sorted(remap[n] for n in neighbors))
    args[1], args[2], args[3] = new_geoids, new_pops, PartGraph(tuple(rows), (0, 0, *range(1, 65)))
    def change(data):
        data["block_count"] = 65
        data["source"]["extracted_file_sha256"] = _source_hashes(source)
    _change_diagnosis(args, monkeypatch, change)
    with pytest.raises(ValueError, match="Common multipart ownership"):
        _build(args)


def test_stale_target_count_selection_rejected(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    def change(data):
        data["plans"][1]["policy"] = data["plans"][0]["policy"]
    _change_diagnosis(args, monkeypatch, change)
    with pytest.raises(ValueError, match="target-count population policy differs"):
        _build(args, 37)


def test_duplicate_target_count_plan_rejected(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    _change_diagnosis(args, monkeypatch, lambda data: data["plans"].append(data["plans"][0]))
    with pytest.raises(ValueError, match="exactly one source-policy plan"):
        _build(args)


def test_island_becoming_independent_root_is_not_silently_accepted(tmp_path, monkeypatch):
    args = list(_fixture(tmp_path, monkeypatch))
    source, geoids, _, _, _, geoms = args
    # Island has exactly one 28th of total population: two feasible roots now.
    args[2] = (27,) * 65 + (65,)
    _write_source(source, geoms, geoids, args[2])
    def change(data):
        data["source"]["extracted_file_sha256"] = _source_hashes(source)
        data["total_population"] = sum(args[2])
        data["components"][0]["population"] = 27 * 65
        data["components"][1]["population"] = 65
    _change_diagnosis(args, monkeypatch, change)
    with pytest.raises(ValueError, match="attachment or target-count allocation"):
        _build(args)
