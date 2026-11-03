"""Source integrity, independent totals, and dateline-safe point projection."""

from __future__ import annotations

from contextlib import contextmanager
import io
import math
from pathlib import Path
from typing import Any, Iterator
import zipfile

import pytest
import shapefile

from apportionment.data.apportionment_2020 import US_2020_APPORTIONMENT_POPULATIONS
from scripts import district_block_sources as sources


class Measurements:
    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        yield


def _make_source(
    directory: Path, state: str = "20", *, dateline: bool = False,
    rows: list[tuple[str, int, float, float, int, int]] | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / f"tl_2020_{state}_tabblock20.shp"
    if rows is None:
        rows = [
            (f"{state}0010001000001", 2, 179 if dateline else -99, 60 if dateline else 38, 1, 0),
            (f"{state}0010001000002", 3, -179 if dateline else -98, 60 if dateline else 39, 1, 0),
            (f"{state}0010001000003", 0, -178 if dateline else -97, 60 if dateline else 38, 0, 1),
        ]
    with shapefile.Writer(str(source)) as writer:
        writer.field("GEOID20", "C", size=15)
        writer.field("POP20", "N", size=9)
        writer.field("INTPTLON20", "C", size=20)
        writer.field("INTPTLAT20", "C", size=20)
        writer.field("ALAND20", "N", size=14)
        writer.field("AWATER20", "N", size=14)
        for geoid, population, lon, lat, land, water in rows:
            writer.poly([[(lon, lat), (lon, lat + 0.1), (lon + 0.1, lat + 0.1),
                          (lon + 0.1, lat), (lon, lat)]])
            writer.record(geoid, population, str(lon), str(lat), land, water)
    source.with_suffix(".prj").write_text("synthetic test CRS", encoding="utf-8")
    return source


def _toy_totals(monkeypatch: pytest.MonkeyPatch, state: str = "20") -> None:
    monkeypatch.setitem(sources.EXPECTED_RESIDENT_POPULATIONS, state, 5)
    monkeypatch.setitem(sources.EXPECTED_BLOCK_COUNTS, state, 3)


def _archive(cache: Path, source: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / source.with_suffix(".zip").name
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in source.parent.glob(source.stem + ".*"):
            zipped.write(path, path.name)
    return archive


def test_official_totals_cover_the_same_50_states() -> None:
    assert set(sources.EXPECTED_BLOCK_COUNTS) == set(US_2020_APPORTIONMENT_POPULATIONS)
    assert set(sources.EXPECTED_RESIDENT_POPULATIONS) == set(sources.STATE_NAMES)
    assert sum(sources.EXPECTED_RESIDENT_POPULATIONS.values()) == 331_449_281 - 689_545
    assert sum(sources.EXPECTED_BLOCK_COUNTS.values()) == 8_132_968 - 6_012
    assert sources.EXPECTED_RESIDENT_POPULATIONS["20"] == 2_937_880
    assert sources.EXPECTED_BLOCK_COUNTS["20"] == 172_529


def test_load_retains_zero_water_and_source_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _toy_totals(monkeypatch)
    units, populations, metadata = sources.load_units(_make_source(tmp_path), "20")
    assert [unit.geoid for unit in units] == list(populations)
    assert [unit.population for unit in units] == [2, 3, 0]
    assert metadata["total_population"] == 5
    assert metadata["block_count"] == 3
    assert metadata["water_only_block_count"] == 1
    assert metadata["zero_population_block_count"] == 1
    assert metadata["projection"]["lon0"] == -98.4
    assert metadata["projection"]["lat0"] == 38.6
    assert metadata["projection"]["dateline_unwrapped"] is False
    assert metadata["official_totals_validated"] is True


def test_dateline_point_projection_is_local_but_polygon_support_is_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _toy_totals(monkeypatch, "02")
    units, _, metadata = sources.load_units(_make_source(tmp_path, "02", dateline=True), "02")
    assert abs(metadata["projection"]["lon0"]) > 179
    distance = math.dist(units[0].centroid, units[1].centroid)
    assert 110_000 < distance < 113_000
    assert metadata["source_crosses_antimeridian"] is True
    assert metadata["shared_edge_antimeridian_normalization_supported"] is False


@pytest.mark.parametrize("field", ["population", "blocks"])
def test_independent_totals_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    _toy_totals(monkeypatch)
    target = sources.EXPECTED_RESIDENT_POPULATIONS if field == "population" else sources.EXPECTED_BLOCK_COUNTS
    monkeypatch.setitem(target, "20", 999)
    with pytest.raises(ValueError, match="Source totals do not match Census"):
        sources.load_units(_make_source(tmp_path), "20")


@pytest.mark.parametrize("rows", [
    [("210010001000001", 5, -98, 38, 1, 0)],
    [("200010001000001", -1, -98, 38, 1, 0)],
    [("200010001000001", 5, 181, 38, 1, 0)],
    [("200010001000001", 5, -98, 91, 1, 0)],
    [("200010001000001", 2, -98, 38, 1, 0), ("200010001000001", 3, -98, 38, 1, 0)],
])
def test_invalid_block_records_fail(tmp_path: Path, rows: Any) -> None:
    with pytest.raises(ValueError):
        sources.load_units(_make_source(tmp_path, rows=rows), "20")


def test_manifest_and_member_hashes_verify_reuse_and_repair_extraction(tmp_path: Path) -> None:
    source = _make_source(tmp_path / "fixture")
    cache = tmp_path / "cache"
    archive = _archive(cache, source)
    extracted, initial = sources.prepare_source("20", cache, Measurements())
    assert initial["downloaded_in_timed_pipeline"] is False
    assert initial["extracted_files_reused"] is False
    assert initial["archive_sha256"] == sources.sha256(archive)
    assert Path(initial["extraction_dir"]) == extracted.parent.resolve()
    assert sources.prepare_source("20", cache, Measurements())[1]["extracted_files_reused"] is True
    extracted.write_bytes(b"altered source")
    _, repaired = sources.prepare_source("20", cache, Measurements())
    assert repaired["extracted_files_reused"] is False
    assert sources.sha256(extracted) == sources.sha256(source)
    archive.write_bytes(archive.read_bytes() + b"changed archive")
    with pytest.raises(ValueError, match="archive identity changed"):
        sources.prepare_source("20", cache, Measurements())


@pytest.mark.parametrize("name", ["../escape.shp", "C:/escape.shp", "other.shp"])
def test_unsafe_archive_members_fail_before_extraction(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "tl_2020_20_tabblock20.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(name, b"invalid")
    with pytest.raises(ValueError, match="unsafe source ZIP member"):
        sources.prepare_source("20", tmp_path, Measurements())


class Response(io.BytesIO):
    def __init__(self, data: bytes, status: int, headers: dict[str, str], *, fail_after: int | None = None):
        super().__init__(data)
        self.status = status
        self.headers = headers
        self.fail_after = fail_after

    def read(self, size: int = -1) -> bytes:
        if self.fail_after is not None and self.tell() >= self.fail_after:
            raise OSError("interrupted transfer")
        return super().read(size)


@pytest.mark.parametrize("supports_range", [True, False])
def test_interrupted_download_resumes_or_restarts_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, supports_range: bool
) -> None:
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w") as zipped:
        zipped.writestr("test.txt", b"sample payload")
    data = memory.getvalue()
    calls: list[Any] = []

    def urlopen(request: Any, timeout: int) -> Response:
        calls.append(request)
        if len(calls) == 1:
            return Response(data, 200, {"Content-Length": str(len(data)), "ETag": '"v1"'}, fail_after=8)
        assert request.get_header("Range") == "bytes=8-"
        assert request.get_header("If-range") == '"v1"'
        if supports_range:
            return Response(data[8:], 206, {
                "Content-Length": str(len(data) - 8), "ETag": '"v1"',
                "Content-Range": f"bytes 8-{len(data) - 1}/{len(data)}",
            })
        return Response(data, 200, {"Content-Length": str(len(data)), "ETag": '"v2"'})

    monkeypatch.setattr(sources.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(sources.time, "sleep", lambda _: None)
    monkeypatch.setattr(sources, "_CHUNK_SIZE", 8)
    archive = tmp_path / "download.zip"
    result = sources._download_archive("https://example.test/source.zip", archive)
    assert archive.read_bytes() == data
    assert result["attempts"] == 2
    assert not archive.with_suffix(".zip.partial").exists()
    assert not archive.with_suffix(".zip.partial.json").exists()


def test_fips_normalization_rejects_dc_and_territories() -> None:
    assert sources.normalize_state_fips("1") == "01"
    for value in ("11", "72", "00", "../20"):
        with pytest.raises(ValueError):
            sources.normalize_state_fips(value)
