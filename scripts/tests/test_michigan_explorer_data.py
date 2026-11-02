"""The explorer's cards use saved residents, not cartographic area or guesswork."""
from copy import deepcopy
import gzip
import json

import pytest

from scripts.build_block_plan_bundle import BundleBuilder
from scripts.build_michigan_explorer_data import (
    city_collection, fetch_city_sources, parse_gazetteer, parse_place_populations,
    plan_summary, read_asset, summarize_county,
)


def feature(index, population, district=0, county="081"):
    return {"type": "Feature", "properties": {"geoid": f"26{county}{index:010d}",
            "population": population, "district_id": district},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 1], [0, 0]]]}}


def county(population, count, fips="081"):
    return {"fips": fips, "population": population, "blockCount": count, "bbox": [-86, 42, -85, 43]}


def test_county_percentages_use_residents_and_keep_zero_population_blocks():
    collection = {"type": "FeatureCollection", "features": [feature(1, 20), feature(2, 80, 1), feature(3, 0, 1)]}
    original = deepcopy(collection)
    result = summarize_county(collection, county(100, 3), "Kent", 2, set())
    assert collection == original
    assert result["name"] == "Kent"
    assert result["districtShares"] == [
        {"districtId": 0, "population": 20, "blockCount": 1, "percent": 20},
        {"districtId": 1, "population": 80, "blockCount": 2, "percent": 80},
    ]
    # A zero-population county remains inspectable, including districts that
    # own only zero-population blocks, without an undefined percentage.
    empty = summarize_county({"type": "FeatureCollection", "features": [feature(4, 0, 1)]}, county(0, 1), "Kent", 2, set())
    assert empty["districtShares"] == [{"districtId": 1, "population": 0, "blockCount": 1, "percent": 0}]


@pytest.mark.parametrize("change", [
    lambda row: row["properties"].update(geoid="260010000000001"),
    lambda row: row["properties"].update(geoid="bad"),
    lambda row: row["properties"].update(district_id=2),
    lambda row: row["properties"].update(district_id=-1),
    lambda row: row["properties"].update(district_id=True),
    lambda row: row["properties"].update(population=-1),
    lambda row: row["properties"].update(population=1.5),
])
def test_reject_wrong_or_invalid_saved_block(change):
    row = feature(1, 10)
    change(row)
    with pytest.raises(ValueError, match="saved block"):
        summarize_county({"type": "FeatureCollection", "features": [row]}, county(10, 1), "Kent", 2, set())


def test_duplicate_blocks_and_changed_index_totals_fail():
    row = feature(1, 10)
    with pytest.raises(ValueError, match="saved block"):
        summarize_county({"type": "FeatureCollection", "features": [row, row]}, county(20, 2), "Kent", 2, set())
    with pytest.raises(ValueError, match="reconcile"):
        summarize_county({"type": "FeatureCollection", "features": [row]}, county(11, 1), "Kent", 2, set())


@pytest.mark.parametrize("count", [13, 18, 21, 30])
def test_each_michigan_anchor_reconciles_population_and_named_counties(count):
    collection = {"type": "FeatureCollection", "features": [feature(d + 1, d, d) for d in range(count)]}
    population = sum(range(count))
    summary = summarize_county(collection, county(population, count), "Kent", count, set())
    plan = {"id": f"26-{count}", "districtCount": count, "residentPopulation": population,
            "blockCount": count, "districtPopulations": list(range(count))}
    result = plan_summary(plan, [summary])
    assert result["planId"] == plan["id"]
    assert result["counties"][0]["name"] == "Kent"
    assert all(d["countyFips"] == ["081"] and d["blockCount"] == 1 for d in result["districts"])
    with pytest.raises(ValueError, match="reconcile"):
        plan_summary({**plan, "residentPopulation": population + 1}, [summary])


GAZ = ("USPS\tGEOID\tNAME\tLSAD\tINTPTLAT\tINTPTLONG     \n"
       "MI\t2603000\tAnn Arbor city\t25\t42.276147\t-83.730860     \n"
       "MI\t2600380\tAddison village\t47\t41.985887\t-84.349076\n"
       "MI\t2600980\tAlbion city\t25\t42.247855\t-84.759191\n").encode()


def population_html(rows):
    header = ["GEOID", "STATE", "BASENAME", "NAME", "LSADC", "POP100"]
    return ("<title>Michigan 2020 Census - Data as of January 1, 2020</title><table><tr>" +
            "".join(f"<th>{h}</th>" for h in header) + "</tr>" +
            "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows) +
            "</table>").encode()


def test_city_points_join_official_names_coordinates_and_real_population():
    rows = [["2603000", "26", "Ann Arbor", "Ann Arbor city", "25", "123851"],
            ["2600380", "26", "Addison", "Addison village", "47", "20000"],
            ["2600980", "26", "Albion", "Albion city", "25", "7700"]]
    points = city_collection(parse_gazetteer(GAZ), parse_place_populations(population_html(rows)))
    assert len(points["features"]) == 1
    city = points["features"][0]
    assert city["properties"]["name"] == "Ann Arbor"
    assert city["properties"]["population"] == 123851
    assert city["properties"]["rank"] == 1
    assert city["geometry"]["coordinates"] == [-83.730860, 42.276147]
    assert "not a city boundary" in points["metadata"]["coordinateMeaning"]
    assert len(city_collection(parse_gazetteer(GAZ), parse_place_populations(population_html(rows)), minimum=0)["features"]) == 2


def test_city_source_malformed_vintage_duplicate_and_join_fail_closed():
    rows = [["2603000", "26", "Ann Arbor", "Ann Arbor city", "25", "123851"]]
    with pytest.raises(ValueError, match="vintage"):
        parse_place_populations(b"<html>An API key is required</html>")
    with pytest.raises(ValueError, match="duplicate"):
        parse_place_populations(population_html(rows + rows))
    with pytest.raises(ValueError, match="duplicate"):
        parse_gazetteer(GAZ + GAZ.splitlines()[1] + b"\n")
    with pytest.raises(ValueError, match="join mismatch"):
        city_collection({}, parse_place_populations(population_html(rows)))
    changed = parse_gazetteer(GAZ)
    changed["2603000"]["name"] = "Changed city"
    with pytest.raises(ValueError, match="join mismatch"):
        city_collection(changed, parse_place_populations(population_html(rows)))


def test_source_pin_mismatch_is_preserved_without_fetch(tmp_path):
    path = tmp_path / "2020_gaz_place_26.txt"
    path.write_bytes(b"preserved mismatch")
    with pytest.raises(ValueError, match="differs from its pin"):
        fetch_city_sources(tmp_path)
    assert path.read_bytes() == b"preserved mismatch"


def test_generated_and_input_payloads_are_bound_to_hashes(tmp_path):
    builder = BundleBuilder(tmp_path)
    expected = {"data": "saved plan"}
    asset = builder.generated(expected, "fixture-explorer-summary.json")
    index = {"assets": builder.assets}
    preserved = {}
    assert read_asset(tmp_path, tmp_path / ".cache", index, asset, preserved) == expected
    with pytest.raises(ValueError, match="allowlist"):
        read_asset(tmp_path, tmp_path / ".cache", index, {**asset, "bytes": 1}, preserved)
    target = next(iter(preserved))
    target.write_bytes(gzip.compress(json.dumps({"data": "changed"}).encode()))
    with pytest.raises(ValueError, match="hash or byte"):
        read_asset(tmp_path, tmp_path / ".cache", index, asset, preserved)
