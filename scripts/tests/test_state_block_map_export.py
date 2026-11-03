"""State identity, unsupported topology, and owned gzip-only map storage."""

from __future__ import annotations

import gzip
import copy
import json
from pathlib import Path
from typing import Any

import pytest
import shapefile
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient

from scripts import state_block_map_export as exporter


def _geoid(index: int) -> str:
    return f"01001000100{index:04d}"


def _source(tmp_path: Path, shapes: list[Polygon]) -> tuple[Path, dict[str, int]]:
    path = tmp_path / "blocks.shp"
    populations = {}
    with shapefile.Writer(str(path)) as writer:
        writer.field("GEOID20", "C", size=15)
        writer.field("COUNTYFP20", "C", size=3)
        writer.field("POP20", "N", size=10)
        for index, polygon in enumerate(shapes):
            polygon = orient(polygon, sign=-1)
            writer.poly([list(polygon.exterior.coords)])
            writer.record(_geoid(index), "001", 5 + index)
            populations[_geoid(index)] = 5 + index
    return path, populations


def _run(source: Path, populations: dict[str, int], labels: list[int], output: Path) -> dict[str, Any]:
    return exporter.export_state_block_maps(
        source, dict(zip(populations, labels, strict=True)), populations, output,
        state_fips="01", state_name="Alabama", n_districts=max(labels) + 1,
    )


def test_successful_state_maps_keep_verified_gzip_only(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01), box(-99.99, 38, -99.98, 38.01)])
    output = tmp_path / "maps"
    result = _run(source, populations, [0, 1], output)
    assert result["state_fips"] == "01"
    assert result["state_name"] == "Alabama"
    assert "national_state_only" in result["load_scenarios"]
    assert "national_kansas_only" not in result["load_scenarios"]
    assert result["strict_validation"] == {"passed": True, "issues": []}
    assert result["storage"]["geojson_artifact_count"] == 4
    assert not list(output.rglob("*.geojson"))
    assert (output / "block-index.json").exists()
    assert source.exists()
    for artifact in result["storage"]["artifacts"]:
        raw = gzip.decompress((output / artifact["gzip_path"]).read_bytes())
        assert len(raw) == artifact["raw_bytes"]
        assert json.loads(raw)["type"] == "FeatureCollection"
    saved = json.loads((output / "map-manifest.json").read_text())
    assert saved["storage"]["gzip_roundtrip_verified"] is True


def test_antimeridian_source_is_explicitly_unsupported_before_export(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-179.5, 50, -179.4, 51), box(179.4, 50, 179.5, 51)])
    output = tmp_path / "maps"
    with pytest.raises(exporter.UnsupportedStateGeometryError, match="antimeridian"):
        _run(source, populations, [0, 1], output)
    assert not output.exists()


def test_disconnected_geometry_retains_compressed_failed_diagnostics(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01), box(-99.98, 38, -99.97, 38.01)])
    output = tmp_path / "maps"
    with pytest.raises(exporter.StateMapValidationError, match="2 polygon components"):
        _run(source, populations, [0, 0], output)
    saved = json.loads((output / "map-manifest.json").read_text())
    assert saved["strict_validation"]["passed"] is False
    assert not list(output.rglob("*.geojson"))
    assert (output / "districts-full.geojson.gz").exists()


def test_corrupt_gzip_does_not_delete_raw_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01)])
    original = exporter.original_exporter.export_maps

    def corrupt(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original(*args, **kwargs)
        (args[3] / "districts-full.geojson.gz").write_bytes(gzip.compress(b"incorrect"))
        return result

    monkeypatch.setattr(exporter.original_exporter, "export_maps", corrupt)
    output = tmp_path / "maps"
    with pytest.raises(ValueError, match="roundtrip mismatch"):
        _run(source, populations, [0], output)
    assert (output / "districts-full.geojson").exists()
    assert (output / "blocks/county-001.geojson").exists()


def test_export_failure_compresses_only_new_partial_geojson(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01)])

    def fail(*args: Any, **kwargs: Any) -> Any:
        (args[3] / "districts-full.geojson").write_bytes(b'{"incomplete":')
        raise RuntimeError("deliberate export failure")

    monkeypatch.setattr(exporter.original_exporter, "export_maps", fail)
    output = tmp_path / "maps"
    with pytest.raises(RuntimeError, match="deliberate"):
        _run(source, populations, [0], output)
    saved = json.loads((output / "failed-export-storage.json").read_text())
    assert saved["status"] == "failed"
    assert saved["storage"]["partial_export"] is True
    assert not (output / "districts-full.geojson").exists()
    assert gzip.decompress((output / "districts-full.geojson.gz").read_bytes()) == b'{"incomplete":'


