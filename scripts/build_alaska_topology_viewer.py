"""Build a read-only Alaska diagnostic map from verified saved evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".cache/state-block-benchmark/suite-through-1000/diagnostics/alaska"
TEMPLATE = ROOT / "scripts/assets/alaska-topology-viewer.html"


def build(output: Path = OUTPUT) -> Path:
    inputs = ("diagnosis.json", "components.geojson", "candidates.geojson")
    docs = {name: json.loads((output / name).read_text(encoding="utf-8")) for name in inputs}
    diagnosis = docs["diagnosis.json"]
    if diagnosis.get("state_fips") != "02" or not diagnosis.get("components"):
        raise ValueError("A saved Alaska component diagnosis is required.")
    plans = diagnosis.get("plans", [])
    if any(plan.get("actual_district_plan_generated") is not False for plan in plans):
        raise ValueError("Only source diagnosis, not solved district plans, belongs in this viewer.")
    component_ids = {row["id"] for row in diagnosis["components"]}
    links = diagnosis.get("links", [])
    link_ids = {row["id"] for row in links}
    if len(component_ids) != len(diagnosis["components"]) or len(link_ids) != len(links):
        raise ValueError("Component and candidate IDs must be unique.")
    for name in inputs[1:]:
        document = docs[name]
        if document.get("type") != "FeatureCollection":
            raise ValueError(f"Invalid diagnostic feature collection: {name}")
        expected = diagnosis.get("artifact_sha256", {}).get(name)
        if not expected or hashlib.sha256((output / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Missing or mismatched diagnostic artifact hash: {name}")
    feature_components = [row["properties"]["id"] for row in docs["components.geojson"]["features"]]
    feature_links = [row["properties"]["id"] for row in docs["candidates.geojson"]["features"]]
    if len(feature_components) != len(component_ids) or set(feature_components) != component_ids:
        raise ValueError("Component map and diagnosis IDs differ.")
    if len(feature_links) != len(link_ids) or set(feature_links) != link_ids:
        raise ValueError("Candidate map and diagnosis IDs differ.")
    if any(len(row["component_ids"]) != 2 or not set(row["component_ids"]).issubset(component_ids) for row in links):
        raise ValueError("Candidate endpoints refer to unknown components.")
    if any(not set(plan.get("selected_link_ids", [])).issubset(link_ids) for plan in plans):
        raise ValueError("Policy selects an unknown candidate.")
    optional = ()
    if (output / "geography-context.json").is_file():
        context = json.loads((output / "geography-context.json").read_text(encoding="utf-8"))
        if not set(context.get("component_labels", {})).issubset({str(i) for i in component_ids}):
            raise ValueError("Geographic labels refer to unknown source components.")
        optional = ("geography-context.json",)
    target = output / "index.html"
    target.write_bytes(TEMPLATE.read_bytes())
    (output / "viewer.json").write_text(json.dumps({
        "kind": "alaska_topology_diagnostic_viewer_v1",
        "district_plan_solved": False,
        "view_only": True,
        "coordinate_note": "Unwrapped diagnostic coordinates; these files are not production RFC 7946 exports.",
        "template": TEMPLATE.relative_to(ROOT).as_posix(),
        "sha256": {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in (*inputs, *optional, "index.html")},
    }, indent=2) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    print(build())
