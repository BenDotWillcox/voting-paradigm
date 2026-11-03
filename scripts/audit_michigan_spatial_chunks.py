"""Independently verify served Michigan chunks against immutable county exports.

This audit reads only source/published assets. It never publishes or runs a
solver. Every original feature is compared, including geometry and properties.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from scripts.build_block_plan_bundle import read_pinned, resource_path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def signature(value: object) -> str:
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def audit(root: Path, cache_root: Path, base_url: str, before_dir: Path) -> dict:
    index = json.loads((root / "data/districting-block-plans/server-index.json").read_bytes())
    manifest = json.loads(read_pinned(root, index["manifestPath"], index["manifestSha256"]))
    before_manifest = json.loads((before_dir / "manifest.json").read_bytes())
    before_index = json.loads((before_dir / "server-index.json").read_bytes())
    for key in ("plans", "anchors", "landDisplays", "comparisonLayers", "catalogSha256", "stateOutlines"):
        assert manifest.get(key) == before_manifest.get(key), f"Changed saved {key}"
    assert index["proofs"] == before_index["proofs"]
    assert all(index["assets"].get(key) == value for key, value in before_index["assets"].items())
    for pin in json.loads((before_dir / "pins.json").read_bytes()):
        assert sha((root / pin["path"]).read_bytes()) == pin["sha256"], pin["path"]
    source_files = {}
    served = set()

    def load(asset: dict, http: bool = False) -> dict:
        key = asset["url"].removeprefix("/api/district-plans/")
        assert key != asset["url"]
        entry = index["assets"][key]
        if http:
            request = urllib.request.Request(base_url.rstrip("/") + asset["url"], headers={"Accept-Encoding": "gzip"})
            with urllib.request.urlopen(request, timeout=60) as response:
                assert response.status == 200 and response.headers.get("Content-Encoding") == "gzip"
                compressed = response.read()
            served.add(key)
        else:
            compressed = read_pinned(root, entry["path"], entry["gzipSha256"], cache_root)
            source_files[entry["path"]] = entry["gzipSha256"]
        raw = gzip.decompress(compressed)
        assert sha(compressed) == entry["gzipSha256"] and len(compressed) == entry["gzipBytes"]
        assert sha(raw) == entry["rawSha256"] == asset["sha256"]
        assert len(raw) == entry["rawBytes"] == asset["bytes"]
        return json.loads(raw)

    reports = []
    for plan_id in ("26-13", "26-18", "26-21", "26-30"):
        plan = manifest["plans"][plan_id]
        explorer = manifest["michiganExplorer"]["plans"][plan_id]
        assert {key: value for key, value in explorer.items() if key != "spatialIndex"} == before_manifest["michiganExplorer"]["plans"][plan_id]
        source_index = load(plan["assets"]["detailIndex"])
        spatial = load(explorer["spatialIndex"], http=True)
        assert spatial["planId"] == plan_id and spatial["stateFips"] == "26"
        expected = {}
        expected_counties = {}
        for county in source_index["counties"]:
            document = load(county["asset"])
            county_pop = 0
            for feature in document["features"]:
                props = feature["properties"]
                geoid = props["geoid"]
                assert geoid not in expected and geoid[2:5] == county["fips"]
                expected[geoid] = signature(feature)
                county_pop += props["population"]
            assert len(document["features"]) == county["blockCount"] and county_pop == county["population"]
            expected_counties[county["fips"]] = [len(document["features"]), county_pop]

        actual_counties = {}
        district_populations = [0] * plan["districtCount"]
        actual = set()
        chunks = spatial["chunks"]
        assert len({chunk["chunkId"] for chunk in chunks}) == len(chunks)

        def verify_chunk(chunk: dict) -> tuple[dict, list]:
            document = load(chunk["asset"], http=True)
            features = document["features"]
            assert len(features) == chunk["blockCount"]
            assert sum(feature["properties"]["population"] for feature in features) == chunk["population"]
            rows = []
            w, s, e, n = chunk["bbox"]
            for feature in features:
                props = feature["properties"]
                assert expected.get(props["geoid"]) == signature(feature), props["geoid"]
                geometry = feature["geometry"]
                assert geometry["type"] in ("Polygon", "MultiPolygon")
                polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
                for polygon in polygons:
                    for ring in polygon:
                        for x, y, *_ in ring:
                            assert w <= x <= e and s <= y <= n, "Chunk bbox misses source geometry"
                rows.append((props["geoid"], props["district_id"], props["population"]))
            return chunk, rows

        with ThreadPoolExecutor(max_workers=4) as pool:
            for chunk, rows in pool.map(verify_chunk, chunks):
                for geoid, district, population in rows:
                    assert geoid not in actual, f"Duplicate block {geoid}"
                    actual.add(geoid)
                    assert 0 <= district < len(district_populations)
                    district_populations[district] += population
                    totals = actual_counties.setdefault(geoid[2:5], [0, 0])
                    totals[0] += 1
                    totals[1] += population
        assert actual == expected.keys(), "Missing or extra source blocks"
        assert actual_counties == expected_counties
        assert district_populations == plan["districtPopulations"]
        assert len(actual) == spatial["totalBlockCount"] == plan["blockCount"]
        assert sum(district_populations) == spatial["totalPopulation"] == plan["residentPopulation"]
        reports.append({"planId": plan_id, "chunks": len(chunks), "uniqueBlocks": len(actual),
                        "residentPopulation": sum(district_populations), "counties": len(actual_counties),
                        "allFeatureGeometryAndPropertiesIdentical": True,
                        "gzipBytes": sum(chunk["asset"]["gzipBytes"] for chunk in chunks),
                        "rawBytes": sum(chunk["asset"]["bytes"] for chunk in chunks)})
        print(f"Verified {plan_id}: {len(chunks)} served chunks, {len(actual)} unchanged blocks", flush=True)
    for path, expected_sha in source_files.items():
        assert sha(resource_path(root, path, cache_root).read_bytes()) == expected_sha
    return {"status": "complete", "checkedAtUtc": datetime.now(timezone.utc).isoformat(), "baseUrl": base_url,
            "plans": reports, "servedAssetsVerified": len(served), "sourceAssetsRehashed": len(source_files),
            "priorAssetEntriesPreserved": len(before_index["assets"]), "all181PlanRecordsPreserved": True,
            "catalogSha256": index["catalogSha256"], "solverRuns": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:3011")
    parser.add_argument("--before-dir", type=Path, default=ROOT / ".cache/block-main-port/michigan-spatial-before")
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/block-main-port/michigan-spatial-http-audit.json")
    args = parser.parse_args()
    result = audit(args.root, args.cache_root, args.base_url, args.before_dir)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
