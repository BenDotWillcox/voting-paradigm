"""Publish additive land displays only after all accepted state plans validate.

Saved plans, evidence, original census assets and block inspection stay pinned.
National display layers are bundled by anchor to bound browser requests.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time

from shapely import STRtree
from shapely.geometry import LineString, Polygon, shape

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.build_block_plan_bundle import BundleBuilder, OUTPUT, digest, encoded, read_pinned, resource_path, safe_path
from scripts.build_state_explorer_geometry import validate_collection
from scripts.publish_state_explorer import atomic_json, file_hash, merge_assets, read_reference, validate_anchors, validate_assets

NAMESPACE = OUTPUT / "state-land-display-v1"
REPORT = NAMESPACE / "publication.json"
GEOMETRY_KEYS = {"overview", "detail", "coast", "dividers", "detailDividers", "coverage", "coordinateFrame"}


def classify_coast(document: dict) -> tuple[dict, dict]:
    """Keep only top-level shorelines prominent, including for islands in lakes.

    Dissolved rings are disjoint or nested. Index their bounding boxes before
    exact containment, avoiding the quadratic browser test on Alaska's coast.
    This changes styling metadata only; every coordinate is retained.
    """
    rings, properties = [], []
    for feature in document["features"]:
        geometry = feature["geometry"]
        lines = [geometry["coordinates"]] if geometry["type"] == "LineString" else geometry["coordinates"]
        if geometry["type"] not in ("LineString", "MultiLineString"):
            raise ValueError("Coast must contain dissolved closed lines")
        for line in lines:
            if len(line) < 4 or line[0] != line[-1]:
                raise ValueError("Coast ring is open or degenerate")
            polygon = Polygon(line)
            if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
                raise ValueError("Coast ring is invalid")
            rings.append(polygon)
            properties.append((deepcopy(feature["properties"]), deepcopy(line)))
    tree = STRtree(rings)
    counts = {"outer": 0, "inland": 0}
    features = []
    for i, polygon in enumerate(rings):
        scope = "outer"
        boundary = LineString(properties[i][1])
        for raw_j in tree.query(polygon):
            j = int(raw_j)
            if i == j:
                continue
            other = rings[j]
            if polygon.equals(other):
                raise ValueError("Coast contains duplicate rings")
            if other.area > polygon.area and other.covers(boundary):
                scope = "inland"
                break
        counts[scope] += 1
        props, line = properties[i]
        features.append({"type": "Feature", "properties": {**props, "shoreline_scope": scope},
                         "geometry": {"type": "LineString", "coordinates": line}})
    return {**deepcopy(document), "features": features,
            "metadata": {**document.get("metadata", {}), "shorelineClassification": "top-level-containment-v1"}}, counts


def annotated_features(document: dict, plan: dict) -> list[dict]:
    features = deepcopy(document["features"])
    for feature in features:
        feature.setdefault("properties", {}).update({"state_fips": plan["stateFips"],
            "plan_id": plan["id"], "coordinate_frame": plan["coordinateFrame"]})
    return features


def assert_preserved(before: dict, after: dict) -> None:
    """Reject edits to memberships, census views, cities or block inspection."""
    for key, value in before.items():
        if key not in {"stateExplorers", "landDisplays", "landAnchors"} and after.get(key) != value:
            raise ValueError(f"Preserved manifest field changed: {key}")
    for plan_id, value in before.get("landDisplays", {}).items():
        if after["landDisplays"].get(plan_id) != value:
            raise ValueError("Existing Michigan land display changed")
    for state, original in before["stateExplorers"].items():
        updated = after["stateExplorers"][state]
        if {k: v for k, v in original.items() if k != "plans"} != {k: v for k, v in updated.items() if k != "plans"}:
            raise ValueError("City or state explorer metadata changed")
        if set(original["plans"]) != set(updated["plans"]):
            raise ValueError("Explorer plan membership changed")
        for plan_id, record in original["plans"].items():
            changed = updated["plans"][plan_id]
            if state == "26" and changed != record:
                raise ValueError("Michigan explorer changed")
            for key, value in record.items():
                if key not in GEOMETRY_KEYS and changed.get(key) != value:
                    raise ValueError(f"Block inspection reference changed: {plan_id}/{key}")
            if state != "26" and changed.get("censusOverview") != record.get("censusOverview", record["overview"]):
                raise ValueError("Original continuous census overview was not retained")


def publish(root: Path, cache: Path, *, write: bool = False) -> dict:
    started = time.perf_counter()
    root, cache = root.resolve(), cache.resolve()
    index_path = safe_path(root, OUTPUT / "server-index.json")
    before_index = index_path.read_bytes()
    index = json.loads(before_index)
    before_manifest = read_pinned(root, OUTPUT / "manifest.json", index["manifestSha256"])
    manifest = json.loads(before_manifest)
    catalog = json.loads(read_pinned(root, index["catalogPath"], index["catalogSha256"], cache))
    accepted_plans = {p["plan_id"]: p for p in catalog["plans"]}
    states = validate_anchors(manifest)
    updated = deepcopy(manifest)
    assets = dict(index["assets"])
    additions, preserved, inputs, checks = {}, {}, [], {}
    frozen_runtime = None
    for state in states:
        if state == "26":
            continue
        relative = NAMESPACE / "states" / f"{state}.json"
        raw = safe_path(root, relative).read_bytes()
        fragment = json.loads(raw)
        expected = {key for key, plan in manifest["plans"].items() if plan["stateFips"] == state}
        if (fragment.get("status") != "complete" or fragment.get("catalogSha256") != index["catalogSha256"]
                or set(fragment["landDisplays"]) != expected or set(fragment["geometryPlans"]) != expected):
            raise ValueError(f"Incomplete or mismatched land fragment: {state}")
        if (fragment.get("baseManifestSha256") != digest(before_manifest)
                or fragment.get("baseIndexSha256") != digest(before_index)):
            raise ValueError("Land fragment was built against different app metadata")
        runtime = fragment["audit"]["runtimeHashes"]
        if not runtime or (frozen_runtime is not None and runtime != frozen_runtime):
            raise ValueError("Mixed or missing land-builder runtime identities")
        frozen_runtime = runtime
        for relative_runtime, sha in runtime.items():
            if file_hash(safe_path(root, relative_runtime)) != sha:
                raise ValueError(f"Frozen land-builder runtime changed: {relative_runtime}")
        inputs.append({"path": relative.as_posix(), "sha256": digest(raw)})
        merge_assets(additions, fragment["assets"])
        merge_assets(assets, fragment["assets"])
        source_files = [item for audit in fragment["audit"]["plans"].values() for item in audit["preservedFiles"]]
        for item in source_files:
            if item["path"] in preserved and preserved[item["path"]] != item["sha256"]:
                raise ValueError("Conflicting preserved source identity")
            preserved[item["path"]] = item["sha256"]
        for plan_id in sorted(expected):
            plan = manifest["plans"][plan_id]
            audit = fragment["audit"]["plans"][plan_id]
            accepted = accepted_plans[plan_id]
            if (audit["waterPaths"].get("all_components_explained") is not True
                    or audit["residentPopulation"] != plan["residentPopulation"]
                    or audit["blockCount"] != plan["blockCount"]
                    or audit["recordedLinkCount"] != plan["recordedLinkCount"]
                    or audit["recordedConnectionsSha256"] != plan["assets"].get("connections", {}).get("sha256")):
                raise ValueError("Land audit does not reconcile with saved plan")
            if (audit["assignmentsSha256"] != accepted["validation"]["checkpoint_sha256"]
                    or audit["sourceArchiveSha256"] != accepted["source"]["archive_sha256"]):
                raise ValueError("Land audit source/assignment identity changed")
            display = fragment["landDisplays"][plan_id]
            geometry = fragment["geometryPlans"][plan_id]
            if display["planId"] != plan_id or set(geometry) - GEOMETRY_KEYS:
                raise ValueError("Unexpected land display identity or geometry fields")
            if display["state"] != geometry["detail"] or display["national"] != geometry["overview"]:
                raise ValueError("Land display does not use its matched explorer geometry")
            connections = read_reference(root, cache, display["connections"], assets)
            metadata = connections.get("metadata", {})
            if (connections.get("type") != "FeatureCollection"
                    or [metadata.get(k) for k in ("planId", "stateFips", "coordinateFrame", "schemaVersion")]
                    != [plan_id, state, plan["coordinateFrame"], 2]
                    or len(connections["features"]) != display["summary"]["derivedConnectionCount"]
                    or len(connections["features"]) != audit["waterPaths"]["derived_connection_count"]):
                raise ValueError("Derived connections do not match land display audit")
            if geometry.get("coverage") != "land-focused" or geometry.get("coordinateFrame") != plan["coordinateFrame"]:
                raise ValueError("Land display coverage or frame mismatch")
            for key in ("overview", "detail"):
                document = read_reference(root, cache, geometry[key], assets)
                validate_collection(document, plan)
                meta = document.get("metadata", {})
                if (meta.get("planId"), meta.get("stateFips"), meta.get("coordinateFrame")) != (plan_id, state, plan["coordinateFrame"]):
                    raise ValueError("Land geometry metadata mismatch")
            old = updated["stateExplorers"][state]["plans"][plan_id]
            updated["stateExplorers"][state]["plans"][plan_id] = {**old,
                "censusOverview": old.get("censusOverview", old["overview"]), **geometry}
            updated.setdefault("landDisplays", {})[plan_id] = deepcopy(display)
            checks[plan_id] = fragment["audit"]["plans"][plan_id]
        print(f"Validated land fragment {state}: {len(expected)} plans", flush=True)
    if set(updated["landDisplays"]) != set(manifest["plans"]):
        raise ValueError("Land displays do not cover all accepted plans")

    builder = BundleBuilder(root, cache_root=cache)
    anchors, shoreline_counts = {}, {}
    for anchor in manifest["anchors"]:
        layers = {key: [] for key in ("outlines", "coast", "dividers", "connections", "recordedConnections")}
        frames = {}
        for plan_id in anchor["planIds"]:
            plan = manifest["plans"][plan_id]
            state = plan["stateFips"]
            frames[state] = plan["coordinateFrame"]
            explorer = updated["stateExplorers"][state]["plans"][plan_id]
            display = updated["landDisplays"][plan_id]
            for key, ref in (("outlines", explorer["overview"]), ("coast", explorer["coast"]),
                             ("dividers", explorer["dividers"]), ("connections", display["connections"])):
                document = read_reference(root, cache, ref, assets)
                if key == "outlines":
                    validate_collection(document, plan)
                if key == "coast":
                    document, counts = classify_coast(document)
                    shoreline_counts[plan_id] = counts
                layers[key].extend(annotated_features(document, plan))
            if plan["assets"].get("connections"):
                document = read_reference(root, cache, plan["assets"]["connections"], assets)
                if len(document["features"]) != plan["recordedLinkCount"]:
                    raise ValueError("Recorded connection count changed")
                layers["recordedConnections"].extend(annotated_features(document, plan))
        record = {"houseSize": anchor["houseSize"], "planIds": deepcopy(anchor["planIds"])}
        for key, features in layers.items():
            metadata = {"houseSize": anchor["houseSize"], "planIds": anchor["planIds"], "coordinateFrames": frames}
            if key == "coast":
                metadata["shorelineClassification"] = "top-level-containment-v1"
            record[key] = builder.generated({"type": "FeatureCollection", "features": features, "metadata": metadata},
                                             f"land-{anchor['houseSize']}-{key}.geojson")
        anchors[str(anchor["houseSize"])] = record
        print(f"Bundled land anchor {anchor['houseSize']}", flush=True)
    updated["landAnchors"] = anchors
    merge_assets(additions, builder.assets)
    merge_assets(assets, builder.assets)
    validate_assets(root, cache, additions)
    assert_preserved(manifest, updated)
    for path, sha in preserved.items():
        if file_hash(resource_path(root, path, cache)) != sha:
            raise ValueError(f"Preserved evidence changed: {path}")
    report = {"schemaVersion": 1, "status": "complete", "states": len(states), "plans": len(manifest["plans"]),
        "anchorStatePairs": 200, "catalogSha256": index["catalogSha256"], "inputs": inputs,
        "baseManifestSha256": digest(before_manifest), "baseIndexSha256": digest(before_index),
        "preservedPlansSha256": digest(encoded(manifest["plans"])), "preservedProofsSha256": digest(encoded(index["proofs"])),
        "preservedOriginalAssets": len(index["assets"]), "preservedSources": len(preserved),
        "generatedAssetCount": len(additions), "generatedGzipBytes": sum(v["gzipBytes"] for v in additions.values()),
        "anchors": anchors, "shorelines": shoreline_counts, "checks": checks,
        "solverRuns": 0, "savedAssignmentsModified": 0, "runtimeSeconds": time.perf_counter() - started,
        "coverageNote": "Display removes zero-land census blocks; mixed land/water blocks retain their footprint. Small enclosed overview holes are hidden using saved ownership. All residents and assignments remain included."}
    if not write:
        return report
    if file_hash(index_path) != digest(before_index) or file_hash(safe_path(root, OUTPUT / "manifest.json")) != digest(before_manifest):
        raise ValueError("Live bundle changed; refusing stale publication")
    for item in inputs:
        if file_hash(safe_path(root, item["path"])) != item["sha256"]:
            raise ValueError("Land fragment changed during validation")
    backup = safe_path(root, NAMESPACE / "publication-history")
    backup.mkdir(parents=True, exist_ok=True)
    for label, raw in (("manifest", before_manifest), ("server-index", before_index)):
        path = backup / f"{label}-{digest(raw)}.json"
        if path.exists():
            if file_hash(path) != digest(raw):
                raise ValueError("Publication backup identity conflict")
        else:
            path.write_bytes(raw)
    updated_index = {**index, "assets": assets, "manifestSha256": digest(encoded(updated)),
        "stateLandDisplayProvenance": {"reportPath": REPORT.as_posix(), "reportSha256": digest(encoded(report))}}
    atomic_json(safe_path(root, REPORT), report)
    atomic_json(safe_path(root, OUTPUT / "manifest.json"), updated)
    atomic_json(index_path, updated_index)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, default=Path(os.environ.get("BLOCK_PLAN_CACHE_ROOT", ROOT / ".cache")))
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    report = publish(args.bundle_root, args.cache_root, write=args.publish)
    print(json.dumps({key: report[key] for key in ("status", "states", "plans", "generatedAssetCount", "runtimeSeconds")}, indent=2))


if __name__ == "__main__":
    main()
