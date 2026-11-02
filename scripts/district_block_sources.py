"""Verified 2020 Census block inputs for the 50-state offline benchmark.

Resident totals come from Census apportionment Table 2 (not its overseas-inclusive
apportionment populations). Block totals come from Census geographic tallies.
All records, including water and zero-population blocks, remain in the input.
The first download establishes a local SHA-256 identity; Census publishes no
checksum here. Subsequent uses verify that identity and extracted-file hashes.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from typing import Any, Protocol
import urllib.error
import urllib.request
import zipfile

import shapefile

from districting import Unit
from scripts.precompute_state_districts import STATE_NAMES


BLOCK_COUNTS_SOURCE_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/geo_tallies2020/"
    "State_Block_Counts_2010_2020.txt"
)
RESIDENT_POPULATION_SOURCE_URL = (
    "https://www2.census.gov/programs-surveys/decennial/2020/data/"
    "apportionment/apportionment-2020-table02.pdf"
)
SOURCE_DIRECTORY_URL = "https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/"
# FIPS, resident population, all tabulation blocks. Verified against the two
# independent primary Census tables above on 2026-10-22; excludes DC/territories.
_OFFICIAL_TOTALS = """
01 5024279 185976
02 733391 28568
04 7151502 155444
05 3011524 136422
06 39538223 519723
08 5773714 140345
09 3605944 49926
10 989948 20198
12 21538187 390066
13 10711908 232717
15 1455271 14732
16 1839106 81879
17 12812508 369978
18 6785528 204568
19 3190369 175199
20 2937880 172529
21 4505836 132662
22 4657757 142874
23 1362359 47138
24 6177224 83827
25 7029917 107278
26 10077331 254730
27 5706494 198705
28 2961279 112241
29 6154913 253632
30 1084225 88417
31 1961504 119103
32 3104614 57409
33 1377529 31948
34 9288994 137972
35 2117522 107215
36 20201249 288819
37 10439388 236638
38 779094 84566
39 11799448 276428
40 3959353 180154
41 4237256 130807
42 13002700 336985
44 1097379 25649
45 5118425 146844
46 886667 71383
47 6910840 179717
48 29145505 668757
49 3271616 71207
50 643077 24611
51 8631393 163491
53 7705281 158093
54 1793716 72558
55 5893718 203059
56 576851 53769
"""
EXPECTED_RESIDENT_POPULATIONS = {
    row[0]: int(row[1]) for line in _OFFICIAL_TOTALS.splitlines() if (row := line.split())
}
EXPECTED_BLOCK_COUNTS = {
    row[0]: int(row[2]) for line in _OFFICIAL_TOTALS.splitlines() if (row := line.split())
}
_CHUNK_SIZE = 1_048_576
_EARTH_RADIUS_METERS = 6_371_000.0


class PhaseMeasurements(Protocol):
    def phase(self, name: str) -> AbstractContextManager[None]: ...


def normalize_state_fips(value: str) -> str:
    code = value.zfill(2)
    if code not in STATE_NAMES:
        raise ValueError(f"Unsupported state FIPS {value!r}; expected one of the 50 states.")
    return code


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, data: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(data, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def _download_archive(url: str, archive: Path) -> dict[str, Any]:
    """Stream with three retries; resume only with an HTTP entity validator."""
    partial = archive.with_suffix(".zip.partial")
    resume_path = archive.with_suffix(".zip.partial.json")
    received_bytes = 0
    resumed_bytes = 0
    for attempt in range(1, 4):
        prior: dict[str, Any] = {}
        if resume_path.exists():
            try:
                prior = json.loads(resume_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                prior = {}
        validator = prior.get("etag") or prior.get("last_modified")
        offset = partial.stat().st_size if partial.exists() else 0
        if prior.get("url") != url or not validator:
            offset = 0
        headers = {"User-Agent": "Nebula-Civitas-Census-Benchmark/1.0", "Accept-Encoding": "identity"}
        if offset:
            headers.update({"Range": f"bytes={offset}-", "If-Range": validator})
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=120) as response:
                status = response.status
                length = response.headers.get("Content-Length")
                expected_total: int | None = int(length) if length is not None else None
                if status == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if not offset or match is None or int(match[1]) != offset:
                        raise ValueError("Server returned an inconsistent byte-range response.")
                    expected_total = int(match[3])
                    resumed_bytes = offset
                elif status == 200:
                    offset = 0  # Server ignored Range or its entity validator changed.
                else:
                    raise ValueError(f"Unexpected source HTTP status {status}.")
                etag = response.headers.get("ETag")
                resume = {
                    "url": url, "etag": etag if etag and not etag.startswith("W/") else None,
                    "last_modified": response.headers.get("Last-Modified"),
                    "expected_bytes": expected_total,
                }
                _write_json(resume_path, resume)
                with partial.open("ab" if offset else "wb") as output:
                    for chunk in iter(lambda: response.read(_CHUNK_SIZE), b""):
                        output.write(chunk)
                        received_bytes += len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if expected_total is not None and partial.stat().st_size != expected_total:
                    raise OSError("Downloaded source length does not match the HTTP response.")
            with zipfile.ZipFile(partial) as zipped:
                if not zipped.infolist():
                    raise ValueError("Downloaded source ZIP is empty.")
            os.replace(partial, archive)
            resume_path.unlink(missing_ok=True)
            return {**resume, "attempts": attempt, "received_bytes": received_bytes,
                    "resumed_bytes": resumed_bytes}
        except (urllib.error.URLError, OSError, http.client.HTTPException, zipfile.BadZipFile) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code == 416:
                partial.unlink(missing_ok=True)
                resume_path.unlink(missing_ok=True)
            if attempt == 3:
                raise
            time.sleep(min(attempt, 2))
    raise AssertionError("Unreachable download retry state.")


def _safe_members(zipped: zipfile.ZipFile, stem: str) -> list[zipfile.ZipInfo]:
    allowed = {f"{stem}{suffix}" for suffix in (
        ".shp", ".shx", ".dbf", ".prj", ".cpg", ".shp.iso.xml", ".shp.ea.iso.xml"
    )}
    members = zipped.infolist()
    names: set[str] = set()
    for member in members:
        name = member.filename
        if (name not in allowed or name in names or member.is_dir()
                or stat.S_ISLNK(member.external_attr >> 16)):
            raise ValueError(f"Unexpected, duplicate, or unsafe source ZIP member: {name!r}.")
        names.add(name)
    required = {f"{stem}{suffix}" for suffix in (".shp", ".shx", ".dbf", ".prj")}
    if not required.issubset(names):
        raise ValueError(f"Source ZIP is missing required files: {sorted(required - names)}.")
    return members


def _extract_source(archive: Path, target: Path) -> dict[str, str]:
    """Validate every ZIP CRC before replacing any previously extracted file."""
    with zipfile.ZipFile(archive) as zipped:
        members = _safe_members(zipped, archive.stem)
        with tempfile.TemporaryDirectory(prefix=f".{archive.stem}.extract-", dir=archive.parent) as directory:
            staging = Path(directory)
            hashes: dict[str, str] = {}
            for member in members:
                digest = hashlib.sha256()
                with zipped.open(member) as source, (staging / member.filename).open("wb") as output:
                    for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
                        output.write(chunk)
                        digest.update(chunk)
                hashes[member.filename] = digest.hexdigest()
            target.mkdir(exist_ok=True)
            for member in members:
                destination = target / member.filename
                if not destination.resolve().is_relative_to(target.resolve()):
                    raise ValueError("Extracted source path escapes its state directory.")
                os.replace(staging / member.filename, destination)
    return hashes


def prepare_source(
    state_fips: str, cache: Path, measurement: PhaseMeasurements
) -> tuple[Path, dict[str, Any]]:
    """Acquire/verify a state archive and its exact extracted files inside cache."""
    state_fips = normalize_state_fips(state_fips)
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"tl_2020_{state_fips}_tabblock20.zip"
    target = cache / archive.stem
    for path in (archive, target):
        if not path.resolve().is_relative_to(cache.resolve()):
            raise ValueError("Source path escapes the specified cache directory.")
    manifest_path = archive.with_suffix(".manifest.json")
    url = SOURCE_DIRECTORY_URL + archive.name
    downloaded = not archive.exists()
    prior = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    download_metadata: dict[str, Any] | None = None
    with measurement.phase("source_acquisition"):
        if downloaded:
            download_metadata = _download_archive(url, archive)
        source_hash = sha256(archive)
        if prior is not None and (
            not isinstance(prior, dict) or prior.get("url") != url
            or prior.get("archive_sha256") != source_hash
            or prior.get("state_fips") != state_fips
        ):
            raise ValueError("Source archive identity changed from its recorded manifest.")
    with measurement.phase("source_extraction"):
        hashes = prior.get("extracted_file_sha256", {}) if prior else {}
        with zipfile.ZipFile(archive) as zipped:
            members = _safe_members(zipped, archive.stem)
            expected_names = {member.filename for member in members}
        reused = bool(hashes) and set(hashes) == expected_names
        if reused:
            reused = all(
                (target / name).is_file()
                and (target / name).resolve().is_relative_to(target.resolve())
                and sha256(target / name) == digest
                for name, digest in hashes.items()
            )
        if not reused:
            hashes = _extract_source(archive, target)
        manifest = {
            "schema": 1, "state_fips": state_fips, "state": STATE_NAMES[state_fips],
            "url": url, "archive_sha256": source_hash, "archive_bytes": archive.stat().st_size,
            "extracted_file_sha256": hashes,
            "download": download_metadata if downloaded else (prior or {}).get("download"),
            "hash_provenance": "Locally computed SHA-256; no publisher checksum is provided.",
        }
        _write_json(manifest_path, manifest)
    shapefile_path = target / f"{archive.stem}.shp"
    return shapefile_path, {
        **manifest, "archive_path": str(archive.resolve()), "extraction_dir": str(target.resolve()),
        "source_shapefile_path": str(shapefile_path.resolve()), "manifest_path": str(manifest_path.resolve()),
        "downloaded_in_timed_pipeline": downloaded, "extracted_files_reused": reused,
        "extracted_bytes": sum((target / name).stat().st_size for name in hashes),
        "crs_wkt": shapefile_path.with_suffix(".prj").read_text(encoding="utf-8"),
    }


def _nonnegative_integer(value: Any, field: str, geoid: str) -> int:
    integer = int(value)
    if integer < 0 or integer != float(value):
        raise ValueError(f"Invalid {field} for source block {geoid}.")
    return integer


def load_units(
    source: Path, state_fips: str
) -> tuple[list[Unit], dict[str, int], dict[str, Any]]:
    """Validate totals and project internal points; retain source record order.

    Equirectangular coordinates are an approximate local distance model, not an
    equal-area/geodesic projection. For longitude spans over 180 degrees, point
    longitudes are unwrapped around their population-weighted circular mean.
    This avoids a false population center near Greenwich for Alaska, but does
    not normalize polygon topology; the unchanged adjacency/export adapters
    cannot certify antimeridian-crossing states and must report that limitation.
    """
    state_fips = normalize_state_fips(state_fips)
    records: list[tuple[str, float, float, int]] = []
    populations: dict[str, int] = {}
    tracts: set[str] = set()
    water_only = 0
    with shapefile.Reader(str(source)) as reader:
        fields = {field[0] for field in reader.fields[1:]}
        required = {"GEOID20", "POP20", "INTPTLON20", "INTPTLAT20", "ALAND20", "AWATER20"}
        if not required.issubset(fields):
            raise ValueError(f"Missing source columns: {sorted(required - fields)}")
        bbox = [float(value) for value in reader.bbox]
        for row in reader.iterRecords():
            geoid = str(row["GEOID20"])
            if (len(geoid) != 15 or not geoid.isascii() or not geoid.isdigit()
                    or not geoid.startswith(state_fips) or geoid in populations):
                raise ValueError(f"Invalid, duplicate, or wrong-state GEOID: {geoid}")
            population = _nonnegative_integer(row["POP20"], "POP20", geoid)
            land = _nonnegative_integer(row["ALAND20"], "ALAND20", geoid)
            water = _nonnegative_integer(row["AWATER20"], "AWATER20", geoid)
            lon, lat = float(row["INTPTLON20"]), float(row["INTPTLAT20"])
            if not math.isfinite(lon + lat) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError(f"Invalid internal point for source block {geoid}.")
            populations[geoid] = population
            records.append((geoid, lon, lat, population))
            tracts.add(geoid[:11])
            water_only += int(land == 0 and water > 0)
    total = sum(populations.values())
    expected_population, expected_blocks = EXPECTED_RESIDENT_POPULATIONS[state_fips], EXPECTED_BLOCK_COUNTS[state_fips]
    if total != expected_population or len(records) != expected_blocks:
        raise ValueError(
            f"Source totals do not match Census for {state_fips}: "
            f"blocks={len(records)} (expected {expected_blocks}), "
            f"population={total} (expected {expected_population})."
        )
    span = bbox[2] - bbox[0]
    crosses_antimeridian = span > 180
    working_lons = [lon for _, lon, _, _ in records]
    if crosses_antimeridian:
        sine = math.fsum(math.sin(math.radians(lon)) * pop for _, lon, _, pop in records)
        cosine = math.fsum(math.cos(math.radians(lon)) * pop for _, lon, _, pop in records)
        reference = math.degrees(math.atan2(sine, cosine))
        working_lons = [reference + ((lon - reference + 180) % 360 - 180) for lon in working_lons]
    lon0 = sum(lon * record[3] for lon, record in zip(working_lons, records, strict=True)) / total
    lat0 = sum(lat * pop for _, _, lat, pop in records) / total
    x_scale = _EARTH_RADIUS_METERS * math.pi / 180 * math.cos(math.radians(lat0))
    y_scale = _EARTH_RADIUS_METERS * math.pi / 180
    units = [
        Unit(geoid, ((lon - lon0) * x_scale, (lat - lat0) * y_scale), pop)
        for lon, (geoid, _, lat, pop) in zip(working_lons, records, strict=True)
    ]
    return units, populations, {
        "state_fips": state_fips, "state": STATE_NAMES[state_fips],
        "block_count": len(records), "populated_block_count": sum(p > 0 for p in populations.values()),
        "zero_population_block_count": sum(p == 0 for p in populations.values()),
        "water_only_block_count": water_only, "tract_count": len(tracts),
        "total_population": total, "largest_block_population": max(populations.values()),
        "source_bbox": bbox, "longitude_span_degrees": span,
        "source_crosses_antimeridian": crosses_antimeridian,
        "shared_edge_antimeridian_normalization_supported": not crosses_antimeridian,
        "projection": {"kind": "population-centered-equirectangular", "lon0": lon0, "lat0": lat0,
                       "dateline_unwrapped": crosses_antimeridian,
                       "distance_model": "approximate local plane; distortion increases across broad states"},
        "location_source": "TIGER INTPT internal points, not household locations or population centroids",
        "official_totals_validated": True,
        "expected_totals": {"block_count": expected_blocks, "resident_population": expected_population},
        "block_count_source_url": BLOCK_COUNTS_SOURCE_URL,
        "resident_population_source_url": RESIDENT_POPULATION_SOURCE_URL,
    }