def test_existing_output_and_wrong_state_are_rejected_without_changes(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01)])
    output = tmp_path / "maps"
    output.mkdir()
    preserved = output / "existing.geojson"
    preserved.write_text("original")
    with pytest.raises(ValueError, match="empty"):
        _run(source, populations, [0], output)
    assert preserved.read_text() == "original"
    with pytest.raises(ValueError, match="does not belong"):
        exporter.export_state_block_maps(
            source, {_geoid(0): 0}, populations, tmp_path / "other",
            state_fips="02", state_name="Alaska", n_districts=1,
        )


def _water_link(left: int = 0, right: int = 1) -> dict[str, Any]:
    return {
        "id": f"water-{left}-{right}", "state_fips": "01", "component_ids": [left, right],
        "distance_m": 876.0,
        "endpoints": [
            {"geoid": _geoid(left), "part_index": 0, "part_node": left, "coordinate": [-99.99 + 0.02 * left, 38.005]},
            {"geoid": _geoid(right), "part_index": 0, "part_node": right, "coordinate": [-100 + 0.02 * right, 38.005]},
        ],
    }


def _water_run(source: Path, populations: dict[str, int], labels: list[int], output: Path, links: list[dict[str, Any]]) -> dict[str, Any]:
    return exporter.export_state_block_maps(
        source, dict(zip(populations, labels, strict=True)), populations, output,
        state_fips="01", state_name="Alabama", n_districts=max(labels) + 1,
        water_connections=links,
    )


def test_declared_water_link_passes_policy_without_claiming_physical_connectivity(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01), box(-99.98, 38, -99.97, 38.01)])
    result = _water_run(source, populations, [0, 0], tmp_path / "maps", [_water_link()])
    assert result["strict_validation"]["passed"] is False
    validation = result["connectivity_validation"]
    assert validation["passed"] is True
    assert validation["source_coverage_preserved_exactly"] is True
    assert validation["districts"] == [{
        "district_id": 0, "physical_polygon_components": 2,
        "connected_components_after_links": 1, "used_link_ids": ["water-0-1"],
    }]
    saved = json.loads(gzip.decompress((tmp_path / "maps/water-connections.geojson.gz").read_bytes()))
    feature = saved["features"][0]
    assert feature["geometry"]["type"] == "LineString"
    assert feature["properties"]["used_by_district"] == 0
    assert feature["properties"]["endpoint_districts"] == [0, 0]
    assert feature["properties"]["endpoints"] == _water_link()["endpoints"]
    assert result["storage"]["geojson_artifact_count"] == 5
    assert not list((tmp_path / "maps").rglob("*.geojson"))


def test_unlinked_physical_split_remains_invalid_under_water_policy(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100 + i * 0.02, 38, -99.99 + i * 0.02, 38.01) for i in range(3)])
    with pytest.raises(exporter.StateMapValidationError, match="still has 2 components"):
        _water_run(source, populations, [0, 0, 0], tmp_path / "maps", [_water_link()])
    saved = json.loads((tmp_path / "maps/map-manifest.json").read_text())
    assert saved["connectivity_validation"]["passed"] is False
    assert saved["strict_validation"]["passed"] is False


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("coordinate", [-99.995, 38.005], "not on the declared source part boundary"),
    ("geoid", "020010001000000", "not an assigned source block"),
    ("part_index", 1, "invalid source part index"),
    ("part_node", 1, "global part ownership"),
])
def test_water_link_rejects_false_endpoint_geometry(tmp_path: Path, field: str, value: Any, reason: str) -> None:
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01), box(-99.98, 38, -99.97, 38.01)])
    link = copy.deepcopy(_water_link())
    link["endpoints"][0][field] = value
    with pytest.raises(exporter.StateMapValidationError, match=reason):
        _water_run(source, populations, [0, 0], tmp_path / "maps", [link])


def test_cross_district_link_cannot_connect_a_district_via_another_district(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100 + i * 0.02, 38, -99.99 + i * 0.02, 38.01) for i in range(3)])
    with pytest.raises(exporter.StateMapValidationError, match="still has 2 components"):
        _water_run(source, populations, [0, 1, 0], tmp_path / "maps", [_water_link(0, 1), _water_link(1, 2)])
    saved = json.loads((tmp_path / "maps/map-manifest.json").read_text())
    assert saved["connectivity_validation"]["used_link_ids"] == []


def test_water_chain_requires_every_intermediate_component_in_the_district(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100 + i * 0.02, 38, -99.99 + i * 0.02, 38.01) for i in range(3)])
    result = _water_run(source, populations, [0, 0, 0], tmp_path / "maps", [_water_link(0, 1), _water_link(1, 2)])
    assert result["connectivity_validation"]["passed"] is True
    assert result["connectivity_validation"]["districts"][0]["physical_polygon_components"] == 3
    assert result["connectivity_validation"]["districts"][0]["connected_components_after_links"] == 1


