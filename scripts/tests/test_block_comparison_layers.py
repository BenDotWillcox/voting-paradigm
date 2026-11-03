import json
from pathlib import Path
from zipfile import ZipFile

import pytest
import shapefile
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape

from scripts.build_block_comparison_layers import (
    aggregate_blocks, block_attributes, density_properties, fallback_tract_geometry,
    load_source_manifest, missing_material_tracts, normalize_geometry,
    publish, validate_tract_join,
)
from scripts.build_block_plan_bundle import BundleBuilder, OUTPUT, digest, encoded
from scripts.fetch_block_comparison_sources import source_metadata


def test_tract_density_uses_land_area_and_conserves_population():
    tracts, count = aggregate_blocks([
        ("260010001001001", 100, 1_000_000),
        ("260010001001002", 25, 500_000),
        ("260010002001001", 10, 200_000),
    ], "26")
    assert count == 3
    assert sum(value["population"] for value in tracts.values()) == 135
    assert density_properties("26001000100", tracts["26001000100"])["densityPerKm2"] == pytest.approx(125 / 1.5)


def test_real_dbf_field_order_cannot_swap_population_and_land(tmp_path):
    stem = "tl_2020_26_tabblock20"
    directory = tmp_path / "state-block-benchmark/source/26" / stem
    directory.mkdir(parents=True)
    path = directory / (stem + ".dbf")
    with shapefile.Writer(dbf=str(path)) as writer:
        writer.field("GEOID20", "C", size=15)
        writer.field("ALAND20", "N", size=14, decimal=0)
        writer.field("POP20", "N", size=12, decimal=0)
        writer.record("260010001001001", 2_000_000, 30)
    plan = {"state_fips": "26", "resident_population": 30, "block_count": 1,
            "source": {"archive_sha256": "f" * 64,
                       "extracted_file_sha256": {path.name: digest(path.read_bytes())}}}
    tracts, provenance = block_attributes(plan, tmp_path)
    assert tracts["26001000100"] == {"population": 30, "landAreaM2": 2_000_000, "blockCount": 1}
    assert provenance["population"] == 30


