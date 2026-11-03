"""Add a display-only, shared 50-state boundary layer to a validated app bundle.

The union uses the full selected 435-seat district outlines before simplification,
not the separately simplified national districts. No accepted plan or source file
is changed. Alaska's selected full export already uses its continuous working
frame; this helper preserves that frame without wrapping or adding connections.

Run after build_block_plan_bundle.py. Both roots are repository roots:
  python scripts/build_block_state_outlines.py --source-root PATH --bundle-root PATH
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

from shapely import union_all
from shapely.geometry import mapping, shape

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_block_plan_bundle import (
    BundleBuilder, CATALOG, OUTPUT, digest, encoded, read_pinned, safe_path,
    validate_catalog,
)


def read_source_pinned(source_root: Path, relative: Path, expected: str, cache_root: Path | None = None) -> bytes:
    value = relative.as_posix()
    if not value.startswith(".cache/"):
        raise ValueError("Historical outlines must be under the selected cache mount")
    mount = cache_root if cache_root is not None else source_root / ".cache"
    return read_pinned(mount, value.removeprefix(".cache/"), expected)


def read_full_outlines(source_root: Path, plan: dict[str, Any], *, cache_root: Path | None = None) -> tuple[dict, dict]:
    alaska = plan["state_fips"] == "02"
    manifest_path = Path(plan["map_directory"]) / ("manifest.json" if alaska else "map-manifest.json")
    maps = json.loads(read_source_pinned(source_root, manifest_path, plan["validation"]["map_manifest_sha256"], cache_root))
    filename = maps["full_file"] if alaska else maps["district_outlines"]["full"]["gzip_path"]
    if alaska and filename != "districts-full.working.geojson.gz":
        raise ValueError("Alaska state boundary requires the continuous working export")
    metadata = plan["validation"]["payloads"][filename]
    relative = Path(plan["map_directory"]) / filename
    compressed = read_source_pinned(source_root, relative, metadata["gzip_sha256"], cache_root)
    if len(compressed) != metadata["gzip_bytes"]:
        raise ValueError("Compressed full-outline size mismatch")
    raw = gzip.decompress(compressed)
    if digest(raw) != metadata["raw_sha256"] or len(raw) != metadata["raw_bytes"]:
        raise ValueError("Decoded full-outline identity mismatch")
    collection = json.loads(raw)
    if collection.get("type") != "FeatureCollection" or len(collection["features"]) != plan["district_count"]:
        raise ValueError("Unexpected full-outline district count")
    populations = {}
    for feature in collection["features"]:
        props = feature["properties"]
        district = props["district_id"]
        if type(district) is not int or district in populations or not 0 <= district < plan["district_count"]:
            raise ValueError("Invalid or duplicate district identity")
        populations[district] = props["population"]
    if [populations[i] for i in range(plan["district_count"])] != plan["district_populations"]:
        raise ValueError("Full-outline district populations differ from selected plan")
    return collection, {
        "state_fips": plan["state_fips"], "plan_id": plan["plan_id"],
        "path": relative.as_posix(), "raw_sha256": metadata["raw_sha256"],
        "gzip_sha256": metadata["gzip_sha256"],
        "map_manifest_sha256": plan["validation"]["map_manifest_sha256"],
    }


def dissolve_state(collection: dict, state_fips: str, state_name: str, tolerance: float = 0.002) -> dict:
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Simplification tolerance must be finite and nonnegative")
    polygons = [shape(feature["geometry"]) for feature in collection["features"]]
    if not polygons or any(p.is_empty or not p.is_valid or p.geom_type not in ("Polygon", "MultiPolygon") for p in polygons):
        raise ValueError("State boundary input must contain valid, nonempty polygons")
    united = union_all(polygons)
    if united.is_empty or not united.is_valid or united.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("Dissolved state boundary is invalid")
    # Preserve holes and disconnected islands. This is display simplification,
    # not connectivity repair and not an independent administrative survey.
    display = united.simplify(tolerance, preserve_topology=True)
    if display.is_empty or not display.is_valid:
        raise ValueError("Simplified state boundary is invalid")
    return {
        "type": "Feature",
        "properties": {"state_fips": state_fips, "state_name": state_name,
                       "coordinate_frame": "alaska-continuous" if state_fips == "02" else "source"},
        "geometry": mapping(display),
    }


def build_state_outlines(source_root: Path, bundle_root: Path, tolerance: float = 0.002, *, cache_root: Path | None = None) -> dict:
    source_root, bundle_root = source_root.resolve(), bundle_root.resolve()
    source_catalog = safe_path(source_root, CATALOG).read_bytes()
    catalog = json.loads(source_catalog)
    validate_catalog(catalog)
    catalog_hash = digest(source_catalog)
    read_pinned(bundle_root, CATALOG, catalog_hash)
    index_path = safe_path(bundle_root, OUTPUT / "server-index.json")
    index = json.loads(index_path.read_bytes())
    if index.get("schemaVersion") != 1 or index.get("catalogSha256") != catalog_hash:
        raise ValueError("App bundle and source catalog differ")
    manifest_path = OUTPUT / "manifest.json"
    if index.get("manifestPath") != manifest_path.as_posix():
        raise ValueError("Unexpected app manifest path")
    manifest = json.loads(read_pinned(bundle_root, manifest_path, index["manifestSha256"]))
    if manifest.get("catalogSha256") != catalog_hash:
        raise ValueError("App manifest catalog identity differs")
    plans = sorted((p for p in catalog["plans"] if 435 in p["house_sizes"]), key=lambda p: p["state_fips"])
    if len(plans) != 50 or len({p["state_fips"] for p in plans}) != 50:
        raise ValueError("State outline layer requires all 50 unique states")
    features, sources = [], []
    for plan in plans:
        outlines, provenance = read_full_outlines(source_root, plan, cache_root=cache_root)
        features.append(dissolve_state(outlines, plan["state_fips"], plan["state"], tolerance))
        sources.append(provenance)
        print(f"Prepared {plan['state']} state boundary", flush=True)
    collection = {
        "type": "FeatureCollection", "features": features,
        "metadata": {
            "purpose": "display-only census-coverage state outlines",
            "method": "union selected full district polygons, then topology-preserving simplification",
            "simplification_tolerance_degrees": tolerance, "catalog_sha256": catalog_hash,
            "source_house_size": 435, "shared_across_house_sizes": manifest["houseSizes"],
            "alaska_note": "Selected full working-frame export retained; no antimeridian rewrapping.",
            "source_plan_ids": [item["plan_id"] for item in sources],
        },
    }
    builder = BundleBuilder(bundle_root)
    asset = builder.generated(collection, "state-outlines.geojson")
    manifest["stateOutlines"] = asset
    index["assets"].update(builder.assets)
    # Filesystem provenance remains server-only, just like the selected plan
    # report/manifest pins. The browser receives only the content-addressed URL.
    index["stateOutlineProvenance"] = {
        "catalogSha256": catalog_hash, "sourceHouseSize": 435,
        "simplificationToleranceDegrees": tolerance, "sources": sources,
    }
    manifest_bytes = encoded(manifest)
    index["manifestSha256"] = digest(manifest_bytes)
    # Generated content is immutable. Publish the manifest then its matching pin;
    # request handlers fail closed if observed between these two replacements.
    for relative, data in [(manifest_path, manifest_bytes), (OUTPUT / "server-index.json", encoded(index))]:
        path = safe_path(bundle_root, relative)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
    return {"state_count": len(features), "gzip_bytes": asset["gzipBytes"], "raw_bytes": asset["bytes"],
            "sha256": asset["sha256"], "catalog_sha256": catalog_hash, "source_files_modified": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--cache-root", type=Path, default=os.environ.get("BLOCK_PLAN_CACHE_ROOT"))
    parser.add_argument("--tolerance", type=float, default=0.002)
    args = parser.parse_args()
    print(json.dumps(build_state_outlines(args.source_root, args.bundle_root, args.tolerance, cache_root=args.cache_root), indent=2))


if __name__ == "__main__":
    main()
