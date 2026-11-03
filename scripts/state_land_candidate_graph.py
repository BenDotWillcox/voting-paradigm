"""Reuse immutable whole-block graphs only as physical-part candidate lists.

The historical builder examined every source-bbox pair with F***1****. When
source interiors never overlap, every actual Polygon-part shared edge is also
present between its owning whole blocks. Multipart ownership is NOT a physical
edge: state_land_water_paths still tests each part and audits its own graph.
Alaska's continuous working geometry requires the independent bbox fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from collections.abc import Sequence
from typing import Any

import numpy as np

from scripts.build_block_plan_bundle import digest, resource_path
from scripts.build_michigan_land_display import canonical, read_graph

# Reviewed immutable legacy implementation scripts/district_block_adjacency.py.
# This is a provenance version, not the current display implementation's hash.
LEGACY_BUILDER_SHA256 = "8e3bd87629631e5452b6294bb94789dffa733a7b490db8a5238687a7609c0efc"
TOPOLOGY_RULE = "F***1****; original source coordinates; no snapping or buffering"


def load_state_candidate_graph(
    root: Path,
    cache_root: Path,
    state_fips: str,
    geoids: Sequence[str],
    source_sha256: str,
    accepted_report: dict[str, Any],
) -> tuple[tuple[tuple[int, ...], ...] | None, dict[str, Any], dict[str, str]]:
    """Return validated candidate CSR, audit, and newly preserved file hashes.

    The caller has already pinned ``accepted_report`` and verified the source
    archive. For corrected policy plans, the pinned part-cache identity supplies
    source/order/library provenance for the original whole-block cache. Its
    independently reconstructed key selects a single immutable legacy file.
    No cache build, repair, write, or solver action is performed.
    """
    if len(state_fips) != 2 or not state_fips.isdigit():
        raise ValueError("Candidate graph needs a two-digit state FIPS.")
    if state_fips == "02":
        return None, {"method": "source-bbox-candidates", "reason": "Alaska uses its accepted continuous longitude frame; no legacy whole-block cache is used."}, {}
    if len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256):
        raise ValueError("Candidate source archive SHA-256 is invalid.")
    if not geoids or len(set(geoids)) != len(geoids) or any(
        not isinstance(geoid, str) or len(geoid) != 15 or not geoid.isascii()
        or not geoid.isdigit() or not geoid.startswith(state_fips) for geoid in geoids
    ):
        raise ValueError("Candidate graph requires all unique state source GEOIDs.")
    geoid_hash = digest(canonical(list(geoids)))
    whole_record = accepted_report.get("graph_cache")
    part_record = accepted_report.get("physical_part_graph_cache")
    if isinstance(whole_record, dict):
        identity = whole_record.get("identity", {})
        origin = "accepted whole-block cache identity"
    elif isinstance(part_record, dict):
        part_identity = part_record.get("identity", {})
        if (part_identity.get("source_archive_sha256") != source_sha256
                or part_identity.get("ordered_geoids_sha256") != geoid_hash
                or part_identity.get("block_count") != len(geoids)):
            raise ValueError("Accepted part-cache source or GEOID identity disagrees with source DBF.")
        identity = {
            "schema": 1, "topology_rule": TOPOLOGY_RULE,
            "source_archive_sha256": source_sha256, "ordered_geoids_sha256": geoid_hash,
            "node_count": len(geoids), "adjacency_builder_sha256": LEGACY_BUILDER_SHA256,
            "shapely_version": part_identity.get("shapely_version"),
            "geos_version": part_identity.get("geos_version"),
        }
        origin = "original whole-block identity reconstructed from accepted part-cache source/order/library provenance"
    else:
        raise ValueError("Accepted report has no pinned physical graph provenance for cached candidates.")
    expected_fields = {"schema", "topology_rule", "source_archive_sha256", "ordered_geoids_sha256",
                       "node_count", "adjacency_builder_sha256", "shapely_version", "geos_version"}
    if (set(identity) != expected_fields or identity.get("schema") != 1
            or identity.get("topology_rule") != TOPOLOGY_RULE
            or identity.get("source_archive_sha256") != source_sha256
            or identity.get("ordered_geoids_sha256") != geoid_hash
            or identity.get("node_count") != len(geoids)
            or identity.get("adjacency_builder_sha256") != LEGACY_BUILDER_SHA256
            or any(not isinstance(identity.get(key), str) or not identity[key] for key in ("shapely_version", "geos_version"))):
        raise ValueError("Legacy candidate identity differs from the verified source, GEOID order, or reviewed builder.")
    key = digest(canonical(identity))
    if isinstance(whole_record, dict) and whole_record.get("key") != key:
        raise ValueError("Pinned graph cache key disagrees with its identity.")
    directory = (Path(".cache/kansas-block-benchmark/graph-cache") if state_fips == "20"
                 else Path(".cache/state-block-benchmark/graph-cache") / state_fips)
    relative = directory / f"shared-edge-{key}.npz"
    path = resource_path(root, relative, cache_root)
    adjacency, proof = read_graph(path, identity, geoids)
    if isinstance(whole_record, dict) and "bytes" in whole_record and path.stat().st_size != whole_record["bytes"]:
        raise ValueError("Pinned candidate graph cache byte length differs.")
    # read_graph independently validates the archive members, expected identity,
    # GEOID ordering, payload checksum, CSR symmetry, shape, bounds and topology.
    with np.load(path, allow_pickle=False) as archive:
        manifest = json.loads(archive["manifest"].tobytes())
    metadata = manifest["graph_metadata"]
    if metadata.get("interior_overlap_pair_count") != 0:
        raise ValueError("Whole-block candidates need zero source interior overlaps to guarantee part-edge coverage.")
    audit = {
        "method": "validated-legacy-whole-block-csr-candidates", "provenance": origin,
        "path": relative.as_posix(), "identity": identity, "key": key,
        "fileSha256": proof["file_sha256"], "payloadSha256": proof["payload_sha256"],
        "sourceInteriorOverlapPairCount": 0, "candidateUndirectedEdges": metadata["edge_count"],
        "exactPartRecheckRequired": True, "syntheticOwnershipEdgesUsed": False,
        "meaning": "Candidate discovery only; exact Polygon-part checks and the independent combined audit determine physical connectivity.",
    }
    return adjacency, audit, {relative.as_posix(): proof["file_sha256"]}