def test_empty_water_policy_does_not_implicitly_accept_multis(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01), box(-99.98, 38, -99.97, 38.01)])
    with pytest.raises(exporter.StateMapValidationError, match="still has 2 components"):
        _water_run(source, populations, [0, 0], tmp_path / "maps", [])


def test_water_link_cannot_hide_another_part_of_the_same_block(tmp_path: Path) -> None:
    source = tmp_path / "multipart.shp"
    with shapefile.Writer(str(source)) as writer:
        writer.field("GEOID20", "C", size=15)
        writer.field("COUNTYFP20", "C", size=3)
        writer.field("POP20", "N", size=10)
        writer.poly([
            list(orient(box(-100, 38, -99.99, 38.01), sign=-1).exterior.coords),
            list(orient(box(-99.90, 38, -99.89, 38.01), sign=-1).exterior.coords),
        ])
        writer.record(_geoid(0), "001", 0)
        writer.poly([list(orient(box(-99.98, 38, -99.97, 38.01), sign=-1).exterior.coords)])
        writer.record(_geoid(1), "001", 6)
    link = _water_link()
    link["endpoints"][1]["part_node"] = 2  # The first block owns two source parts.
    with pytest.raises(exporter.StateMapValidationError, match="still has 2 components"):
        _water_run(source, {_geoid(0): 0, _geoid(1): 6}, [0, 0], tmp_path / "maps", [link])
    saved = json.loads((tmp_path / "maps/map-manifest.json").read_text())
    assert saved["connectivity_validation"]["districts"][0]["physical_polygon_components"] == 3


def _exclave_link(left: int = 0, right: int = 1) -> dict[str, Any]:
    return {**_water_link(left, right), "id": f"exclave-{left}-{right}",
            "kind": "recorded-exclave-connection", "policy": "test-recorded-exclave-policy",
            "geographic_context": {"water_only": False, "crossed_state": "Missouri"},
            "provenance": {"diagnostic": "synthetic geometry regression"}}


def _exclave_run(source: Path, populations: dict[str, int], labels: list[int], output: Path, links: list[dict[str, Any]]) -> dict[str, Any]:
    return exporter.export_state_block_maps(
        source, dict(zip(populations, labels, strict=True)), populations, output,
        state_fips="01", state_name="Alabama", n_districts=max(labels) + 1,
        exclave_connections=links,
    )


def test_exclave_export_retains_separate_policy_and_land_context(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01), box(-99.98, 38, -99.97, 38.01)])
    output = tmp_path / "maps"
    result = _exclave_run(source, populations, [0, 0], output, [_exclave_link()])
    assert result["strict_validation"]["passed"] is False
    validation = result["connectivity_validation"]
    assert validation["passed"] is True
    assert validation["policy"] == "shared_edges_plus_recorded_exclave_connections"
    assert validation["source_coverage_preserved_exactly"] is True
    assert validation["districts"][0]["physical_polygon_components"] == 2
    assert validation["districts"][0]["connected_components_after_links"] == 1
    assert "water_connections" not in result
    assert result["exclave_connections"]["connection_count"] == 1
    feature = json.loads(gzip.decompress((output / "exclave-connections.geojson.gz").read_bytes()))["features"][0]
    assert feature["properties"]["kind"] == "recorded-exclave-connection"
    assert feature["properties"]["geographic_context"] == _exclave_link()["geographic_context"]
    assert feature["properties"]["used_by_district"] == 0
    assert feature["properties"]["endpoint_districts"] == [0, 0]
    assert not (output / "water-connections.geojson.gz").exists()
    assert "foreign-state territory" in result["notes"][-2]


def test_exclave_opt_in_cannot_implicitly_select_water_semantics(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01), box(-99.98, 38, -99.97, 38.01)])
    with pytest.raises(exporter.StateMapValidationError, match="explicitly declare"):
        _exclave_run(source, populations, [0, 0], tmp_path / "maps", [_water_link()])
    saved = json.loads((tmp_path / "maps/map-manifest.json").read_text())
    assert saved["connectivity_validation"]["policy"] == "shared_edges_plus_recorded_exclave_connections"
    assert "Water connection" not in str(saved["connectivity_validation"]["issues"])


def test_two_recorded_policies_cannot_be_ambiguously_combined(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01)])
    output = tmp_path / "maps"
    with pytest.raises(ValueError, match="cannot be combined"):
        exporter.export_state_block_maps(source, {_geoid(0): 0}, populations, output,
            state_fips="01", state_name="Alabama", n_districts=1, water_connections=[], exclave_connections=[])
    assert not output.exists()