def test_removed_extraction_can_be_read_from_pinned_archive_without_reextracting(tmp_path):
    stem = "tl_2020_26_tabblock20"
    directory = tmp_path / "state-block-benchmark/source/26"
    directory.mkdir(parents=True)
    dbf = tmp_path / (stem + ".dbf")
    with shapefile.Writer(dbf=str(dbf)) as writer:
        writer.field("GEOID20", "C", size=15)
        writer.field("ALAND20", "N", size=14, decimal=0)
        writer.field("POP20", "N", size=12, decimal=0)
        writer.record("260010001001001", 500_000, 12)
    archive = directory / (stem + ".zip")
    with ZipFile(archive, "w") as zipped:
        zipped.write(dbf, dbf.name)
    plan = {"state_fips": "26", "resident_population": 12, "block_count": 1,
            "source": {"archive_sha256": digest(archive.read_bytes()),
                       "extracted_file_sha256": {dbf.name: digest(dbf.read_bytes())}}}
    before = archive.read_bytes()
    tracts, _ = block_attributes(plan, tmp_path)
    assert tracts["26001000100"]["population"] == 12
    assert not (directory / stem).exists()
    assert archive.read_bytes() == before
    plan["source"]["archive_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="archive hash mismatch"):
        block_attributes(plan, tmp_path)


def test_zero_land_area_has_null_density_even_with_population():
    assert density_properties("02013000100", {"population": 5, "landAreaM2": 0})["densityPerKm2"] is None


@pytest.mark.parametrize("rows, message", [
    ([("260010001001001", 2, 3), ("260010001001001", 2, 3)], "Duplicate"),
    ([("020010001001001", 2, 3)], "cross-state"),
    ([("26001", 2, 3)], "Invalid"),
    ([("260010001001001", -1, 3)], "nonnegative"),
    ([("260010001001001", 1.5, 3)], "integers"),
])
def test_rejects_bad_source_attributes(rows, message):
    with pytest.raises(ValueError, match=message):
        aggregate_blocks(rows, "26")


def test_join_allows_only_explicitly_empty_water_tract_omission():
    attributes = {"001": {"population": 10, "landAreaM2": 100},
                  "002": {"population": 0, "landAreaM2": 0}}
    assert validate_tract_join(attributes, {"001"}) == ["002"]
    with pytest.raises(ValueError, match="populated or land"):
        validate_tract_join(attributes, {"002"})
    with pytest.raises(ValueError, match="lacks block"):
        validate_tract_join(attributes, {"001", "002", "003"})


def test_only_materially_missing_tracts_need_fallback():
    attributes = {"001": {"population": 10, "landAreaM2": 100},
                  "002": {"population": 0, "landAreaM2": 0},
                  "003": {"population": 0, "landAreaM2": 50}}
    assert missing_material_tracts(attributes, {"001"}) == {"003"}


def test_fallback_reconstructs_only_missing_tract_from_immutable_source(tmp_path):
    stem = "tl_2020_12_tabblock20"
    source = tmp_path / "source"
    source.mkdir()
    with shapefile.Writer(str(source / stem), shapeType=shapefile.POLYGON) as writer:
        writer.field("GEOID20", "C", size=15)
        writer.field("ALAND20", "N", size=14, decimal=0)
        writer.field("POP20", "N", size=12, decimal=0)
        for geoid, x, land, pop in [("120579801001001", 0, 50, 0),
                                     ("120579801001002", 1, 70, 0),
                                     ("120570001001001", 10, 90, 5)]:
            writer.poly([[[x, 0], [x, 1], [x + 1, 1], [x + 1, 0], [x, 0]]])
            writer.record(geoid, land, pop)
    directory = tmp_path / "state-block-benchmark/source/12"
    directory.mkdir(parents=True)
    archive = directory / (stem + ".zip")
    hashes = {}
    with ZipFile(archive, "w") as zipped:
        for path in source.iterdir():
            zipped.write(path, path.name)
            hashes[path.name] = digest(path.read_bytes())
    before = archive.read_bytes()
    plan = {"state_fips": "12", "source": {"archive_sha256": digest(before), "extracted_file_sha256": hashes}}
    attributes = {"12057980100": {"population": 0, "landAreaM2": 120, "blockCount": 2}}
    features, evidence = fallback_tract_geometry(plan, tmp_path, attributes, {"12057980100"}, tolerance=0)
    assert len(features) == 1
    assert shape(features[0]["geometry"]).equals(box(0, 0, 2, 1))
    assert features[0]["properties"]["geometrySource"] == "source-block-union"
    assert evidence[0]["population"] == 0 and evidence[0]["landAreaM2"] == 120
    assert evidence[0]["sourceShpSha256"] == hashes[stem + ".shp"]
    assert archive.read_bytes() == before and not (directory / stem).exists()
    assert fallback_tract_geometry(plan, tmp_path, attributes, set()) == ([], [])
    attributes["12057980100"]["blockCount"] = 3
    with pytest.raises(ValueError, match="reconcile"):
        fallback_tract_geometry(plan, tmp_path, attributes, {"12057980100"})


def test_alaska_shift_preserves_islands_and_holes():
    western_island = box(170, 51, 171, 52).difference(box(170.2, 51.2, 170.3, 51.3))
    mainland = box(-160, 60, -159, 61)
    output, repaired = normalize_geometry(mapping(MultiPolygon([western_island, mainland])), "02")
    value = shape(output)
    assert not repaired
    assert value.bounds == (-190.0, 51.0, -159.0, 61.0)
    assert len(value.geoms) == 2
    assert sum(len(part.interiors) for part in value.geoms) == 1
    assert value.area == pytest.approx(western_island.area + mainland.area)


def test_other_states_do_not_shift_and_invalid_display_geometry_is_reported():
    output, repaired = normalize_geometry(mapping(box(-84, 44, -83, 45)), "26")
    assert shape(output).equals(box(-84, 44, -83, 45))
    assert not repaired
    crossing = Polygon([(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)])
    output, repaired = normalize_geometry(mapping(crossing), "26")
    assert repaired and shape(output).is_valid


def test_rejects_impossible_alaska_frame():
    with pytest.raises(ValueError, match="working frame"):
        normalize_geometry(mapping(box(0, 50, 1, 51)), "02")


def test_source_identity_and_path_containment(tmp_path, monkeypatch):
    entries = []
    for kind in ("tracts", "counties", "congressional"):
        path = tmp_path / f"{kind}.zip"
        path.write_bytes(kind.encode())
        entries.append(source_metadata({"kind": kind, "path": path.name,
                                       "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size, "vintage": 2020}))
    monkeypatch.setattr("scripts.build_block_comparison_layers.SOURCES", tuple(dict(entry) for entry in entries))
    manifest = {"schemaVersion": 1, "sources": entries}
    (tmp_path / "sources.json").write_bytes(encoded(manifest))
    assert set(load_source_manifest(tmp_path)[1]) == {"tracts", "counties", "congressional"}
    (tmp_path / "tracts.zip").write_bytes(b"modified")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_source_manifest(tmp_path)
    entries[0]["path"] = "../outside.zip"
    (tmp_path / "sources.json").write_bytes(encoded(manifest))
    with pytest.raises(ValueError, match="identity or vintage"):
        load_source_manifest(tmp_path)


def test_wrong_congress_and_unpinned_sources_are_rejected(tmp_path):
    (tmp_path / "sources.json").write_bytes(encoded({"schemaVersion": 1, "sources": [{
        "kind": "congressional", "path": "cb_2026_us_cd120_500k.zip", "vintage": 2026,
    }]}))
    with pytest.raises(ValueError, match="identity or vintage"):
        load_source_manifest(tmp_path)


def test_publication_keeps_plan_assets_and_adds_separate_allowlisted_layers(tmp_path):
    builder = BundleBuilder(tmp_path)
    asset = builder.generated({"type": "FeatureCollection", "features": []}, "26-density.geojson")
    manifest = {"plans": {"26-13": {"accepted": True}}, "stateOutlines": {"url": "/existing"}}
    index = {"assets": {"existing": {"proof": "26-13"}}, "proofs": {"26-13": {"reportSha256": "a" * 64}}}
    layers = {"26": {"density": {"asset": asset}}}
    publish(tmp_path, manifest, index, builder, layers, {"sourceFilesModified": 0})
    saved_manifest = json.loads((tmp_path / OUTPUT / "manifest.json").read_bytes())
    saved_index = json.loads((tmp_path / OUTPUT / "server-index.json").read_bytes())
    assert saved_manifest["plans"] == {"26-13": {"accepted": True}}
    assert saved_manifest["stateOutlines"] == {"url": "/existing"}
    assert saved_manifest["comparisonLayers"] == layers
    assert saved_index["assets"]["existing"] == {"proof": "26-13"}
    assert saved_index["manifestSha256"] == digest((tmp_path / OUTPUT / "manifest.json").read_bytes())
    assert saved_index["assets"][asset["url"].removeprefix("/api/district-plans/")]["proof"] is None
