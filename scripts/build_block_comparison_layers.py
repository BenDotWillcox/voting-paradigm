"""Build on-demand geographic context without changing any accepted district plan.

The three Census cartographic ZIPs and their SHA-256 pins live in sources.json.
2020 block population and land area are aggregated to 2020 tracts; this is an
overview choropleth, not a claim that tract or enacted boundaries nest in a plan.
Only the final manifest/index publication makes generated assets discoverable.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterable
from zipfile import ZipFile

import shapefile
from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from scripts.build_block_plan_bundle import (
    BundleBuilder, CATALOG, OUTPUT, digest, encoded, read_pinned, safe_path,
    validate_catalog,
)
from scripts.fetch_block_comparison_sources import SOURCES, source_metadata


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(2 ** 20), b""):
            result.update(chunk)
    return result.hexdigest()


def aggregate_blocks(records: Iterable[Any], state_fips: str) -> tuple[dict[str, dict], int]:
    """Aggregate exact source attributes; reject duplicate or cross-state joins."""
    tracts: dict[str, dict] = {}
    seen: set[str] = set()
    for record in records:
        geoid, population, land = record
        if not isinstance(geoid, str) or len(geoid) != 15 or not geoid.isdigit() or not geoid.startswith(state_fips):
            raise ValueError("Invalid or cross-state block GEOID")
        if geoid in seen:
            raise ValueError("Duplicate block GEOID")
        seen.add(geoid)
        if any(type(value) is not int or value < 0 for value in (population, land)):
            raise ValueError("Population and land area must be nonnegative integers")
        tract = tracts.setdefault(geoid[:11], {"population": 0, "landAreaM2": 0, "blockCount": 0})
        tract["population"] += population
        tract["landAreaM2"] += land
        tract["blockCount"] += 1
    return tracts, len(seen)


def density_properties(geoid: str, values: dict) -> dict:
    land = values["landAreaM2"]
    return {"geoid": geoid, **values,
            "densityPerKm2": values["population"] * 1_000_000 / land if land else None}


def validate_tract_join(tracts: dict[str, dict], geometry_geoids: set[str]) -> list[str]:
    extra = geometry_geoids - tracts.keys()
    if extra:
        raise ValueError(f"Tract geometry lacks block attributes: {sorted(extra)[:8]}")
    missing = sorted(tracts.keys() - geometry_geoids)
    meaningful = [key for key in missing if tracts[key]["population"] or tracts[key]["landAreaM2"]]
    if meaningful:
        raise ValueError(f"Cartographic source omits populated or land tracts: {meaningful[:8]}")
    return missing


def missing_material_tracts(tracts: dict[str, dict], geometry_geoids: set[str]) -> set[str]:
    return {key for key in tracts.keys() - geometry_geoids
            if tracts[key]["population"] or tracts[key]["landAreaM2"]}


def normalize_geometry(geometry: dict, state_fips: str) -> tuple[dict, bool]:
    """Normalize Alaska before planar validation, retaining rings and island parts."""
    def coordinates(value: Any) -> Any:
        if isinstance(value[0], (int, float)):
            x, y = value[:2]
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError("Nonfinite geographic coordinate")
            return [x - 360 if state_fips == "02" and x > 0 else x, y]
        return [coordinates(child) for child in value]
    if geometry["type"] not in ("Polygon", "MultiPolygon"):
        raise ValueError("Comparison geometry must be polygonal")
    normalized = {"type": geometry["type"], "coordinates": coordinates(geometry["coordinates"])}
    polygon = shape(normalized)
    repaired = not polygon.is_valid
    if repaired:
        polygon = make_valid(polygon)
        if polygon.geom_type == "GeometryCollection":
            polygons = [part for part in polygon.geoms if part.geom_type in ("Polygon", "MultiPolygon")]
            polygon = unary_union(polygons)
    if polygon.is_empty or not polygon.is_valid or polygon.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("Invalid comparison polygon after display-only validity repair")
    if state_fips == "02" and (polygon.bounds[0] < -240 or polygon.bounds[2] > -120):
        raise ValueError("Alaska comparison geometry escaped continuous working frame")
    return mapping(polygon), repaired


@contextmanager
def zip_reader(path: Path):
    with ZipFile(path) as archive:
        shapes = [name for name in archive.namelist() if name.endswith(".shp")]
        if len(shapes) != 1:
            raise ValueError("Expected exactly one shapefile in comparison ZIP")
        stem = shapes[0][:-4]
        # All three inputs are small cartographic national files, not block shapes.
        reader = shapefile.Reader(shp=io.BytesIO(archive.read(stem + ".shp")),
                                  shx=io.BytesIO(archive.read(stem + ".shx")),
                                  dbf=io.BytesIO(archive.read(stem + ".dbf")), encoding="utf-8")
        try:
            yield reader
        finally:
            reader.close()


def block_attributes(plan: dict, cache_root: Path) -> tuple[dict, dict]:
    state = plan["state_fips"]
    stem = f"tl_2020_{state}_tabblock20"
    relative = Path("kansas-block-benchmark/source") if state == "20" else Path("state-block-benchmark/source") / state
    source = plan["source"]
    dbf_path = safe_path(cache_root, relative / stem / (stem + ".dbf"))
    expected = source.get("extracted_file_sha256", {}).get(stem + ".dbf")
    provenance = {"stateFips": state, "path": (relative / stem / (stem + ".dbf")).as_posix(),
                  "sourceArchiveSha256": source["archive_sha256"]}
    if expected and dbf_path.exists():
        actual = file_digest(dbf_path)
        if actual != expected:
            raise ValueError(f"Block DBF hash mismatch for state {state}")
        stream: Any = dbf_path.open("rb")
    else:
        # Some historical extractions were removed to save disk; the pinned ZIP
        # remains sufficient. KS and AK pin archives rather than extracted DBFs.
        archive_path = safe_path(cache_root, relative / (stem + ".zip"))
        if file_digest(archive_path) != source["archive_sha256"]:
            raise ValueError(f"Block archive hash mismatch for state {state}")
        with ZipFile(archive_path) as archive:
            raw = archive.read(stem + ".dbf")
        actual = digest(raw)
        if expected and actual != expected:
            raise ValueError(f"Archived DBF hash mismatch for state {state}")
        stream = io.BytesIO(raw)
    provenance["dbfSha256"] = actual
    try:
        with shapefile.Reader(dbf=stream, encoding="utf-8") as reader:
            # pyshp returns selected fields in DBF declaration order, not the
            # requested order (ALAND20 precedes POP20 in TIGER). Bind by name.
            records = ((row["GEOID20"], row["POP20"], row["ALAND20"])
                       for row in reader.iterRecords(fields=["GEOID20", "POP20", "ALAND20"]))
            tracts, count = aggregate_blocks(records, state)
    finally:
        stream.close()
    population = sum(value["population"] for value in tracts.values())
    if population != plan["resident_population"] or count != plan["block_count"]:
        raise ValueError(f"Source blocks/population do not reconcile with accepted state {state}")
    provenance.update({"population": population, "blockCount": count, "tractCount": len(tracts)})
    return tracts, provenance


def fallback_tract_geometry(plan: dict, cache_root: Path, tracts: dict, requested: set[str],
                            tolerance: float = 0.0002) -> tuple[list[dict], list[dict]]:
    """Fill rare cartographic omissions using only pinned original block geometry.

    The large source SHP is streamed to a temporary file, never re-extracted into
    the preserved source directory. Only selected block shapes are constructed.
    Density still uses exact DBF land area, never the generalized display area.
    """
    if not requested:
        return [], []
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Fallback simplification tolerance must be finite and nonnegative")
    state = plan["state_fips"]
    if not requested.issubset(tracts) or any(not key.startswith(state) for key in requested):
        raise ValueError("Fallback tract does not belong to selected state attributes")
    stem = f"tl_2020_{state}_tabblock20"
    relative = Path("kansas-block-benchmark/source") if state == "20" else Path("state-block-benchmark/source") / state
    archive_path = safe_path(cache_root, relative / (stem + ".zip"))
    source = plan["source"]
    if file_digest(archive_path) != source["archive_sha256"]:
        raise ValueError("Fallback source archive hash mismatch")
    polygons: dict[str, list] = {key: [] for key in requested}
    totals = {key: {"population": 0, "landAreaM2": 0, "blockCount": 0} for key in requested}
    repairs = {key: 0 for key in requested}
    with ZipFile(archive_path) as archive, tempfile.TemporaryFile() as shp_stream:
        shp_hash = hashlib.sha256()
        with archive.open(stem + ".shp") as source_shp:
            while chunk := source_shp.read(2 ** 20):
                shp_hash.update(chunk)
                shp_stream.write(chunk)
        shp_sha256 = shp_hash.hexdigest()
        dbf_raw, shx_raw = archive.read(stem + ".dbf"), archive.read(stem + ".shx")
        dbf_sha256 = digest(dbf_raw)
        for name, actual in [(stem + ".shp", shp_sha256), (stem + ".dbf", dbf_sha256), (stem + ".shx", digest(shx_raw))]:
            expected = source.get("extracted_file_sha256", {}).get(name)
            if expected is not None and actual != expected:
                raise ValueError("Fallback extracted-member identity mismatch")
        shp_stream.seek(0)
        with shapefile.Reader(shp=shp_stream, shx=io.BytesIO(shx_raw), dbf=io.BytesIO(dbf_raw), encoding="utf-8") as reader:
            for row in reader.iterRecords(fields=["GEOID20", "POP20", "ALAND20"]):
                tract = row["GEOID20"][:11]
                if tract not in requested:
                    continue
                geometry, repaired = normalize_geometry(reader.shape(row.oid).__geo_interface__, state)
                polygons[tract].append(shape(geometry))
                repairs[tract] += repaired
                totals[tract]["population"] += row["POP20"]
                totals[tract]["landAreaM2"] += row["ALAND20"]
                totals[tract]["blockCount"] += 1
    features, provenance = [], []
    for tract in sorted(requested):
        if totals[tract] != tracts[tract] or not polygons[tract]:
            raise ValueError("Fallback blocks do not reconcile to tract attributes")
        full = unary_union(polygons[tract])
        display = full.simplify(tolerance, preserve_topology=True)
        if display.is_empty or not display.is_valid or display.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("Invalid fallback display geometry")
        geometry = mapping(display)
        features.append({"type": "Feature", "properties": {
            "geoid": tract, "name": f"Census tract {tract[5:]}", "geometrySource": "source-block-union",
        }, "geometry": geometry})
        provenance.append({"stateFips": state, "tractGeoid": tract, **totals[tract],
                           "sourceArchive": (relative / (stem + ".zip")).as_posix(),
                           "sourceArchiveSha256": source["archive_sha256"],
                           "sourceShpSha256": shp_sha256, "sourceDbfSha256": dbf_sha256,
                           "fullUnionGeometrySha256": digest(encoded(mapping(full))),
                           "displayGeometrySha256": digest(encoded(geometry)),
                           "displayValidityRepairs": repairs[tract],
                           "simplificationToleranceDegrees": tolerance,
                           "method": "union pinned source block polygons, then topology-preserving display simplification"})
    return features, provenance


def load_source_manifest(source_dir: Path) -> tuple[dict, dict[str, dict]]:
    source_path = source_dir / "sources.json"
    manifest = json.loads(source_path.read_bytes())
    if manifest.get("schemaVersion") != 1:
        raise ValueError("Unsupported comparison source manifest schema")
    specifications = {item["kind"]: source_metadata(item) for item in SOURCES}
    entries = {}
    for entry in manifest["sources"]:
        kind = entry["kind"]
        if kind in entries or kind not in ("tracts", "counties", "congressional"):
            raise ValueError("Duplicate or unknown comparison source")
        expected = specifications[kind]
        if any(entry.get(key) != expected[key] for key in ("path", "sha256", "bytes", "url", "vintage", "scale")):
            raise ValueError(f"Wrong comparison source identity or vintage: {kind}")
        path = safe_path(source_dir, entry["path"])
        if path.stat().st_size != entry["bytes"] or file_digest(path) != entry["sha256"]:
            raise ValueError(f"Comparison source hash mismatch: {kind}")
        entries[kind] = entry
    if set(entries) != {"tracts", "counties", "congressional"}:
        raise ValueError("All three pinned comparison sources are required")
    return manifest, entries


def read_geography(source_dir: Path, entries: dict, states: set[str]) -> tuple[dict, dict]:
    layers: dict[str, dict] = {state: {kind: [] for kind in entries} for state in states}
    audit: dict[str, Any] = {"displayValidityRepairs": {}, "excludedNonVotingFeatures": [], "excludedOutside50States": {}}
    for kind, entry in entries.items():
        seen: set[str] = set()
        repairs = outside = 0
        with zip_reader(safe_path(source_dir, entry["path"])) as reader:
            fields = [field[0] for field in reader.fields[1:]]
            state_field = "STATEFP20" if "STATEFP20" in fields else "STATEFP"
            geoid_field = "GEOID20" if "GEOID20" in fields else "GEOID"
            name_field = "NAME20" if "NAME20" in fields else "NAME"
            for item in reader.iterShapeRecords():
                record = item.record.as_dict()
                state, geoid = record[state_field], record[geoid_field]
                if state not in states:
                    outside += 1
                    continue
                if kind == "congressional":
                    district = record.get("CD119FP", geoid[-2:])
                    if district == "ZZ":
                        audit["excludedNonVotingFeatures"].append(geoid)
                        continue
                if geoid in seen:
                    raise ValueError(f"Duplicate comparison {kind} GEOID: {geoid}")
                seen.add(geoid)
                geometry, repaired = normalize_geometry(item.shape.__geo_interface__, state)
                repairs += repaired
                properties = {"geoid": geoid, "name": record.get(name_field, record.get("NAMELSAD", geoid))}
                if kind == "congressional":
                    properties["district"] = district
                layers[state][kind].append({"type": "Feature", "properties": properties, "geometry": geometry})
        audit["displayValidityRepairs"][kind] = repairs
        audit["excludedOutside50States"][kind] = outside
        print(f"Validated {kind} reference geometry for 50 states", flush=True)
    for state, values in layers.items():
        for kind, features in values.items():
            if not features:
                raise ValueError(f"Missing {kind} comparison coverage for {state}")
            features.sort(key=lambda feature: feature["properties"]["geoid"])
    return layers, audit


def publish(root: Path, manifest: dict, index: dict, builder: BundleBuilder, layers: dict, report: dict) -> None:
    """One publication point, reached only after all source joins and counts pass."""
    manifest["comparisonLayers"] = layers
    index["assets"].update(builder.assets)
    index["comparisonLayerProvenance"] = report
    manifest_bytes = encoded(manifest)
    index["manifestSha256"] = digest(manifest_bytes)
    for relative, data in [(OUTPUT / "comparison-report.json", encoded(report)),
                           (OUTPUT / "manifest.json", manifest_bytes),
                           (OUTPUT / "server-index.json", encoded(index))]:
        path = safe_path(root, relative)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)


def build_comparison_layers(root: Path, cache_root: Path, source_dir: Path) -> dict:
    root, cache_root, source_dir = root.resolve(), cache_root.resolve(), source_dir.resolve()
    catalog_bytes = safe_path(root, CATALOG).read_bytes()
    catalog = json.loads(catalog_bytes)
    validate_catalog(catalog)
    catalog_hash = digest(catalog_bytes)
    index = json.loads(safe_path(root, OUTPUT / "server-index.json").read_bytes())
    if index.get("catalogSha256") != catalog_hash or index.get("manifestPath") != (OUTPUT / "manifest.json").as_posix():
        raise ValueError("Comparison bundle/catalog identity differs")
    manifest = json.loads(read_pinned(root, OUTPUT / "manifest.json", index["manifestSha256"]))
    if manifest.get("catalogSha256") != catalog_hash:
        raise ValueError("Client manifest catalog identity differs")
    plans = {p["state_fips"]: p for p in catalog["plans"] if 435 in p["house_sizes"]}
    source_manifest, entries = load_source_manifest(source_dir)
    geography, audit = read_geography(source_dir, entries, set(plans))
    builder = BundleBuilder(root)
    layers = {}
    population_sources = []
    missing_water_tracts = {}
    block_derived_tracts = []
    for state, plan in sorted(plans.items()):
        tracts, provenance = block_attributes(plan, cache_root)
        population_sources.append(provenance)
        features = geography[state]
        if {feature["properties"]["geoid"] for feature in features["counties"]} != {geoid[:5] for geoid in tracts}:
            raise ValueError(f"2020 county reference does not match block county GEOIDs for {state}")
        missing = missing_material_tracts(tracts, {f["properties"]["geoid"] for f in features["tracts"]})
        if missing:
            fallback, fallback_provenance = fallback_tract_geometry(plan, cache_root, tracts, missing)
            features["tracts"].extend(fallback)
            features["tracts"].sort(key=lambda feature: feature["properties"]["geoid"])
            block_derived_tracts.extend(fallback_provenance)
        missing_water_tracts[state] = validate_tract_join(tracts, {f["properties"]["geoid"] for f in features["tracts"]})
        for feature in features["tracts"]:
            geoid = feature["properties"]["geoid"]
            feature["properties"].update(density_properties(geoid, tracts[geoid]))
        if len(features["congressional"]) != plan["district_count"]:
            raise ValueError(f"119th district count differs from 435-seat apportionment for {state}")
        layers[state] = {}
        definitions = {
            "density": ("tracts", "Population density · 2020", "People per land km², aggregated from 2020 census blocks to tracts. Zero land area is not applicable." + (" A tract omitted by the cartographic file uses a simplified union of its source blocks." if missing else ""), "2020 Census · cartographic 1:500,000"),
            "counties": ("counties", "County boundaries · 2020", "2020 counties and county equivalents; cartographic geographic reference.", "2020 Census · cartographic 1:500,000"),
            "congressional": ("congressional", "119th Congress · 2025–2026", "Serving congressional district boundaries; a 435-seat geographic reference, not a one-to-one comparison at larger House sizes.", "2025 Census · 119th Congress · cartographic 1:500,000"),
        }
        for key, (kind, label, description, vintage) in definitions.items():
            document = {"type": "FeatureCollection", "features": features[kind], "metadata": {
                "stateFips": state, "kind": key,
                "coordinateFrame": "alaska-continuous" if state == "02" else "source",
                "sourceUrl": entries[kind]["url"], "sourceSha256": entries[kind]["sha256"],
                "vintage": vintage, "displayOnly": True,
            }}
            asset = builder.generated(document, f"{state}-{key}.geojson")
            layers[state][key] = {"asset": asset, "label": label, "description": description,
                                  "sourceUrl": entries[kind]["url"], "vintage": vintage,
                                  "featureCount": len(features[kind])}
        print(f"Prepared {plan['state']}: {len(features['tracts'])} tracts, {len(features['counties'])} counties, {len(features['congressional'])} congressional districts", flush=True)
    report = {"schemaVersion": 1, "catalogSha256": catalog_hash, "stateCount": len(layers),
              "layerCount": len(builder.assets), "generatedGzipBytes": builder.generated_bytes,
              "population": sum(item["population"] for item in population_sources),
              "blockCount": sum(item["blockCount"] for item in population_sources),
              "densityMethod": "sum POP20 / (sum ALAND20 / 1,000,000) within each 2020 tract; null when land area is zero",
              "geometryNote": "Census 1:500,000 cartographic boundaries are generalized display context, not exact plan validation geometry.",
              "alaskaNote": "Positive longitudes shifted by -360 before planar validation, retaining the accepted continuous frame.",
              "sourceManifestSha256": digest((source_dir / "sources.json").read_bytes()),
              "sources": source_manifest, "populationSources": population_sources,
              "omittedZeroPopulationZeroLandTracts": missing_water_tracts,
              "blockDerivedTracts": block_derived_tracts,
              "audit": audit, "acceptedPlansModified": 0, "sourceFilesModified": 0}
    if len(layers) != 50 or len(builder.assets) != 150 or sum(len(geography[s]["congressional"]) for s in geography) != 435:
        raise ValueError("Incomplete 50-state comparison coverage")
    publish(root, manifest, index, builder, layers, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, default=os.environ.get("BLOCK_PLAN_CACHE_ROOT"))
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_comparison_layers(args.root, args.cache_root or args.root / ".cache", args.source_dir)
    print(json.dumps({key: report[key] for key in ("stateCount", "layerCount", "generatedGzipBytes", "population", "blockCount")}, indent=2))


if __name__ == "__main__":
    main()