def test_exclave_link_must_have_same_district_endpoints_to_repair_polygon(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100 + i * .02, 38, -99.99 + i * .02, 38.01) for i in range(3)])
    with pytest.raises(exporter.StateMapValidationError, match="still has 2 components"):
        _exclave_run(source, populations, [0, 1, 0], tmp_path / "maps", [_exclave_link(0, 1), _exclave_link(1, 2)])
    saved = json.loads((tmp_path / "maps/map-manifest.json").read_text())
    assert saved["connectivity_validation"]["used_link_ids"] == []


def test_exclave_endpoints_are_independently_checked_on_source_parts(tmp_path: Path) -> None:
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01), box(-99.98, 38, -99.97, 38.01)])
    link = _exclave_link()
    link["endpoints"][0]["coordinate"] = [-99.995, 38.005]
    with pytest.raises(exporter.StateMapValidationError, match="not on the declared source part boundary"):
        _exclave_run(source, populations, [0, 0], tmp_path / "maps", [link])


def _mixed_links() -> list[dict[str, Any]]:
    return [{**_water_link(0, 1), "kind": "recorded-water-connection", "policy": "test-mixed",
             "geographic_context": {"water_only": True, "mapped_land_length_m": 0.0, "mapped_water_length_m": 100.0}},
            {**_exclave_link(1, 2), "policy": "test-mixed",
             "geographic_context": {"water_only": False, "mapped_land_length_m": 25.0, "mapped_water_length_m": 100.0}}]


def _mixed_run(source, populations, labels, output, links):
    return exporter.export_state_block_maps(source, dict(zip(populations, labels, strict=True)), populations, output,
        state_fips="01", state_name="Alabama", n_districts=max(labels) + 1, recorded_connections=links)


def test_mixed_export_keeps_both_types_and_physical_components(tmp_path):
    source, populations = _source(tmp_path, [box(-100 + i * .02, 38, -99.99 + i * .02, 38.01) for i in range(3)])
    result = _mixed_run(source, populations, [0, 0, 0], tmp_path / "maps", _mixed_links())
    assert result["strict_validation"]["passed"] is False
    validation = result["connectivity_validation"]
    assert validation["passed"] is True
    assert validation["policy"] == "shared_edges_plus_recorded_mixed_connections"
    assert validation["districts"][0]["physical_polygon_components"] == 3
    assert validation["districts"][0]["connected_components_after_links"] == 1
    assert "water_connections" not in result and "exclave_connections" not in result
    assert result["recorded_connections"]["connection_count"] == 2
    features = json.loads(gzip.decompress((tmp_path / "maps/recorded-connections.geojson.gz").read_bytes()))["features"]
    assert [f["properties"]["kind"] for f in features] == ["recorded-water-connection", "recorded-exclave-connection"]
    assert all(f["properties"]["endpoint_districts"] == [0, 0] for f in features)
    assert all(f["properties"]["used_by_district"] == 0 for f in features)


def test_mixed_link_cannot_connect_a_district_through_other_district(tmp_path):
    source, populations = _source(tmp_path, [box(-100 + i * .02, 38, -99.99 + i * .02, 38.01) for i in range(3)])
    with pytest.raises(exporter.StateMapValidationError, match="still has 2 components"):
        _mixed_run(source, populations, [0, 1, 0], tmp_path / "maps", _mixed_links())
    saved = json.loads((tmp_path / "maps/map-manifest.json").read_text())
    assert saved["connectivity_validation"]["used_link_ids"] == []


@pytest.mark.parametrize(("field", "value"), [("kind", "recorded-water-connection"),
                                                ("kind", "unspecified"),
                                                ("geographic_context", {"water_only": True, "mapped_land_length_m": 25, "mapped_water_length_m": 100})])
def test_mixed_export_rejects_forged_classification(tmp_path, field, value):
    source, populations = _source(tmp_path, [box(-100 + i * .02, 38, -99.99 + i * .02, 38.01) for i in range(3)])
    links = _mixed_links()
    links[1][field] = value
    with pytest.raises(exporter.StateMapValidationError, match="Mixed connection"):
        _mixed_run(source, populations, [0, 0, 0], tmp_path / "maps", links)


def test_mixed_policy_rejects_wrong_source_part_ownership(tmp_path):
    source, populations = _source(tmp_path, [box(-100 + i * .02, 38, -99.99 + i * .02, 38.01) for i in range(3)])
    links = _mixed_links()
    links[1]["endpoints"][1]["part_node"] = 1
    with pytest.raises(exporter.StateMapValidationError, match="global part ownership"):
        _mixed_run(source, populations, [0, 0, 0], tmp_path / "maps", links)


def test_mixed_and_legacy_policies_cannot_be_combined(tmp_path):
    source, populations = _source(tmp_path, [box(-100, 38, -99.99, 38.01)])
    with pytest.raises(ValueError, match="cannot be combined"):
        exporter.export_state_block_maps(source, {_geoid(0): 0}, populations, tmp_path / "maps",
            state_fips="01", state_name="Alabama", n_districts=1, water_connections=[], recorded_connections=[])
