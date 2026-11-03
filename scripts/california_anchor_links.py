"""Verify California's unchanged six-link policy for the remaining House anchors.

The frozen K52 adapter performs exact source, physical graph, endpoint, and
crossing checks. This wrapper then recomputes population-group eligibility for
the actual requested count. Connection records retain the original builder's
provenance unchanged; target-count provenance belongs to the returned audit.
"""
from __future__ import annotations

from collections.abc import Sequence
import copy
import hashlib
import json
from numbers import Integral
from pathlib import Path
import time
from typing import Any

from districting.part_connectivity import PartGraph
from scripts import california_recorded_links as base_policy
from scripts.hawaii_population_links import select_population_aware_forest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CA_DIAGNOSTIC_DIR = base_policy.DEFAULT_CA_DIAGNOSTIC_DIR
SUPPORTED_DISTRICT_COUNTS = (69, 83, 120)
BASE_VERIFICATION_DISTRICT_COUNT = 52
PINNED_BASE_MODULE_SHA256 = "e05a573272489afde655dfbdbd5c5f414e568a735ab4830c100dcf29e0d3ef1a"


def _verify_base_module() -> str:
    digest = base_policy._sha256(Path(base_policy.__file__))
    if digest != PINNED_BASE_MODULE_SHA256:
        raise ValueError("The frozen California K52 adapter changed; anchor verification cannot redefine the policy.")
    return digest


def _verify_reused_edges(physical: PartGraph, augmented: PartGraph,
                         records: tuple[dict[str, Any], ...], candidates: list[dict[str, Any]]) -> None:
    """Independently require exactly the authorized new edges, without mutation."""
    if (len(records) != 6 or [row.get("candidate_id") for row in records] != list(base_policy.AUTHORIZED_CANDIDATE_IDS)
            or [row.get("id") for row in records] != [f"ca-water-{i:03d}" for i in range(1, 7)]
            or any(row.get("kind") != "recorded-water-connection" or row.get("state_fips") != "06" for row in records)):
        raise ValueError("Base verification must return the same six authorized California water records.")
    by_id = {row["id"]: row for row in candidates}
    additions: dict[int, set[int]] = {}
    for record in records:
        candidate = by_id.get(record["candidate_id"])
        if candidate is None or any(record.get(key) != value for key, value in candidate.items() if key != "id"):
            raise ValueError("A reused connection record differs from its verified diagnostic candidate.")
        a, b = [endpoint["part_node"] for endpoint in record["endpoints"]]
        if a == b or b in physical.adjacency[a] or b in additions.get(a, set()):
            raise ValueError("The six records must introduce distinct nonphysical source-part edges.")
        additions.setdefault(a, set()).add(b)
        additions.setdefault(b, set()).add(a)
    if augmented.part_to_unit != physical.part_to_unit or len(augmented.adjacency) != len(physical.adjacency):
        raise ValueError("Reused policy graph changed source-part ownership or coverage.")
    for node, neighbors in enumerate(physical.adjacency):
        expected = tuple(sorted(set(neighbors) | additions[node])) if node in additions else neighbors
        if augmented.adjacency[node] != expected:
            raise ValueError("Reused policy graph must equal physical adjacency plus exactly the six authorized edges.")


