"""Regression tests for additive, source-pinned nationwide land displays."""
from copy import deepcopy
import hashlib
import io
import struct
from zipfile import ZipFile

import numpy as np
import pytest
import shapefile
from shapely.geometry import MultiPolygon, Polygon, box, mapping

from scripts.build_state_land_display import (
    prepare_land_layers, source_attributes, source_bounds, source_reader,
    verify_fragment, working_geometry,
)
from scripts.build_michigan_land_display import checked_assignments, remove_water_only


def feature(district, geometry, population):
    return {"type": "Feature", "properties": {"district_id": district, "population": population}, "geometry": mapping(geometry)}


def plan(state="44", count=2, frame="source", bbox=None):
    return {"id": f"{state}-{count}", "stateFips": state, "districtCount": count,
            "districtPopulations": [11, 17][:count], "coordinateFrame": frame, "bbox": bbox or [0, 0, 4, 2]}


def test_clean_overview_preserves_ownership_and_labels_generic_state():
    full = {"type": "FeatureCollection", "features": [feature(0, box(0, 0, 2, 2), 11), feature(1, box(2, 0, 4, 2), 17)]}
    # Shared small enclosed water hole, plus an open coastline inlet.
    water = {2: box(1.999, .5, 2, .51), 3: box(2, .5, 2.001, .51), 4: box(0, 1, .1, 1.1)}
    exact, _ = remove_water_only(full, water, np.array([0, 1, 0, 1, 0]))
    before = deepcopy(full)
    layers, audit = prepare_land_layers(exact, full, plan())
    assert full == before
    assert audit["overview"]["suppressed_water_holes"] == 1
    assert audit["overview"]["open_channels_unchanged"]
    for name, collection in layers.items():
        assert collection["metadata"]["coverage"] == "land-focused"
        assert collection["metadata"]["stateFips"] == "44"
        assert collection["metadata"]["planId"] == "44-2"
    assert layers["coast"]["features"][0]["properties"]["state_fips"] == "44"
    assert layers["dividers"]["features"][0]["properties"]["district_ids"] == [0, 1]
    assert [f["properties"] for f in layers["detail"]["features"]] == [f["properties"] for f in full["features"]]


def test_all_water_district_is_rejected_instead_of_omitted():
    full = {"type": "FeatureCollection", "features": [feature(0, box(0, 0, 1, 1), 11)]}
    exact, _ = remove_water_only(full, {0: box(0, 0, 1, 1)}, np.array([0]))
    with pytest.raises(ValueError, match="only hidden water"):
        prepare_land_layers(exact, full, plan(count=1))


def test_alaska_uses_continuous_geometry_and_preserves_islands():
    raw = MultiPolygon([box(-160, 50, -159, 51), box(175, 51, 176, 52)])
    continuous = working_geometry(raw, "alaska-continuous")
    assert continuous.bounds == (-185, 50, -159, 52)
    assert len(continuous.geoms) == 2
    assert raw.bounds == (-160, 50, 176, 52)
    full = {"type": "FeatureCollection", "features": [feature(0, continuous, 11)]}
    layers, audit = prepare_land_layers(full, full, plan("02", 1, "alaska-continuous", [-186, 49, -158, 53]))
    assert all(layer["metadata"]["coordinateFrame"] == "alaska-continuous" for layer in layers.values())
    assert audit["coordinateWrappingApplied"] is False
    with pytest.raises(ValueError, match="frame"):
        prepare_land_layers(full, full, plan("02", 1, "alaska-continuous", [-180, 49, -158, 53]))


def test_mixed_land_water_and_hidden_water_population_remain_in_saved_statistics():
    geoids = ["440010000000001", "440010000000002", "440010000000003"]
    accepted = {"district_count": 1, "district_populations": [35], "validation": {"district_block_counts": [3]}}
    populations = np.array([20, 11, 4])
    checkpoint = {"assignments": dict.fromkeys(geoids, 0)}
    assignments = checked_assignments(accepted, checkpoint, geoids, populations)
    full = {"type": "FeatureCollection", "features": [feature(0, box(0, 0, 3, 1), 35)]}
    hidden, _ = remove_water_only(full, {1: box(1, 0, 2, 1)}, assignments)
    assert hidden["features"][0]["properties"]["population"] == 35
    assert hidden["features"][0]["geometry"]["type"] == "MultiPolygon"
    bad = deepcopy(checkpoint)
    bad["assignments"][geoids[0]] = True
    with pytest.raises(ValueError, match="assignment"):
        checked_assignments(accepted, bad, geoids, populations)


def write_archive(path, state, polygons):
    pieces = {key: io.BytesIO() for key in ("shp", "shx", "dbf")}
    writer = shapefile.Writer(shp=pieces["shp"], shx=pieces["shx"], dbf=pieces["dbf"])
    writer.field("GEOID20", "C", 15)
    writer.field("POP20", "N", 12, 0)
    writer.field("ALAND20", "N", 16, 0)
    for index, geometry in enumerate(polygons):
        writer.shape(mapping(geometry))
        writer.record(f"{state}{index:013}", index + 1, 0 if index == 0 else 10)
    writer.close()
    data = {f"tl_2020_{state}_tabblock20.{suffix}": value.getvalue() for suffix, value in pieces.items()}
    with ZipFile(path, "w") as archive:
        for name, value in data.items():
            archive.writestr(name, value)
    return {"archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "archive_bytes": path.stat().st_size,
            "extracted_file_sha256": {name: hashlib.sha256(value).hexdigest() for name, value in data.items()}}


def test_source_archive_pins_and_bbox_candidates(tmp_path):
    path = tmp_path / "source.zip"
    source = write_archive(path, "44", [box(0, 0, 1, 1), box(1, 0, 2, 1)])
    with source_reader(path, source, "44") as (reader, shp, shx):
        geoids, pop, land = source_attributes(reader, "44")
        assert len(geoids) == 2 and pop.tolist() == [1, 2] and land.tolist() == [0, 10]
        assert source_bounds(shp, shx, 2, lambda i: None, "source") == [(0, 0, 1, 1), (1, 0, 2, 1)]
        corrupted = bytearray(shx)
        struct.pack_into(">i", corrupted, 104, 100)
        with pytest.raises(ValueError, match="record identity"):
            source_bounds(shp, corrupted, 2, lambda i: None, "source")
    wrong = {**source, "archive_sha256": "0" * 64}
    with pytest.raises(ValueError, match="archive identity"):
        with source_reader(path, wrong, "44"):
            pass
    # Alaska's historical catalog pins the complete zip, without extracted pins.
    minimal = {"archive_sha256": source["archive_sha256"]}
    with source_reader(path, minimal, "44") as (reader, _, _):
        with pytest.raises(ValueError, match="GEOID"):
            source_attributes(reader, "02")


def test_stale_or_unexplained_fragment_is_not_reused(tmp_path):
    identity = {"baseBundle": {"manifestSha256": "original"}}
    with pytest.raises(ValueError, match="identity differs"):
        verify_fragment(tmp_path, tmp_path, {"status": "complete", "identity": {}}, identity)
    with pytest.raises(ValueError, match="unexplained"):
        verify_fragment(tmp_path, tmp_path, {"status": "complete", "identity": identity, "audit": {"waterPaths": {"all_components_explained": False}}}, identity)
