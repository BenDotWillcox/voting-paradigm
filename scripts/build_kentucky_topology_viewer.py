"""Build the read-only Kentucky topology diagnostic from its saved source audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".cache/state-block-benchmark/suite-through-1000/diagnostics/kentucky"
TEMPLATE = ROOT / "scripts/assets/kentucky-topology-viewer.html"


def build(output: Path = OUTPUT) -> Path:
    """Write only the new diagnostic viewer; do not touch benchmark results."""
    output = output.resolve()
    if output != OUTPUT.resolve():
        raise ValueError("Kentucky diagnostic output must use its dedicated diagnostics/kentucky directory")
    inputs = ("diagnosis.json", "components.geojson", "links.geojson", "detail-blocks.geojson")
    documents = {name: json.loads((output / name).read_text(encoding="utf-8")) for name in inputs}
    diagnosis = documents["diagnosis.json"]
    if not diagnosis.get("components") or not diagnosis.get("plans"):
        raise ValueError("A completed component and population-bound audit is required")
    for name in inputs[1:]:
        if documents[name].get("type") != "FeatureCollection":
            raise ValueError(f"Invalid map FeatureCollection: {name}")
    target = output / "index.html"
    target.write_bytes(TEMPLATE.read_bytes())
    optional_inputs = tuple(
        name
        for name in (
            "geography-context.json", "missouri-connection-context.json", "missouri-context.geojson",
            "area-water-audit.json", "area-water-context.geojson", "connection-surface-segments.geojson",
        )
        if (output / name).is_file()
    )
    manifest = {
        "kind": "kentucky_topology_diagnostic_viewer_v1",
        "view_only": True,
        "district_plan_solved": False,
        "template": str(TEMPLATE.relative_to(ROOT)).replace("\\", "/"),
        "sha256": {
            name: hashlib.sha256((output / name).read_bytes()).hexdigest()
            for name in (*inputs, *optional_inputs, "index.html")
        },
    }
    (output / "viewer.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    print(build(parser.parse_args().output))
