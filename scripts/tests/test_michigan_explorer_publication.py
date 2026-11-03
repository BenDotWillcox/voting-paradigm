from copy import deepcopy
import json

import pytest

from scripts.build_block_plan_bundle import BundleBuilder
from scripts.build_michigan_explorer import PLAN_IDS, combine_fragments


def fixtures(tmp_path):
    builder = BundleBuilder(tmp_path)
    manifest = {
        "plans": {pid: {"stateFips": "26", "districtPopulations": [1, 2], "districtCount": 2, "residentPopulation": 3, "blockCount": 2} for pid in PLAN_IDS},
        "landDisplays": {pid: {"unchanged": True} for pid in PLAN_IDS},
        "anchors": [{"houseSize": 435}], "comparisonLayers": {"26": {"pinned": True}},
    }
    index = {"assets": {"old/resource.json": {"historical": True}}, "proofs": {"unchanged": True}}
    geometry = {"plans": {}, "assets": builder.assets}
    data = {"plans": {}, "assets": builder.assets}
    for pid in PLAN_IDS:
        lines = builder.generated({"type": "FeatureCollection", "metadata": {"planId": pid}, "features": []}, f"{pid}-lines.geojson")
        outline = builder.generated({"type": "FeatureCollection", "metadata": {"planId": pid}, "features": [{"properties": {"district_id": i, "population": i + 1}} for i in range(2)]}, f"{pid}-outline.geojson")
        geometry["plans"][pid] = {"overview": outline, **{key: lines for key in ("coast", "dividers", "detailDividers")}}
        summary = {"planId": pid, "stateFips": "26", "residentPopulation": 3, "blockCount": 2,
                   "counties": [{"fips": "001", "population": 3, "blockCount": 2}],
                   "districts": [{"districtId": i, "population": i + 1, "blockCount": 1} for i in range(2)]}
        data["plans"][pid] = {"summary": builder.generated(summary, f"{pid}-summary.json")}
    data["cities"] = builder.generated({"type": "FeatureCollection", "metadata": {"stateFips": "26"}, "features": [{"properties": {"geoid": "2612345", "population": 12345}, "geometry": {"type": "Point", "coordinates": [-85, 43]}}]}, "cities.geojson")
    return manifest, index, geometry, data


def test_publication_only_adds_new_explorer_references(tmp_path):
    manifest, index, geometry, data = fixtures(tmp_path)
    before = json.dumps([manifest, index], sort_keys=True)
    updated, new_index = combine_fragments(tmp_path, manifest, index, geometry, data)
    assert json.dumps([manifest, index], sort_keys=True) == before
    assert {k: v for k, v in updated.items() if k != "michiganExplorer"} == manifest
    assert new_index["proofs"] == index["proofs"]
    assert new_index["assets"]["old/resource.json"] == index["assets"]["old/resource.json"]
    assert set(updated["michiganExplorer"]["plans"]) == PLAN_IDS


def test_publication_rejects_incomplete_plan_coverage(tmp_path):
    manifest, index, geometry, data = fixtures(tmp_path)
    del data["plans"]["26-30"]
    with pytest.raises(ValueError, match="four accepted"):
        combine_fragments(tmp_path, manifest, index, geometry, data)


def test_publication_rejects_tampered_reference_and_resource(tmp_path):
    manifest, index, geometry, data = fixtures(tmp_path)
    tampered = deepcopy(data)
    tampered["cities"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="not pinned"):
        combine_fragments(tmp_path, manifest, index, geometry, tampered)
    entry = next(iter(geometry["assets"].values()))
    (tmp_path / entry["path"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        combine_fragments(tmp_path, manifest, index, geometry, data)


def test_publication_cannot_overwrite_preserved_asset(tmp_path):
    manifest, index, geometry, data = fixtures(tmp_path)
    key = next(iter(geometry["assets"]))
    index["assets"][key] = {"original": True}
    with pytest.raises(ValueError, match="preserved resource"):
        combine_fragments(tmp_path, manifest, index, geometry, data)


@pytest.mark.parametrize("kind", ["summary", "overview", "coast", "dividers", "detailDividers"])
def test_valid_hashed_assets_cannot_be_swapped_between_plans(tmp_path, kind):
    manifest, index, geometry, data = fixtures(tmp_path)
    target = data if kind == "summary" else geometry
    target["plans"]["26-13"][kind] = target["plans"]["26-18"][kind]
    with pytest.raises(ValueError, match="accepted plan"):
        combine_fragments(tmp_path, manifest, index, geometry, data)


def test_existing_spatial_index_survives_republishing_earlier_explorer_fragments(tmp_path):
    manifest, index, geometry, data = fixtures(tmp_path)
    builder = BundleBuilder(tmp_path)
    spatial = builder.generated({"schemaVersion": 1, "planId": "26-13", "stateFips": "26",
                                 "totalBlockCount": 2, "totalPopulation": 3}, "26-13-spatial-index.json")
    index["assets"].update(builder.assets)
    manifest["michiganExplorer"] = {"plans": {"26-13": {"spatialIndex": spatial}}}
    updated, _ = combine_fragments(tmp_path, manifest, index, geometry, data)
    assert updated["michiganExplorer"]["plans"]["26-13"]["spatialIndex"] == spatial
    manifest["michiganExplorer"]["plans"]["26-18"] = {"spatialIndex": spatial}
    with pytest.raises(ValueError, match="spatial index"):
        combine_fragments(tmp_path, manifest, index, geometry, data)
