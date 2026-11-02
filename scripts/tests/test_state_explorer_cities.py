"""Census place labels have explicit geography, vintage and population meaning."""
from copy import deepcopy
import io
import zipfile

import pytest

from scripts.build_block_plan_bundle import digest
from scripts.build_state_explorer_cities import (
    STATES, fetch_source, parse_gazetteer, parse_population_table, place_collection, source_specs,
)


def gazetteer(rows):
    header = "USPS\tGEOID\tNAME\tLSAD\tINTPTLAT\tINTPTLONG   \n"
    return (header + "".join("\t".join(row) + "\n" for row in rows)).encode()


def table(rows, *, empty=False):
    header = ["GEOID", "STATE", "BASENAME", "NAME", "LSADC", "POP100", "MTFCC"]
    body = "<tr><td>No data available</td></tr>" if empty else "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return ("<title>2020 Census - Data as of January 1, 2020</title><table><tr>" +
            "".join(f"<th>{cell}</th>" for cell in header) + "</tr>" + body + "</table>").encode()


def test_national_gazetteer_accepts_real_alphanumeric_lsad_and_excludes_territories():
    raw = gazetteer([
        ["GA", "1321017", "Cusseta-Chattahoochee County unified government", "UG", "32.347445", "-84.788021"],
        ["PR", "7200138", "Example zona urbana", "62", "18", "-66"],
    ])
    result = parse_gazetteer(raw, zipped=False)
    assert set(result) == {"1321017"}
    assert result["1321017"]["lsad"] == "UG"
    assert len(STATES) == 50 and "11" not in STATES and "72" not in STATES


@pytest.mark.parametrize("changes", [
    {0: "CA"}, {1: "bad-id"}, {3: "bad"}, {4: "nan"}, {4: "91"}, {5: "181"},
])
def test_gazetteer_rejects_wrong_state_invalid_coordinates_and_codes(changes):
    row = ["AK", "0200065", "Adak city", "25", "51.9", "-176.6"]
    for key, value in changes.items():
        row[key] = value
    with pytest.raises(ValueError):
        parse_gazetteer(gazetteer([row]), zipped=False)


def test_gazetteer_duplicate_and_archive_identity_fail_closed():
    row = ["AK", "0200065", "Adak city", "25", "51.9", "-176.6"]
    with pytest.raises(ValueError, match="duplicate"):
        parse_gazetteer(gazetteer([row, row]), zipped=False)
    compressed = io.BytesIO()
    with zipfile.ZipFile(compressed, "w") as archive:
        archive.writestr("../unexpected.txt", gazetteer([row]))
    with pytest.raises(ValueError, match="archive"):
        parse_gazetteer(compressed.getvalue())


def test_hawaii_has_valid_empty_incorporated_table_but_populated_cdps():
    assert parse_population_table(table([], empty=True), "15", "incplace") == {}
    rows = [["1571550", "15", "Urban Honolulu", "Urban Honolulu CDP", "57", "350964", "G4210"]]
    parsed = parse_population_table(table(rows), "15", "cdp")
    assert parsed["1571550"]["kind"] == "census-designated-place"
    assert parsed["1571550"]["population"] == 350964
    with pytest.raises(ValueError, match="required 2020 vintage"):
        parse_population_table(b"<title>Missing Key</title>", "15", "cdp")
    with pytest.raises(ValueError, match="duplicate"):
        parse_population_table(table(rows + rows), "15", "cdp")
    with pytest.raises(ValueError, match="wrong-state"):
        parse_population_table(table(rows), "02", "cdp")
    with pytest.raises(ValueError, match="wrong-state"):
        parse_population_table(table(rows), "15", "incplace")


def joined_fixture():
    points = parse_gazetteer(gazetteer([
        ["AK", "0200065", "Alpha city", "25", "51.9", "179.5"],
        ["AK", "0200760", "Beta CDP", "57", "60.9", "-161.4"],
        ["AK", "0201000", "Small city", "25", "62", "-150"],
    ]), zipped=False)
    populations = parse_population_table(table([
        ["0200065", "02", "Alpha", "Alpha city", "25", "10000", "G4110"],
        ["0201000", "02", "Small", "Small city", "25", "9999", "G4110"],
    ]), "02", "incplace")
    populations.update(parse_population_table(table([
        ["0200760", "02", "Beta", "Beta CDP", "57", "10000", "G4210"],
    ]), "02", "cdp"))
    return points, populations


def test_place_selection_keeps_cdp_includes_threshold_and_preserves_alaska_frame():
    coordinates, populations = joined_fixture()
    original = deepcopy(coordinates), deepcopy(populations)
    result = place_collection(coordinates, populations, "02", [])
    assert (coordinates, populations) == original
    features = result["features"]
    assert [f["properties"]["geoid"] for f in features] == ["0200065", "0200760"]
    assert [f["properties"]["rank"] for f in features] == [1, 2]
    assert features[0]["geometry"]["coordinates"] == [-180.5, 51.9]
    assert features[1]["geometry"]["coordinates"] == [-161.4, 60.9]
    assert features[1]["properties"]["kind"] == "census-designated-place"
    assert result["metadata"]["coordinateFrame"] == "alaska-continuous"
    assert "not a place boundary" in result["metadata"]["coordinateMeaning"]


def test_every_source_place_must_join_even_below_display_threshold():
    coordinates, populations = joined_fixture()
    populations.pop("0201000")  # Below 10,000, still mandatory for full join audit.
    with pytest.raises(ValueError, match="Incomplete"):
        place_collection(coordinates, populations, "02", [])
    coordinates, populations = joined_fixture()
    populations["0200065"]["name"] = "Unmatched name"
    with pytest.raises(ValueError, match="name/LSAD"):
        place_collection(coordinates, populations, "02", [])
    coordinates, populations = joined_fixture()
    populations["0200065"]["lsad"] = "57"
    with pytest.raises(ValueError, match="name/LSAD"):
        place_collection(coordinates, populations, "02", [])


@pytest.mark.parametrize("minimum", [-1, True, 1.5])
def test_invalid_population_threshold_is_rejected(minimum):
    with pytest.raises(ValueError, match="selection"):
        place_collection(*joined_fixture(), "02", [], minimum=minimum)


def test_pinned_cache_cannot_silently_refresh_or_overwrite(tmp_path, monkeypatch):
    path = tmp_path / "source.html"
    path.write_bytes(b"original")
    spec = {"filename": path.name, "url": "https://example.invalid/source", "bytes": 8, "sha256": digest(b"original")}
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: pytest.fail("Pinned cache should not fetch"))
    raw, pin = fetch_source(tmp_path, spec)
    assert raw == b"original" and pin == spec
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="differs from its pin"):
        fetch_source(tmp_path, spec)
    assert path.read_bytes() == b"changed"
    with pytest.raises(ValueError, match="Missing source pin"):
        fetch_source(tmp_path, {"filename": path.name, "url": spec["url"]})


def test_declared_sources_cover_49_states_and_leave_michigan_immutable():
    sources = source_specs()
    assert len(sources) == 99
    assert sources[0]["kind"] == "coordinates"
    assert all(source["url"].startswith("https://") and "census.gov/" in source["url"] for source in sources)
    assert "26" not in {source["stateFips"] for source in sources}
    for fips in set(STATES) - {"26"}:
        assert {source["kind"] for source in sources if source["stateFips"] == fips} == {"incplace", "cdp"}