def build_california_anchor_connections(
    shapefile_path: Path, geoids: Sequence[str], populations: Sequence[int], part_graph: PartGraph,
    *, district_count: int, diagnostic_dir: Path = DEFAULT_CA_DIAGNOSTIC_DIR,
) -> tuple[PartGraph, tuple[dict[str, Any], ...], dict[str, Any]]:
    """Reuse full K52 source verification and validate actual K69/K83/K120 policy.

    No new connections, source edits, optimizer calls, or district assignments
    are made. This is source-group arithmetic; final district balance and
    polygon-plus-link connectivity still require their independent checks.
    """
    started = time.perf_counter()
    if isinstance(district_count, bool) or not isinstance(district_count, Integral) or district_count not in SUPPORTED_DISTRICT_COUNTS:
        raise ValueError("California anchor policy supports district counts 69, 83, and 120 only.")
    if len(geoids) < district_count:
        raise ValueError("The requested district count requires at least one whole block per district.")
    base_digest = _verify_base_module()
    augmented, records, base_audit = base_policy.build_california_connections(
        shapefile_path, geoids, populations, part_graph,
        district_count=BASE_VERIFICATION_DISTRICT_COUNT, diagnostic_dir=diagnostic_dir,
    )
    if (base_audit.get("district_count") != BASE_VERIFICATION_DISTRICT_COUNT
            or base_audit.get("physical_component_count") != 7
            or base_audit.get("augmented_component_count") != 1
            or base_audit.get("augmented_graph_connected") is not True
            or base_audit.get("all_source_parts_reached") is not True):
        raise ValueError("The base adapter did not return its complete seven-component source verification.")
    payload = (Path(diagnostic_dir) / "diagnosis.json").read_bytes()
    diagnosis_digest = hashlib.sha256(payload).hexdigest()
    if (diagnosis_digest != base_policy.PINNED_EVIDENCE_SHA256["diagnosis.json"]
            or diagnosis_digest != base_audit["provenance"]["diagnostic_evidence_sha256"]["diagnosis.json"]):
        raise ValueError("California diagnostic evidence changed between base and target-count verification.")
    diagnosis = json.loads(payload)
    target_plans = [plan for plan in diagnosis["plans"] if plan["district_count"] == district_count]
    if len(target_plans) != 1:
        raise ValueError("The pinned diagnosis must contain exactly one source-policy plan for the target count.")
    expected = target_plans[0]
    candidates = base_audit["candidate_connections"]
    component_populations = [row["population"] for row in base_audit["components"]]
    selection = select_population_aware_forest(
        component_populations, [row for row in candidates if row["eligible_positive_gap"]],
        district_count, population_tolerance=.01,
    )
    if (selection["selected_link_ids"] != list(base_policy.AUTHORIZED_CANDIDATE_IDS)
            or selection["eligible_root_component_ids"] != [0] or len(selection["groups"]) != 1
            or selection["groups"][0]["district_count"] != district_count
            or selection["groups"][0]["population"] != base_audit["source_population"]):
        raise ValueError("Target-count selection changed the authorized six edges, mainland root, or one-group allocation.")
    if (expected.get("actual_district_plan_generated") is not False
            or expected.get("selected_link_ids") != list(base_policy.AUTHORIZED_CANDIDATE_IDS)
            or expected.get("augmented_component_count") != 1
            or expected.get("policy") != selection
            or expected.get("policy_population_bound") != selection["population_bound"]):
        raise ValueError("Recomputed target-count population policy differs from the pinned diagnosis.")
    _verify_reused_edges(part_graph, augmented, records, candidates)
    if _verify_base_module() != base_digest:
        raise ValueError("The frozen California base adapter changed during verification.")
    audit = copy.deepcopy(base_audit)
    audit.update({
        "district_count": int(district_count),
        "eligible_root_count": len(selection["eligible_root_component_ids"]),
        "groups": copy.deepcopy(selection["groups"]),
        "population_selection": selection,
        "base_verification_district_count": BASE_VERIFICATION_DISTRICT_COUNT,
        "base_verification_elapsed_seconds": base_audit["elapsed_seconds"],
        "target_selection_verified_against_diagnosis": True,
        "connection_records_reused_unchanged": True,
        "wrapper_provenance": {
            "kind": "california_target_count_verification_v1",
            "builder_sha256": base_policy._sha256(Path(__file__)),
            "base_builder_sha256": base_digest,
            "base_verification_district_count": BASE_VERIFICATION_DISTRICT_COUNT,
            "target_district_count": int(district_count),
            "diagnosis_sha256": diagnosis_digest,
            "population_selector_sha256": base_policy._sha256(ROOT / "scripts/hawaii_population_links.py"),
            "meaning": "Full source verification reused at K52; population-group selection independently recomputed for the actual count. Connection records retain their original provenance.",
        },
        "elapsed_seconds": time.perf_counter() - started,
    })
    return augmented, records, audit
