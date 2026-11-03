"""California recorded-water scope, exact geometry, and honest provenance."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import shapefile
from shapely.geometry import MultiPolygon, box
from shapely.geometry.polygon import orient

from districting.part_connectivity import PartGraph
from scripts import california_recorded_links as policy
from scripts.hawaii_population_links import _great_circle_m


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
    geoids = tuple(f"06001000100{i:04d}" for i in range(58))
    pops = (100,) * 52 + (0, 3, 2, 0, 0, 0)
    xs = [-121 + i * .01 for i in range(53)]
    geoms = [box(xs[i], 36, xs[i + 1], 36.01) for i in range(52)]
    geoms += [box(xs[5], 36.02, xs[6], 36.03), box(xs[20], 35.96, xs[21], 35.97),
              box(xs[20], 35.91, xs[21], 35.92), box(-121.03, 36.002, -121.02, 36.008),
              box(xs[7], 35.96, xs[8], 35.97), box(xs[14], 35.96, xs[15], 35.97)]
    _write_source(source, geoms, geoids, pops)
    rows = [tuple(j for j in (i - 1, i + 1) if 0 <= j < 52) for i in range(52)] + [()] * 6
    graph = PartGraph(tuple(rows), tuple(range(58)))
    diagnostic = tmp_path / "diagnostic"
    diagnostic.mkdir()
    archive = tmp_path / "source.zip"
    archive.write_bytes(b"synthetic verified source")

    def candidate(pair, nodes, coordinates, eligible=True):
        return {"id": f"ca-candidate-{pair[0]:02d}-{pair[1]:02d}", "component_ids": list(pair),
                "endpoints": [{"geoid": geoids[node], "part_node": node, "part_index": 0, "coordinate": coordinate}
                              for node, coordinate in zip(nodes, coordinates, strict=True)],
                "distance_m": _great_circle_m(*coordinates), "classification": "positive_gap", "eligible_positive_gap": eligible,
                "source_boundaries_intersect": False, "intervening_component_ids": [] if eligible else [2],
                "endpoint_component_interior_crossings": []}

    mid5, mid20 = (xs[5] + xs[6]) / 2, (xs[20] + xs[21]) / 2
    candidates = [candidate((0, 1), (5, 52), [[mid5, 36.01], [mid5, 36.02]]),
                  candidate((0, 2), (20, 53), [[mid20, 36], [mid20, 35.97]]),
                  candidate((0, 3), (20, 54), [[mid20, 36], [mid20, 35.92]], eligible=False),
                  candidate((0, 4), (0, 55), [[xs[0], 36.005], [-121.02, 36.005]]),
                  candidate((2, 3), (53, 54), [[mid20, 35.96], [mid20, 35.92]]),
                  candidate((2, 6), (53, 57), [[xs[20], 35.965], [xs[15], 35.965]]),
                  candidate((5, 6), (56, 57), [[xs[8], 35.965], [xs[14], 35.965]])]
    diagnosis = {"state_fips": "06", "physical_component_count": 7, "blocks_spanning_components": [],
                 "status": "diagnostic_complete_no_district_plans_generated", "part_count": 58, "block_count": 58,
                 "source": {"archive_path": str(archive), "archive_sha256": policy._sha256(archive),
                            "extracted_file_sha256": _source_hashes(source)}, "links": candidates, "total_population": sum(pops),
                 "components": [{"population": 5200, "part_count": 52, "block_count": 52}] +
                               [{"population": p, "part_count": 1, "block_count": 1} for p in pops[52:]],
                 "plans": [{"district_count": 52, "selected_link_ids": list(policy.AUTHORIZED_CANDIDATE_IDS),
                            "actual_district_plan_generated": False}]}
    (diagnostic / "diagnosis.json").write_text(json.dumps(diagnosis))
    (diagnostic / "candidate-links.json").write_text(json.dumps(candidates))
    context = {"sources": [{"title": "Synthetic regional geography", "url": "https://example.invalid/map"}],
               "links": [{"candidate_id": candidate_id, "summary": "Regional geographic attribution; no land-mask certification."}
                         for candidate_id in policy.AUTHORIZED_CANDIDATE_IDS],
               "water_context_validation": {"source_component_clearance_verified": True,
                                            "official_regional_geography_reviewed": True,
                                            "independent_global_land_mask_tested": False,
                                            "foreign_land_exclave_identified": False,
                                            "connection_kind": "proposed recorded-water-connection"}}
    (diagnostic / "geography-context.json").write_text(json.dumps(context))
    _repin(diagnostic, monkeypatch)
    return source, geoids, pops, graph, diagnostic, geoms


def _build(args, k=52):
    return policy.build_california_connections(*args[:4], district_count=k, diagnostic_dir=args[4])


def _change_candidate(args, monkeypatch, index, change):
    diagnostic = args[4]
    candidates = json.loads((diagnostic / "candidate-links.json").read_text())
    change(candidates[index])
    diagnosis = json.loads((diagnostic / "diagnosis.json").read_text())
    diagnosis["links"] = candidates
    (diagnostic / "candidate-links.json").write_text(json.dumps(candidates))
    (diagnostic / "diagnosis.json").write_text(json.dumps(diagnosis))
    _repin(diagnostic, monkeypatch)


def test_six_edges_connect_all_parts_without_changing_source_or_certifying_water(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    augmented, records, audit = _build(args)
    assert args[3].adjacency[52:] == ((),) * 6
    assert augmented.part_to_unit == args[3].part_to_unit
    assert [r["candidate_id"] for r in records] == list(policy.AUTHORIZED_CANDIDATE_IDS)
    assert [r["id"] for r in records] == [f"ca-water-{i:03d}" for i in range(1, 7)]
    assert {r["kind"] for r in records} == {"recorded-water-connection"}
    assert audit["physical_component_count"] == 7
    assert audit["augmented_component_count"] == 1
    assert audit["augmented_edge_count"] - audit["physical_edge_count"] == 6
    assert audit["source_population"] == sum(args[2])
    assert audit["population_selection"]["eligible_root_component_ids"] == [0]
    assert audit["unselected_candidate_ids"] == ["ca-candidate-00-03"]
    for record in records:
        assert record["geographic_context"]["independent_global_land_mask_tested"] is False
        assert "mapped_water_length_m" not in record["geographic_context"]
        assert "water_only" not in record["geographic_context"]
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize("k", [True, 26, 69, 83, 120, 11037])
def test_only_currently_authorized_count_runs(tmp_path, monkeypatch, k):
    with pytest.raises(ValueError, match="52 districts only"):
        _build(_fixture(tmp_path, monkeypatch), k)


def test_changed_diagnostic_is_rejected_without_repinning(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    with (args[4] / "geography-context.json").open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="evidence hash changed"):
        _build(args)


@pytest.mark.parametrize("file", ["source.zip", "blocks.shp"])
def test_changed_source_is_rejected(tmp_path, monkeypatch, file):
    args = _fixture(tmp_path, monkeypatch)
    with (tmp_path / file).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="differs from the preserved"):
        _build(args)


def test_population_redistribution_cannot_hide_in_component_total(tmp_path, monkeypatch):
    args = list(_fixture(tmp_path, monkeypatch))
    args[2] = (99, 101) + args[2][2:]
    with pytest.raises(ValueError, match="whole-block population differs"):
        _build(args)


def test_omitted_physical_edge_cannot_be_replaced_by_water_policy(tmp_path, monkeypatch):
    args = list(_fixture(tmp_path, monkeypatch))
    rows = list(args[3].adjacency)
    rows[0], rows[1] = (), (2,)
    args[3] = PartGraph(tuple(rows), args[3].part_to_unit)
    with pytest.raises(ValueError, match="exactly match source shared-edge geometry"):
        _build(args)


@pytest.mark.parametrize(("field", "value"), [("independent_global_land_mask_tested", True),
                                               ("foreign_land_exclave_identified", True),
                                               ("official_regional_geography_reviewed", False)])
def test_water_attribution_cannot_be_strengthened_or_reclassified(tmp_path, monkeypatch, field, value):
    args = _fixture(tmp_path, monkeypatch)
    path = args[4] / "geography-context.json"
    data = json.loads(path.read_text())
    data["water_context_validation"][field] = value
    path.write_text(json.dumps(data))
    _repin(args[4], monkeypatch)
    with pytest.raises(ValueError, match="Water attribution"):
        _build(args)


@pytest.mark.parametrize(("field", "value", "match"), [("geoid", "060010001009999", "ownership/component"),
                                                         ("part_node", True, "endpoint node"),
                                                         ("part_index", 1, "ownership/component"),
                                                         ("coordinate", [-120.945, 36.5], "unchanged source part boundary")])
def test_endpoint_identity_and_geometry_are_rechecked(tmp_path, monkeypatch, field, value, match):
    args = _fixture(tmp_path, monkeypatch)
    _change_candidate(args, monkeypatch, 0, lambda row: row["endpoints"][0].update({field: value}))
    with pytest.raises(ValueError, match=match):
        _build(args)


@pytest.mark.parametrize("distance", [0, -1, float("nan"), True])
def test_connection_requires_positive_finite_distance(tmp_path, monkeypatch, distance):
    args = _fixture(tmp_path, monkeypatch)
    _change_candidate(args, monkeypatch, 0, lambda row: row.update(distance_m=distance))
    with pytest.raises(ValueError, match="positive finite gap"):
        _build(args)


def test_segment_cannot_cross_endpoint_component_interior(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    def change(row):
        row["endpoints"][0]["coordinate"][1] = 36.0
        row["distance_m"] = _great_circle_m(*(e["coordinate"] for e in row["endpoints"]))
    _change_candidate(args, monkeypatch, 0, change)
    with pytest.raises(ValueError, match="crosses a California source part interior"):
        _build(args)


def test_segment_cannot_cross_third_component_even_if_saved_flags_claim_clear(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    _change_candidate(args, monkeypatch, 2, lambda row: row.update(eligible_positive_gap=True, intervening_component_ids=[]))
    with pytest.raises(ValueError, match="crosses a California source part interior"):
        _build(args)


@pytest.mark.parametrize("population", [0, 100])
def test_multipart_owner_cannot_bridge_global_components_even_with_zero_population(tmp_path, monkeypatch, population):
    args = list(_fixture(tmp_path, monkeypatch))
    source, geoids, pops, graph, diagnostic, geoms = args
    new_geoids = geoids[:-1]
    new_pops = (population,) + pops[1:-1]
    new_geoms = [MultiPolygon([geoms[0], geoms[-1]]), *geoms[1:-1]]
    _write_source(source, new_geoms, new_geoids, new_pops)
    remap = {0: 0, 57: 1, **{i: i + 1 for i in range(1, 57)}}
    rows = [()] * 58
    for node, neighbors in enumerate(graph.adjacency):
        rows[remap[node]] = tuple(sorted(remap[n] for n in neighbors))
    args[1], args[2], args[3] = new_geoids, new_pops, PartGraph(tuple(rows), (0, 0, *range(1, 57)))
    data = json.loads((diagnostic / "diagnosis.json").read_text())
    data["block_count"] = 57
    data["source"]["extracted_file_sha256"] = _source_hashes(source)
    (diagnostic / "diagnosis.json").write_text(json.dumps(data))
    _repin(diagnostic, monkeypatch)
    with pytest.raises(ValueError, match="Common multipart ownership"):
        _build(args)


def test_new_shorter_attachment_is_not_silently_authorized(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    diagnostic = args[4]
    candidates = json.loads((diagnostic / "candidate-links.json").read_text())
    xs = [-121 + i * .01 for i in range(53)]
    mid = (xs[14] + xs[15]) / 2
    coordinates = [[mid, 36], [mid, 35.97]]
    candidates.append({"id": "ca-candidate-00-06", "component_ids": [0, 6],
                       "endpoints": [{"geoid": args[1][n], "part_node": n, "part_index": 0, "coordinate": c}
                                     for n, c in zip((14, 57), coordinates, strict=True)],
                       "distance_m": _great_circle_m(*coordinates), "classification": "positive_gap", "eligible_positive_gap": True,
                       "source_boundaries_intersect": False, "intervening_component_ids": [], "endpoint_component_interior_crossings": []})
    data = json.loads((diagnostic / "diagnosis.json").read_text())
    data["links"] = candidates
    (diagnostic / "candidate-links.json").write_text(json.dumps(candidates))
    (diagnostic / "diagnosis.json").write_text(json.dumps(data))
    _repin(diagnostic, monkeypatch)
    with pytest.raises(ValueError, match="selector changed the six authorized"):
        _build(args)
