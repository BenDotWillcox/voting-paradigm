"""Create the app's small block-plan bundle without copying cached county geometry.

Usage: venv/Scripts/python.exe -X utf8 scripts/build_block_plan_bundle.py

The accepted final catalog pins report, map-manifest and compressed-payload hashes.
This adapter checks the reports/manifests, verifies every outline it combines, and
records exact payload identities in a server-only allowlist. Large county payloads
are checked against that allowlist when requested by the Next route. No benchmark
or source artifact is modified. To move the demo, copy this generated directory,
the final catalog, and the repo-relative files listed by server-index.json; the
full benchmark cache is unnecessary, but county files remain needed for detail.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import sys
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
HOUSE_SIZES = [435, 574, 692, 1000]
OUTPUT = Path("data/districting-block-plans")
CATALOG = Path("prompts/state-block-final-catalog.json")
HASH = re.compile(r"^[0-9a-f]{64}$")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def safe_path(root: Path, relative: str | Path) -> Path:
    value = str(relative).replace("\\", "/")
    part = PurePosixPath(value)
    if part.is_absolute() or ":" in value or any(x in ("..", ".", "") for x in value.split("/")):
        raise ValueError(f"Unsafe relative path: {value}")
    path = (root / part).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes repository: {value}")
    return path


def resource_path(root: Path, relative: str | Path, cache_root: Path | None = None) -> Path:
    value = str(relative).replace("\\", "/")
    if value.startswith(".cache/"):
        return safe_path(cache_root or root / ".cache", value[len(".cache/"):])
    return safe_path(root, relative)


def read_pinned(root: Path, relative: str | Path, expected: str, cache_root: Path | None = None) -> bytes:
    if not HASH.fullmatch(expected):
        raise ValueError("Missing or invalid expected SHA-256")
    data = resource_path(root, relative, cache_root).read_bytes()
    if digest(data) != expected:
        raise ValueError(f"Hash mismatch: {relative}")
    return data


def validate_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("status") != "complete" or catalog.get("errors"):
        raise ValueError("Only a complete error-free final catalog may be served")
    if catalog.get("house_sizes") != HOUSE_SIZES:
        raise ValueError("Expected the four approved House anchors")
    plans = catalog.get("plans", [])
    if len(plans) != 181 or catalog.get("expected_unique_plans") != 181:
        raise ValueError("The completed catalog must contain 181 unique plans")
    identities = {(p.get("state_fips"), p.get("district_count")) for p in plans}
    if len(identities) != len(plans):
        raise ValueError("Duplicate state/district-count plan")
    for p in plans:
        validation = p.get("validation", {})
        if p.get("status") != "validated" or validation.get("status") != "validated_saved_plan":
            raise ValueError(f"Unaccepted plan: {p.get('plan_id')}")
        if p.get("report_audit_errors") or validation.get("report_sha256") != p.get("report_sha256"):
            raise ValueError("Plan validation does not bind its selected report")
        if p.get("plan_id") != f"{p['state_fips']}-{p['district_count']}":
            raise ValueError("Unexpected plan identity")
        if not p.get("house_sizes") or not set(p["house_sizes"]).issubset(HOUSE_SIZES):
            raise ValueError("Plan includes an unsupported House size")
        if sum(p["district_populations"]) != p["resident_population"] or len(p["district_populations"]) != p["district_count"]:
            raise ValueError("Inconsistent saved populations")
        if not all(x == 1 for x in validation.get("policy_components", [])) or len(validation.get("policy_components", [])) != p["district_count"]:
            raise ValueError("Plan lacks validated district connectivity")
    for cap in HOUSE_SIZES:
        anchor = [p for p in plans if cap in p["house_sizes"]]
        if len(anchor) != 50 or len({p["state_fips"] for p in anchor}) != 50:
            raise ValueError(f"House {cap} is missing a unique state plan")
        if sum(p["district_count"] for p in anchor) != cap:
            raise ValueError(f"House {cap} seat counts do not sum to its anchor")


class BundleBuilder:
    def __init__(self, root: Path, output: Path = OUTPUT, cache_root: Path | None = None):
        self.root = root.resolve()
        self.cache_root = (cache_root or self.root / ".cache").resolve()
        self.output = output
        safe_path(self.root, output).mkdir(parents=True, exist_ok=True)
        self.assets: dict[str, dict[str, Any]] = {}
        self.proofs: dict[str, dict[str, str]] = {}
        self.national_features: dict[str, list[dict[str, Any]]] = {}
        self.generated_bytes = 0

    def register(self, path: Path, metadata: dict[str, Any], name: str, proof: str | None) -> dict[str, Any]:
        raw_hash = metadata["raw_sha256"]
        gzip_hash = metadata.get("gzip_sha256", metadata.get("sha256"))
        if not HASH.fullmatch(raw_hash) or not isinstance(gzip_hash, str) or not HASH.fullmatch(gzip_hash):
            raise ValueError(f"Unpinned payload: {path}")
        if not re.fullmatch(r"[a-zA-Z0-9._-]+\.(json|geojson)", name):
            raise ValueError(f"Unsafe asset name: {name}")
        resolved = resource_path(self.root, path, self.cache_root)
        if not path.as_posix().startswith((".cache/", self.output.as_posix() + "/assets/")):
            raise ValueError("Only selected cached or generated assets may be exposed")
        if resolved.stat().st_size != metadata["gzip_bytes"]:
            raise ValueError(f"Compressed payload size changed: {path}")
        if metadata["raw_bytes"] < 1 or metadata["gzip_bytes"] < 1:
            raise ValueError("Invalid payload size")
        key = f"{raw_hash}/{name}"
        entry = {
            "path": path.as_posix(), "rawSha256": raw_hash, "gzipSha256": gzip_hash,
            "rawBytes": metadata["raw_bytes"], "gzipBytes": metadata["gzip_bytes"],
            "contentType": "application/geo+json; charset=utf-8" if name.endswith(".geojson") else "application/json; charset=utf-8",
            "proof": proof,
        }
        if key in self.assets and self.assets[key]["rawSha256"] != raw_hash:
            raise ValueError("Content-address collision")
        # Identical decoded assets are interchangeable; retain the first pinned copy.
        self.assets.setdefault(key, entry)
        return {"url": f"/api/district-plans/{key}", "bytes": entry["rawBytes"], "gzipBytes": self.assets[key]["gzipBytes"], "sha256": raw_hash}

    def generated(self, value: Any, name: str) -> dict[str, Any]:
        raw = encoded(value)
        raw_hash = digest(raw)
        compressed = gzip.compress(raw, compresslevel=6, mtime=0)
        path = self.output / "assets" / f"{raw_hash}-{name}.gz"
        destination = safe_path(self.root, path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != compressed:
            raise ValueError("Existing generated content-addressed asset differs")
        if not destination.exists():
            destination.write_bytes(compressed)
        self.generated_bytes += len(compressed)
        return self.register(path, {"raw_sha256": raw_hash, "gzip_sha256": digest(compressed), "raw_bytes": len(raw), "gzip_bytes": len(compressed)}, name, None)

    def cached(self, plan: dict[str, Any], filename: str) -> dict[str, Any]:
        metadata = plan["validation"]["payloads"].get(filename)
        if metadata is None:
            raise ValueError(f"Unvalidated map resource: {filename}")
        path = Path(plan["map_directory"]) / filename
        return self.register(path, metadata, Path(filename).name.removesuffix(".gz"), plan["plan_id"])

    def decoded_cached(self, plan: dict[str, Any], filename: str) -> Any:
        metadata = plan["validation"]["payloads"][filename]
        compressed = read_pinned(self.root, Path(plan["map_directory"]) / filename, metadata["gzip_sha256"], self.cache_root)
        raw = gzip.decompress(compressed)
        if digest(raw) != metadata["raw_sha256"] or len(raw) != metadata["raw_bytes"]:
            raise ValueError("Decoded outline no longer matches the validated catalog")
        return json.loads(raw)

    def plan(self, p: dict[str, Any]) -> dict[str, Any]:
        report = json.loads(read_pinned(self.root, p["report_path"], p["report_sha256"], self.cache_root))
        if not report.get("status", "").startswith("complete"):
            raise ValueError("Selected report is not complete")
        alaska = p["state_fips"] == "02"
        manifest_path = Path(p["map_directory"]) / ("manifest.json" if alaska else "map-manifest.json")
        maps = json.loads(read_pinned(self.root, manifest_path, p["validation"]["map_manifest_sha256"], self.cache_root))
        self.proofs[p["plan_id"]] = {
            "reportPath": p["report_path"], "reportSha256": p["report_sha256"],
            "manifestPath": manifest_path.as_posix(), "manifestSha256": p["validation"]["map_manifest_sha256"],
        }
        frame = "alaska-continuous" if alaska else "source"
        bbox = report["input"]["working_bbox"] if alaska else maps["source_bbox"]
        if len(bbox) != 4 or not all(math.isfinite(x) for x in bbox):
            raise ValueError("Invalid source bounding box")
        if alaska:
            national_file = "districts-national.working.geojson.gz"
            assets = {
                "national": self.cached(p, "districts-national.wrapped.geojson.gz"),
                "state": self.cached(p, maps["state_file"]), "full": self.cached(p, maps["full_file"]),
                "connections": self.cached(p, maps["connections_file"]),
            }
            counties = [{"fips": x["county_fips"], "blockCount": x["block_count"], "population": x["population"], "asset": self.cached(p, x["working_file"])} for x in maps["counties"]]
        else:
            national_file = maps["district_outlines"]["national"]["gzip_path"]
            assets = {level: self.cached(p, maps["district_outlines"][level]["gzip_path"]) for level in ["national", "state", "full"]}
            counties = [{"fips": x["county_fips"], "blockCount": x["block_count"], "population": x["population"], "bbox": x["bbox"], "asset": self.cached(p, x["gzip_path"])} for x in maps["county_blocks"]]
            for key in ["water_connections", "exclave_connections", "recorded_connections"]:
                if key in maps:
                    assets["connections"] = self.cached(p, maps[key]["gzip_path"])
        if sum(x["population"] for x in counties) != p["resident_population"] or sum(x["blockCount"] for x in counties) != p["block_count"]:
            raise ValueError("County index does not reconcile to the selected state")
        assets["detailIndex"] = self.generated({"planId": p["plan_id"], "bbox": bbox, "coordinateFrame": frame, "counties": counties}, f"{p['plan_id']}-detail.json")
        national = self.decoded_cached(p, national_file)
        if national.get("type") != "FeatureCollection" or len(national["features"]) != p["district_count"]:
            raise ValueError("National outlines do not match district count")
        seen = set()
        for feature in national["features"]:
            props = feature["properties"]
            district = props["district_id"]
            if type(district) is not int or district in seen or not 0 <= district < p["district_count"] or props["population"] != p["district_populations"][district]:
                raise ValueError("National outline district identity/population mismatch")
            seen.add(district)
            props.update({"state_fips": p["state_fips"], "state_name": p["state"], "plan_id": p["plan_id"], "coordinate_frame": frame})
        self.national_features[p["plan_id"]] = national["features"]
        o = p["optimizer"]
        return {
            "id": p["plan_id"], "stateFips": p["state_fips"], "stateName": p["state"], "districtCount": p["district_count"], "houseSizes": p["house_sizes"],
            "residentPopulation": p["resident_population"], "blockCount": p["block_count"], "districtPopulations": p["district_populations"],
            "maxDeviationPeople": p["max_deviation_people"], "maxDeviationPercent": p["max_deviation_percent"], "populationRangePeople": p["population_range_people"],
            "connectivityPolicy": p["connectivity_policy"], "strictConnectivity": p["validation"]["all_districts_physically_connected"],
            "policyConnectivity": all(x == 1 for x in p["validation"]["policy_components"]), "recordedLinkCount": p["validation"]["recorded_link_count"],
            "coordinateFrame": frame, "bbox": bbox,
            "optimizer": {"kind": o.get("kind"), "innerPassCount": o["inner_pass_count"], "unsuccessfulInnerPassCount": o["unsuccessful_inner_pass_count"], "innerIterationCaps": o["inner_iteration_caps"], "maximumInnerIterations": o.get("maximum_inner_iterations"), "outerIterations": o.get("outer_iterations"), "centersConverged": o.get("centers_converged"), "outerIterationLimitReached": bool(o.get("outer_iteration_limit_reached"))},
            "runtimeScope": p["runtime_scope"], "pipelineSeconds": p["pipeline_seconds"], "peakMemoryBytes": p["peak_process_working_set_bytes"], "caveats": p["caveats"], "assets": assets,
        }


def build_bundle(root: Path = ROOT, catalog_path: Path = CATALOG, output: Path = OUTPUT, cache_root: Path | None = None) -> dict[str, Any]:
    catalog_bytes = safe_path(root, catalog_path).read_bytes()
    catalog = json.loads(catalog_bytes)
    validate_catalog(catalog)
    builder = BundleBuilder(root, output, cache_root)
    plans = {p["plan_id"]: builder.plan(p) for p in catalog["plans"]}
    anchors = []
    for cap in HOUSE_SIZES:
        ids = sorted(p["id"] for p in plans.values() if cap in p["houseSizes"])
        collection = {"type": "FeatureCollection", "features": [feature for plan_id in ids for feature in builder.national_features[plan_id]]}
        anchors.append({"houseSize": cap, "planIds": ids, "national": builder.generated(collection, f"house-{cap}-national.geojson")})
    manifest = {"schemaVersion": 1, "catalogSha256": digest(catalog_bytes), "generatedAt": datetime.now(timezone.utc).isoformat(), "sourceYear": 2020, "unit": "census_block", "houseSizes": HOUSE_SIZES, "anchors": anchors, "plans": plans}
    manifest_bytes = encoded(manifest)
    server_index = {"schemaVersion": 1, "catalogPath": catalog_path.as_posix(), "catalogSha256": digest(catalog_bytes), "manifestPath": (output / "manifest.json").as_posix(), "manifestSha256": digest(manifest_bytes), "proofs": builder.proofs, "assets": builder.assets}
    # Assets are content-addressed and immutable; publish the two small indexes last.
    for filename, contents in [("manifest.json", manifest_bytes), ("server-index.json", encoded(server_index))]:
        path = safe_path(root, output / filename)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(contents)
        temporary.replace(path)
    return {"plan_count": len(plans), "anchor_count": len(anchors), "asset_count": len(builder.assets), "manifest_bytes": len(manifest_bytes), "server_index_bytes": len(encoded(server_index)), "generated_gzip_bytes": builder.generated_bytes, "county_payloads_copied": 0, "national_gzip_bytes": {a["houseSize"]: a["national"]["gzipBytes"] for a in anchors}, "catalog_sha256": digest(catalog_bytes)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--cache-root", type=Path, default=Path(os.environ.get("BLOCK_PLAN_CACHE_ROOT", ROOT / ".cache")))
    parser.add_argument("--with-state-outlines", action="store_true", help="Also prepare the national state-border display layer")
    args = parser.parse_args()
    if args.with_state_outlines and (args.catalog != CATALOG or args.output != OUTPUT):
        parser.error("State outlines require the standard catalog and output paths")
    result = build_bundle(catalog_path=args.catalog, output=args.output, cache_root=args.cache_root)
    if args.with_state_outlines:
        from scripts.build_block_state_outlines import build_state_outlines
        result["state_outlines"] = build_state_outlines(ROOT, ROOT, cache_root=args.cache_root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
