"""Build the read-only New York diagnostic from its saved topology audit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".cache/state-block-benchmark/suite-through-1000/diagnostics/new-york"
TEMPLATE = ROOT / "scripts/assets/new-york-topology-viewer.html"


def build() -> Path:
    inputs = ("diagnosis.json", "components.geojson", "candidates.geojson", "detail-blocks.geojson")
    documents = {name: json.loads((OUTPUT / name).read_text(encoding="utf-8")) for name in inputs}
    diagnosis = documents["diagnosis.json"]
    if diagnosis.get("state_fips") != "36" or not diagnosis.get("components") or not diagnosis.get("plans"):
        raise ValueError("A completed New York component and population-policy audit is required")
    for name in inputs[1:]:
        if documents[name].get("type") != "FeatureCollection":
            raise ValueError(f"Invalid map FeatureCollection: {name}")
    target = OUTPUT / "index.html"
    target.write_bytes(TEMPLATE.read_bytes())
    optional = tuple(name for name in ("geography-context.json", "new-jersey-context.geojson", "area-water-context.geojson", "area-water-audit.json", "connection-surface-segments.geojson") if (OUTPUT / name).is_file())
    (OUTPUT / "viewer.json").write_text(json.dumps({
        "kind": "new_york_topology_diagnostic_viewer_v1",
        "view_only": True,
        "district_plan_solved": False,
        "template": str(TEMPLATE.relative_to(ROOT)).replace("\\", "/"),
        "sha256": {name: hashlib.sha256((OUTPUT / name).read_bytes()).hexdigest() for name in (*inputs, *optional, "index.html")},
    }, indent=2) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    print(build())
