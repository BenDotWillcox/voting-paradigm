"""Add small spatial files of unchanged Michigan blocks beside saved county data.

Every feature remains whole and appears exactly once. Chunk bounds encompass
every source coordinate, including multipart/water extents outside the nominal
grid cell. The grid is an index, never a new district boundary or land mask.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
import gc
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.build_block_plan_bundle import (
    BundleBuilder, OUTPUT, digest, encoded, read_pinned, resource_path, safe_path,
    validate_catalog,
)
from scripts.build_michigan_explorer_data import read_asset

REPORT = OUTPUT / "michigan-spatial-blocks-report.json"
PLAN_IDS = ("26-13", "26-18", "26-21", "26-30")
GRID_DEGREES = 0.125
MAX_BLOCKS = 256
MAX_RAW_BYTES = 512 * 1024


def canonical_feature(feature: dict) -> bytes:
    """Exact JSON-value identity, independent only of dictionary key order."""
    return json.dumps(feature, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def geometry_bounds(geometry: dict) -> tuple[float, float, float, float]:
    if not isinstance(geometry, dict) or geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("Spatial chunks require saved Polygon or MultiPolygon geometry")
    polygons = geometry.get("coordinates")
    if geometry["type"] == "Polygon":
        polygons = [polygons]
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("Empty saved block geometry")
    west = south = math.inf
    east = north = -math.inf
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("Empty saved Polygon")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("Invalid saved Polygon ring")
            for point in ring:
                if (not isinstance(point, list) or len(point) < 2
                        or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)
                        or not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90):
                    raise ValueError("Invalid source coordinate")
                x, y = point[:2]
                west, south, east, north = min(west, x), min(south, y), max(east, x), max(north, y)
    if west >= east or south >= north:
        raise ValueError("Degenerate saved block bounds")
    return west, south, east, north


@dataclass(frozen=True)
class SavedBlock:
    feature: dict
    geoid: str
    population: int
    district: int
    bbox: tuple[float, float, float, float]
    raw_bytes: int
    fingerprint: str

    @property
    def center(self) -> tuple[float, float]:
        return (self.bbox[0] + self.bbox[2]) / 2, (self.bbox[1] + self.bbox[3]) / 2


def saved_blocks(collection: dict, county: dict, district_count: int, seen: set[str]) -> list[SavedBlock]:
    if collection.get("type") != "FeatureCollection" or not isinstance(collection.get("features"), list):
        raise ValueError("Saved county is not a FeatureCollection")
    records = []
    for feature in collection["features"]:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("Invalid saved Feature")
        props = feature.get("properties", {})
        geoid, population, district = props.get("geoid"), props.get("population"), props.get("district_id")
        if (not isinstance(geoid, str) or not re.fullmatch(r"26" + county["fips"] + r"\d{10}", geoid)
                or geoid in seen or type(population) is not int or population < 0
                or type(district) is not int or not 0 <= district < district_count):
            raise ValueError("Invalid, duplicate or wrong-county saved block")
        seen.add(geoid)
        records.append(SavedBlock(feature, geoid, population, district, geometry_bounds(feature.get("geometry")),
                                  len(encoded(feature)), digest(canonical_feature(feature))))
    records.sort(key=lambda block: block.geoid)
    if len(records) != county["blockCount"] or sum(b.population for b in records) != county["population"]:
        raise ValueError("Saved county population/count does not reconcile")
    return records


def union_bounds(records: list[SavedBlock]) -> list[float]:
    return [min(b.bbox[0] for b in records), min(b.bbox[1] for b in records),
            max(b.bbox[2] for b in records), max(b.bbox[3] for b in records)]


def chunk_document(plan_id: str, chunk_id: str, records: list[SavedBlock]) -> dict:
    return {"type": "FeatureCollection", "metadata": {"schemaVersion": 1, "planId": plan_id,
            "stateFips": "26", "chunkId": chunk_id, "wholeSavedBlocks": True},
            "features": [b.feature for b in records]}


def spatial_groups(records: list[SavedBlock], county_fips: str, grid: float = GRID_DEGREES,
                   max_blocks: int = MAX_BLOCKS, max_raw_bytes: int = MAX_RAW_BYTES):
    """Deterministic grid then median subdivision; broad blocks stand alone."""
    if not 0 < grid <= 1 or type(max_blocks) is not int or max_blocks < 1 or max_raw_bytes < 256:
        raise ValueError("Invalid spatial partition settings")
    cells: dict[tuple[int, int], list[SavedBlock]] = defaultdict(list)
    outliers = []
    for block in records:
        if (block.bbox[2] - block.bbox[0] > grid * 2 or block.bbox[3] - block.bbox[1] > grid * 2
                or block.raw_bytes + 512 > max_raw_bytes):
            outliers.append(block)
        else:
            x, y = block.center
            cells[(math.floor((x + 180) / grid), math.floor((y + 90) / grid))].append(block)

    def split(values: list[SavedBlock], name: str):
        # Reserve enough room for metadata, separators and a long chunk ID.
        size = sum(b.raw_bytes + 1 for b in values) + 512
        if len(values) == 1 or (len(values) <= max_blocks and size <= max_raw_bytes):
            yield name, sorted(values, key=lambda b: b.geoid)
            return
        xspan = max(b.center[0] for b in values) - min(b.center[0] for b in values)
        yspan = max(b.center[1] for b in values) - min(b.center[1] for b in values)
        axis = 0 if xspan >= yspan else 1
        ordered = sorted(values, key=lambda b: (b.center[axis], b.center[1 - axis], b.geoid))
        midpoint = len(ordered) // 2
        yield from split(ordered[:midpoint], name + "a")
        yield from split(ordered[midpoint:], name + "b")

    for (x, y), values in sorted(cells.items()):
        yield from split(values, f"c{county_fips}-g{x:04d}-{y:04d}")
    for block in sorted(outliers, key=lambda b: b.geoid):
        yield f"o{block.geoid}", [block]


def identity_digest(fingerprints: dict[str, str]) -> str:
    return digest("".join(f"{geoid}:{value}\n" for geoid, value in sorted(fingerprints.items())).encode("ascii"))


def validate_chunk(document: dict, descriptor: dict, plan_id: str, expected: dict[str, SavedBlock], seen: set[str]) -> None:
    if (document.get("type") != "FeatureCollection" or document.get("metadata", {}).get("planId") != plan_id
            or document["metadata"].get("chunkId") != descriptor["chunkId"]):
        raise ValueError("Spatial chunk plan/identity mismatch")
    values = []
    for feature in document.get("features", []):
        geoid = feature.get("properties", {}).get("geoid")
        source = expected.get(geoid)
        if source is None or geoid in seen or digest(canonical_feature(feature)) != source.fingerprint:
            raise ValueError("Spatial chunk changed, duplicated or invented a source feature")
        seen.add(geoid)
        values.append(source)
    if (not values or len(values) != descriptor["blockCount"] or sum(b.population for b in values) != descriptor["population"]
            or union_bounds(values) != descriptor["bbox"]):
        raise ValueError("Spatial chunk counts/population/full bounds do not reconcile")


def build_plan(builder: BundleBuilder, manifest: dict, server_index: dict, plan_id: str,
               accepted: dict, preserved: dict[Path, str]) -> dict:
    plan = manifest["plans"][plan_id]
    detail = read_asset(builder.root, builder.cache_root, server_index, plan["assets"]["detailIndex"], preserved)
    if detail.get("planId") != plan_id or len(detail.get("counties", [])) != 83:
        raise ValueError("Spatial source index does not describe all Michigan counties")
    if len({c["fips"] for c in detail["counties"]}) != 83:
        raise ValueError("Duplicate source county")
    source_seen: set[str] = set()
    source_fingerprints: dict[str, str] = {}
    district_populations, district_counts = [0] * plan["districtCount"], [0] * plan["districtCount"]
    chunks, counties, county_audits = [], [], []
    max_raw = max_gzip = oversized = outlier_count = 0
    for position, county in enumerate(sorted(detail["counties"], key=lambda c: c["fips"]), 1):
        collection = read_asset(builder.root, builder.cache_root, server_index, county["asset"], preserved)
        records = saved_blocks(collection, county, plan["districtCount"], source_seen)
        expected = {b.geoid: b for b in records}
        county_seen: set[str] = set()
        for block in records:
            source_fingerprints[block.geoid] = block.fingerprint
            district_populations[block.district] += block.population
            district_counts[block.district] += 1
        first = len(chunks)
        for chunk_id, values in spatial_groups(records, county["fips"]):
            document = chunk_document(plan_id, chunk_id, values)
            asset = builder.generated(document, f"{plan_id}-spatial-{chunk_id}.geojson")
            if len(values) > MAX_BLOCKS or (asset["bytes"] > MAX_RAW_BYTES and len(values) != 1):
                raise ValueError("Spatial chunk exceeded its whole-block partition limits")
            descriptor = {"chunkId": chunk_id, "bbox": union_bounds(values), "blockCount": len(values),
                          "population": sum(b.population for b in values), "asset": asset}
            # Read the published compressed bytes, not the in-memory source,
            # before proving the feature geometry/properties survived exactly.
            decoded = read_asset(builder.root, builder.cache_root, {"assets": builder.assets}, asset, {})
            validate_chunk(decoded, descriptor, plan_id, expected, county_seen)
            chunks.append(descriptor)
            max_raw, max_gzip = max(max_raw, asset["bytes"]), max(max_gzip, asset["gzipBytes"])
            oversized += asset["bytes"] > MAX_RAW_BYTES
            outlier_count += chunk_id.startswith("o")
        if county_seen != set(expected):
            raise ValueError("Spatial export lost a saved block")
        county_total = {"fips": county["fips"], "blockCount": len(records), "population": sum(b.population for b in records)}
        counties.append(county_total)
        county_audits.append({**county_total, "sourceAsset": county["asset"], "chunkCount": len(chunks) - first,
                              "canonicalFeaturesSha256": identity_digest({b.geoid: b.fingerprint for b in records})})
        if position % 10 == 0 or position == 83:
            print(f"{plan_id}: {position}/83 counties, {len(chunks)} spatial chunks", flush=True)
        del collection, records, expected
        gc.collect()
    if (len(source_seen) != plan["blockCount"] or sum(district_populations) != plan["residentPopulation"]
            or district_populations != plan["districtPopulations"]
            or district_counts != accepted["validation"]["district_block_counts"]):
        raise ValueError("Spatial data does not reconcile with accepted district populations/block counts")
    document = {"schemaVersion": 1, "planId": plan_id, "stateFips": "26", "totalBlockCount": len(source_seen),
                "totalPopulation": sum(district_populations), "counties": counties, "chunks": chunks}
    reference = builder.generated(document, f"{plan_id}-spatial-index.json")
    return {"spatialIndex": reference, "chunkCount": len(chunks), "totalBlockCount": len(source_seen),
            "totalPopulation": sum(district_populations), "districtPopulations": district_populations,
            "districtBlockCounts": district_counts, "canonicalFeaturesSha256": identity_digest(source_fingerprints),
            "maximumChunkRawBytes": max_raw, "maximumChunkGzipBytes": max_gzip,
            "oversizedSingleBlockChunks": oversized, "isolatedOutlierChunks": outlier_count,
            "totalChunkRawBytes": sum(c["asset"]["bytes"] for c in chunks),
            "totalChunkGzipBytes": sum(c["asset"]["gzipBytes"] for c in chunks), "counties": county_audits}


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def preserved_assets(root: Path, cache_root: Path, index: dict) -> dict[Path, str]:
    inventory: dict[Path, str] = {}
    for number, entry in enumerate(index["assets"].values(), 1):
        path = resource_path(root, entry["path"], cache_root)
        expected = entry["gzipSha256"]
        if path in inventory and inventory[path] != expected:
            raise ValueError("Conflicting preserved asset pins")
        if path not in inventory and (path.stat().st_size != entry["gzipBytes"] or file_hash(path) != expected):
            raise ValueError(f"Preserved asset differs from its pin: {entry['path']}")
        inventory[path] = expected
        if number % 2000 == 0:
            print(f"Pinned {number}/{len(index['assets'])} existing compressed assets", flush=True)
    return inventory


def combine_spatial(root: Path, manifest: dict, index: dict, plans: dict, assets: dict) -> tuple[dict, dict]:
    if set(plans) != set(PLAN_IDS):
        raise ValueError("Spatial publication must cover all four Michigan plans")
    updated, new_index = deepcopy(manifest), deepcopy(index)
    for plan_id, result in plans.items():
        plan = manifest["plans"][plan_id]
        reference = result["spatialIndex"]
        document = read_asset(root, root / ".cache", {"assets": assets}, reference, {})
        if (document.get("schemaVersion") != 1 or document.get("planId") != plan_id or document.get("stateFips") != "26"
                or document.get("totalBlockCount") != plan["blockCount"] or document.get("totalPopulation") != plan["residentPopulation"]
                or sum(c["blockCount"] for c in document.get("chunks", [])) != plan["blockCount"]
                or sum(c["population"] for c in document.get("chunks", [])) != plan["residentPopulation"]
                or len({c["chunkId"] for c in document["chunks"]}) != len(document["chunks"])):
            raise ValueError("Spatial index does not match its accepted plan")
        for chunk in document["chunks"]:
            key = chunk["asset"]["url"].removeprefix("/api/district-plans/")
            entry = assets.get(key)
            if entry is None or (chunk["asset"]["sha256"], chunk["asset"]["bytes"], chunk["asset"]["gzipBytes"]) != (entry["rawSha256"], entry["rawBytes"], entry["gzipBytes"]):
                raise ValueError("Spatial chunk reference is not pinned")
        updated["michiganExplorer"]["plans"][plan_id]["spatialIndex"] = reference
    for key, entry in assets.items():
        if key in new_index["assets"] and new_index["assets"][key] != entry:
            raise ValueError("Spatial publication conflicts with a preserved resource")
        new_index["assets"][key] = entry
    return updated, new_index


def build_spatial_blocks(bundle_root: Path, cache_root: Path) -> dict:
    started = time.perf_counter()
    root, cache_root = bundle_root.resolve(), cache_root.resolve()
    index_path = safe_path(root, OUTPUT / "server-index.json")
    index_raw = index_path.read_bytes()
    index = json.loads(index_raw)
    manifest_raw = read_pinned(root, OUTPUT / "manifest.json", index["manifestSha256"])
    manifest = json.loads(manifest_raw)
    catalog_raw = read_pinned(root, index["catalogPath"], index["catalogSha256"])
    catalog = json.loads(catalog_raw)
    validate_catalog(catalog)
    if manifest.get("catalogSha256") != index["catalogSha256"] or set(manifest.get("michiganExplorer", {}).get("plans", {})) != set(PLAN_IDS):
        raise ValueError("Spatial publication requires the accepted Michigan explorer")
    print("Verifying all existing registered payloads before spatial preparation", flush=True)
    preserved = preserved_assets(root, cache_root, index)
    preserved[safe_path(root, index["catalogPath"])] = digest(catalog_raw)
    for path in safe_path(root, OUTPUT).glob("*report.json"):
        if path != safe_path(root, REPORT):
            preserved[path] = file_hash(path)
    builder = BundleBuilder(root, cache_root=cache_root)
    plans = {}
    for plan_id in PLAN_IDS:
        accepted = next(p for p in catalog["plans"] if p["plan_id"] == plan_id)
        plans[plan_id] = build_plan(builder, manifest, index, plan_id, accepted, preserved)
        fragment = safe_path(root, Path(".cache/block-main-port/michigan-spatial-progress") / f"{plan_id}.json")
        fragment.parent.mkdir(parents=True, exist_ok=True)
        fragment.write_bytes(encoded({"status": "validated_plan_fragment", "planId": plan_id,
            "spatialIndex": plans[plan_id]["spatialIndex"], "audit": plans[plan_id],
            "assets": {k: v for k, v in builder.assets.items() if f"/{plan_id}-spatial-" in k}}))
        print(f"Validated isolated fragment: {fragment}", flush=True)
    updated, new_index = combine_spatial(root, manifest, index, plans, builder.assets)
    check_manifest = deepcopy(updated)
    for plan_id in PLAN_IDS:
        old = manifest["michiganExplorer"]["plans"][plan_id].get("spatialIndex")
        if old is None:
            check_manifest["michiganExplorer"]["plans"][plan_id].pop("spatialIndex")
        else:
            check_manifest["michiganExplorer"]["plans"][plan_id]["spatialIndex"] = old
    if check_manifest != manifest or any(new_index["assets"].get(k) != v for k, v in index["assets"].items()) or new_index["proofs"] != index["proofs"]:
        raise ValueError("Spatial publication changed preserved plan or asset records")
    print(f"Rehashing {len(preserved)} preserved payload/source/report files", flush=True)
    for path, expected in preserved.items():
        if file_hash(path) != expected:
            raise ValueError(f"Preserved file changed during spatial preparation: {path}")
    report = {"schemaVersion": 1, "status": "complete", "catalogSha256": index["catalogSha256"],
        "partition": {"gridDegrees": GRID_DEGREES, "maximumBlocks": MAX_BLOCKS, "maximumRawBytes": MAX_RAW_BYTES,
                      "bounds": "Full unchanged feature coordinate extent; grid centers only select storage groups",
                      "oversizePolicy": "Single whole blocks may exceed the byte cap; never clip or split a source feature"},
        "plans": plans, "assets": builder.assets, "assetCount": len(builder.assets),
        "featureIdentity": "SHA256 of sorted-key canonical complete source Feature JSON; every exported feature matches exactly once",
        "preservedAssetCount": len(index["assets"]), "preservedFileCount": len(preserved),
        "preservedPlanRecordsSha256": digest(encoded(manifest["plans"])), "preservedAssetEntriesSha256": digest(encoded(index["assets"])),
        "previousManifestSha256": digest(manifest_raw), "previousServerIndexSha256": digest(index_raw),
        "savedAssignmentsModified": 0, "solverRuns": 0, "runtimeSeconds": time.perf_counter() - started}
    report_path = safe_path(root, REPORT)
    if report_path.exists():
        prior = json.loads(report_path.read_bytes())
        for key in ("schemaVersion", "status", "catalogSha256", "partition", "plans", "assets", "featureIdentity", "savedAssignmentsModified", "solverRuns"):
            if prior.get(key) != report[key]:
                raise ValueError("Existing spatial report differs; use a new version rather than overwrite historical evidence")
        report = prior  # Preserve first-build timing and preservation history.
    report_raw = encoded(report)
    new_index["michiganSpatialBlocksProvenance"] = {"reportPath": REPORT.as_posix(), "reportSha256": digest(report_raw)}
    manifest_bytes = encoded(updated)
    new_index["manifestSha256"] = digest(manifest_bytes)
    if index_path.read_bytes() != index_raw or safe_path(root, OUTPUT / "manifest.json").read_bytes() != manifest_raw:
        raise ValueError("Another process changed the bundle during spatial preparation")
    for relative, raw in ((REPORT, report_raw), (OUTPUT / "manifest.json", manifest_bytes), (OUTPUT / "server-index.json", encoded(new_index))):
        destination = safe_path(root, relative)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(raw)
        temporary.replace(destination)
    print(json.dumps({"status": "complete", "assetCount": report["assetCount"], "runtimeSeconds": time.perf_counter() - started,
                      "report": REPORT.as_posix(), "plans": {k: v["chunkCount"] for k, v in plans.items()}}, indent=2), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, default=Path(os.environ.get("BLOCK_PLAN_CACHE_ROOT", ROOT / ".cache")))
    args = parser.parse_args()
    build_spatial_blocks(args.bundle_root, args.cache_root)


if __name__ == "__main__":
    main()
