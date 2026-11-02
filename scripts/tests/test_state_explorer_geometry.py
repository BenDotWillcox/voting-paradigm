"""Display rollouts keep saved populations, real islands and Alaska's frame."""
from copy import deepcopy

import pytest
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape

from scripts.build_state_explorer_geometry import prepare_layers, validate_collection


def fixture(*geometries, state="53"):
    collection = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"district_id": i, "population": 10 + i,
          "block_count": 5, "retained_custom_property": "saved"}, "geometry": mapping(geometry)}
        for i, geometry in enumerate(geometries)]}
    bounds = [min(g.bounds[0] for g in geometries), min(g.bounds[1] for g in geometries),
              max(g.bounds[2] for g in geometries), max(g.bounds[3] for g in geometries)]
    plan = {"id": f"{state}-{len(geometries)}", "stateFips": state, "districtCount": len(geometries),
            "districtPopulations": list(range(10, 10 + len(geometries))), "bbox": bounds,
            "coordinateFrame": "alaska-continuous" if state == "02" else "source"}
    return collection, plan


def test_joint_shared_edges_preserve_populations_and_do_not_draw_coast_as_divider():
    first = Polygon([(0, 0), (1, 0), (1.0005, .4), (1, 1), (0, 1)])
    second = Polygon([(1, 0), (2, 0), (2, 1), (1, 1), (1.0005, .4)])
    collection, plan = fixture(first, second)
    before = deepcopy(collection)
    layers, audit = prepare_layers(collection, plan)
    assert collection == before
    for key in ("overview", "detail"):
        assert [f["properties"] for f in layers[key]["features"]] == [f["properties"] for f in before["features"]]
        one, two = [shape(f["geometry"]) for f in layers[key]["features"]]
        assert one.intersection(two).area == 0
        assert one.boundary.intersection(two.boundary).length > 0
    shared = shape(layers["dividers"]["features"][0]["geometry"])
    coast = shape(layers["coast"]["features"][0]["geometry"])
    assert shared.intersection(coast).length == 0
    assert layers["coast"]["features"][0]["properties"]["state_fips"] == "53"
    assert audit["artificialConnectionsAdded"] == 0


def test_alaska_continuous_coordinates_and_island_holes_are_retained():
    mainland = box(-175, 55, -173, 57).difference(box(-174.8, 55.2, -174.6, 55.4))
    aleutian = box(-187, 52, -186.9, 52.1)
    collection, plan = fixture(MultiPolygon([mainland, aleutian]), state="02")
    layers, audit = prepare_layers(collection, plan)
    for key in ("overview", "detail"):
        geometry = shape(layers[key]["features"][0]["geometry"])
        assert geometry.bounds[0] < -180
        assert geometry.bounds[2] < 0
        assert len(geometry.geoms) == 2
        assert sum(len(p.interiors) for p in geometry.geoms) == 1
        assert layers[key]["metadata"]["coordinateFrame"] == "alaska-continuous"
    assert layers["dividers"]["features"] == []
    assert audit["sourceTopology"] == audit["overviewTopology"] == audit["detailTopology"]
    assert audit["coordinateWrappingApplied"] is False


def test_reject_wrapped_alaska_geometry_and_changed_population():
    collection, plan = fixture(box(-187, 52, -186, 53), state="02")
    changed = deepcopy(collection)
    changed["features"][0]["geometry"] = mapping(box(173, 52, 174, 53))
    with pytest.raises(ValueError, match="continuous longitude"):
        validate_collection(changed, plan)
    collection["features"][0]["properties"]["population"] += 1
    with pytest.raises(ValueError, match="population"):
        prepare_layers(collection, plan)


def test_corner_only_islands_do_not_gain_artificial_connectivity():
    collection, plan = fixture(box(0, 0, 1, 1), box(1, 1, 2, 2))
    layers, audit = prepare_layers(collection, plan)
    assert layers["dividers"]["features"] == []
    assert audit["sourceTopology"]["polygonParts"] == 2
    assert audit["overviewTopology"]["polygonParts"] == 2


def test_overlapping_saved_polygons_fail_instead_of_being_repaired():
    collection, plan = fixture(box(0, 0, 2, 2), box(1, 0, 3, 2))
    with pytest.raises(ValueError, match="partition is invalid"):
        prepare_layers(collection, plan)
