"""Build a read-only California source-topology viewer from a completed audit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".cache/state-block-benchmark/suite-through-1000/diagnostics/california"
TEMPLATE = ROOT / "scripts/assets/california-topology-viewer.html"


def build() -> Path:
    inputs = ("diagnosis.json", "components.geojson", "candidates.geojson", "detail-blocks.geojson")
    documents = {name: json.loads((OUTPUT / name).read_text(encoding="utf-8")) for name in inputs}
    diagnosis = documents["diagnosis.json"]
    if (diagnosis.get("state_fips") != "06" or not diagnosis.get("components")
            or {plan["district_count"] for plan in diagnosis.get("plans", [])} != {52, 69, 83, 120}):
        raise ValueError("A completed California component and four-anchor policy audit is required.")
    if any(plan.get("actual_district_plan_generated") is not False for plan in diagnosis["plans"]):
        raise ValueError("This viewer is exclusively for source-policy diagnosis, not district plans.")
    for name in inputs[1:]:
        if documents[name].get("type") != "FeatureCollection":
            raise ValueError(f"Invalid map FeatureCollection: {name}")
        expected = diagnosis.get("artifact_sha256", {}).get(name)
        if expected and hashlib.sha256((OUTPUT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Saved diagnostic artifact hash does not match: {name}")
    component_ids = {row["id"] for row in diagnosis["components"]}
    link_ids = {row["id"] for row in diagnosis["links"]}
    if len(link_ids) != len(diagnosis["links"]):
        raise ValueError("Candidate link IDs must be unique.")
    if any(not set(row["component_ids"]).issubset(component_ids) for row in diagnosis["links"]):
        raise ValueError("A candidate refers to an unknown source component.")
    if any(not set(plan["selected_link_ids"]).issubset(link_ids) for plan in diagnosis["plans"]):
        raise ValueError("A policy selects an unknown candidate link.")
    target = OUTPUT / "index.html"
    target.write_bytes(TEMPLATE.read_bytes())
    optional = tuple(name for name in ("geography-context.json", "optimizer-starting-point.json")
                     if (OUTPUT / name).is_file())
    (OUTPUT / "viewer.json").write_text(json.dumps({
        "kind": "california_topology_diagnostic_viewer_v1",
        "view_only": True,
        "district_plan_solved": False,
        "template": TEMPLATE.relative_to(ROOT).as_posix(),
        "sha256": {name: hashlib.sha256((OUTPUT / name).read_bytes()).hexdigest()
                   for name in (*inputs, *optional, "index.html")},
    }, indent=2) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    print(build())
