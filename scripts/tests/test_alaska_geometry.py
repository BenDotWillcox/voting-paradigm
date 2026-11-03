"""Alaska frame changes preserve physical topology and whole-block ownership."""
from pathlib import Path
import zipfile

import pytest
import shapefile
from shapely.affinity import translate
from shapely.geometry import MultiPolygon, Point, Polygon, box
from shapely.geometry.polygon import orient

from scripts import alaska_geometry as adapter


def test_positive_longitudes_translate_whole_polygon_and_holes():
    original = Polygon([(170, 55), (174, 55), (174, 59), (170, 59)],
                       holes=[[(171, 56), (173, 56), (173, 58), (171, 58)]])
    actual, offset = adapter.normalize_alaska_geometry(original)
    assert offset == -360
    assert actual.equals_exact(translate(original, xoff=-360), 0)
    assert len(actual.interiors) == 1
    assert actual.area == original.area
    assert original.bounds == (170, 55, 174, 59)


def test_negative_geometry_is_unchanged():
    original = MultiPolygon([box(-178, 55, -177, 56), box(-175, 55, -174, 56)])
    actual, offset = adapter.normalize_alaska_geometry(original)
    assert actual is original
    assert offset == 0


@pytest.mark.parametrize("geometry,match", [
    (Point(-150, 60), "polygonal"),
    (Polygon(), "polygonal"),
    (box(-190, 55, -189, 56), "original longitude"),
    (box(170, 90, 171, 91), "original longitude"),
    (MultiPolygon([box(170, 55, 171, 56), box(-171, 55, -170, 56)]), "mixes longitude"),
    (Polygon([(179, 55), (-179, 55), (-179, 56), (179, 56)]), "mixes longitude"),
    (Polygon([(-150, 60), (-149, 61), (-149, 60), (-150, 61)]), "Invalid source"),
    (Polygon([(-150, 60, 0), (-149, 60, 0), (-149, 61, 0)]), "two-dimensional"),
])
def test_ambiguous_or_invalid_frames_fail_closed(geometry, match):
    with pytest.raises(ValueError, match=match):
        adapter.normalize_alaska_geometry(geometry)


def test_seam_shared_edge_requires_common_frame_without_water_edge():
    original = [box(179, 55, 180, 56), box(-180, 55, -179, 56)]
    raw_graph, _ = adapter.build_exact_part_graph(original, (0, 1))
    normalized = [adapter.normalize_alaska_geometry(part)[0] for part in original]
    graph, audit = adapter.build_exact_part_graph(normalized, (0, 1))
    assert raw_graph.adjacency == ((), ())
    assert graph.adjacency == ((1,), (0,))
    assert audit["synthetic_ownership_edges"] is False
    assert audit["edge_count"] == 1


def test_corner_gap_and_ownership_do_not_create_edges():
    parts = [box(-160, 60, -159, 61), box(-159, 61, -158, 62), box(-157, 60, -156, 61)]
    graph, audit = adapter.build_exact_part_graph(parts, (0, 0, 1))
    assert graph.adjacency == ((), (), ())
    assert graph.part_to_unit == (0, 0, 1)
    assert audit["excluded_corner_pair_count"] == 1
    assert audit["component_count"] == 3


def test_hole_enclave_shares_boundary_but_not_interior():
    outer = Polygon([(-160, 60), (-156, 60), (-156, 64), (-160, 64)],
                    holes=[[(-159, 61), (-157, 61), (-157, 63), (-159, 63)]])
    graph, _ = adapter.build_exact_part_graph([outer, box(-159, 61, -157, 63)], (0, 1))
    assert graph.adjacency == ((1,), (0,))


def test_overlap_is_rejected():
    with pytest.raises(ValueError, match="overlapping-interior"):
        adapter.build_exact_part_graph([box(-160, 60, -158, 62), box(-159, 61, -157, 63)], (0, 1))


def _archive(tmp_path: Path, rows, *, omit_field=None):
    stem = tmp_path / "tl_2020_02_tabblock20"
    with shapefile.Writer(str(stem)) as writer:
        for name in ("GEOID20", "POP20", "ALAND20", "AWATER20", "INTPTLON20", "INTPTLAT20"):
            if name != omit_field:
                writer.field(name, "C", size=30)
        for geoid, geometry, population in rows:
            parts = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
            rings = []
            for part in parts:
                part = orient(part, sign=-1)
                rings.extend([list(part.exterior.coords), *[list(ring.coords) for ring in part.interiors]])
            writer.poly(rings)
            center = geometry.representative_point()
            record = {"GEOID20":geoid,"POP20":str(population),"ALAND20":"1","AWATER20":"2",
                      "INTPTLON20":str(center.x),"INTPTLAT20":str(center.y)}
            writer.record(**{name:value for name,value in record.items() if name != omit_field})
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for suffix in (".shp", ".shx", ".dbf"):
            z.write(stem.with_suffix(suffix), stem.name + suffix)
    return archive


def test_loader_preserves_order_population_and_original_parts(tmp_path):
    archive = _archive(tmp_path, [
        ("020010001000002", MultiPolygon([box(170, 55, 171, 56), box(172, 55, 173, 56)]), 7),
        ("020010001000001", box(-150, 60, -149, 61), 0),
    ])
    before = archive.read_bytes()
    parts, rows, owners, indices, audit = adapter.load_normalized_parts(archive)
    raw, original_rows, raw_owners, _, original_audit = adapter.load_normalized_parts(archive, normalize=False)
    assert owners == raw_owners == (0, 0, 1)
    assert indices == (0, 1, 0)
    assert [row["geoid"] for row in rows] == ["020010001000002", "020010001000001"]
    assert sum(row["population"] for row in rows) == 7
    assert audit["total_population"] == 7
    assert audit["positive_longitude_population"] == 7
    assert audit["longitude_translated_block_count"] == 1
    assert original_audit["longitude_translated_block_count"] == 0
    assert rows[0]["longitude_offset_degrees"] == -360
    assert original_rows[0]["longitude_offset_degrees"] == 0
    assert parts[0].bounds == (-190, 55, -189, 56)
    assert raw[0].bounds == (170, 55, 171, 56)
    assert archive.read_bytes() == before


@pytest.mark.parametrize("rows,match", [
    ([("020010001000001", box(-150,60,-149,61), 1), ("020010001000001", box(-149,60,-148,61), 2)], "unique"),
    ([("060010001000001", box(-150,60,-149,61), 1)], "state-02"),
    ([("020010001000001", box(-150,60,-149,61), -1)], "nonnegative integer"),
    ([("020010001000001", box(-150,60,-149,61), 1.5)], "nonnegative integer"),
])
def test_loader_rejects_bad_records(tmp_path, rows, match):
    with pytest.raises(ValueError, match=match):
        adapter.load_normalized_parts(_archive(tmp_path, rows))


def test_loader_requires_population_column(tmp_path):
    archive = _archive(tmp_path, [("020010001000001", box(-150,60,-149,61),1)], omit_field="POP20")
    with pytest.raises(ValueError, match="missing or duplicate"):
        adapter.load_normalized_parts(archive)


def test_graph_rejects_omitted_or_reordered_unit_ids():
    parts = [box(-150, 60, -149, 61), box(-149, 60, -148, 61)]
    for owners in ((0,2), (1,0), (0,True)):
        with pytest.raises(ValueError):
            adapter.build_exact_part_graph(parts, owners)
