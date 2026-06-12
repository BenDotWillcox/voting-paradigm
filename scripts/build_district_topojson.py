#!/usr/bin/env python3
"""Build compact display artifacts from cached district GeoJSON plans.

The full cached plans remain the algorithm artifacts. Two display files are
derived per plan:

- `districting-topo/.../*.topo.json` — tract-level geometry as quantized
  TopoJSON. Fetched lazily by the browser for tract-level hover detail.
- `districting-summary/.../*.summary.json` — the same metrics plus tract
  polygons dissolved into one outline per district. Small enough to render
  the plan map server-side immediately.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
INPUT_ROOT = ROOT / "public" / "data" / "districting"
OUTPUT_ROOT = ROOT / "public" / "data" / "districting-topo"
SUMMARY_ROOT = ROOT / "public" / "data" / "districting-summary"


def main() -> int:
    args = parse_args()
    paths = find_input_paths(args.state_fips, args.cap)
    if not paths:
        raise SystemExit("No matching district plan JSON files found.")

    for path in paths:
        plan = json.loads(path.read_text(encoding="utf-8"))

        outputs = [
            (output_path_for(path), build_topo_plan(plan, quantization=args.quantization)),
            (
                summary_path_for(path),
                build_summary_plan(plan, quantization=args.summary_quantization),
            ),
        ]
        for output_path, payload_plan in outputs:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(payload_plan, separators=(",", ":"))
            output_path.write_text(payload, encoding="utf-8")
            print(
                f"{path.relative_to(ROOT)} -> {output_path.relative_to(ROOT)} "
                f"({path.stat().st_size / 1024:.1f} KB -> {output_path.stat().st_size / 1024:.1f} KB)"
            )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--state-fips",
        help="Optional two-digit state FIPS to build. Defaults to all states.",
    )
    parser.add_argument(
        "--cap",
        type=int,
        default=435,
        help="House-size cap to build. Defaults to the current 435-seat plan.",
    )
    parser.add_argument(
        "--quantization",
        type=int,
        default=100_000,
        help="Integer grid size for TopoJSON quantization.",
    )
    parser.add_argument(
        "--summary-quantization",
        type=int,
        default=50_000,
        help=(
            "Integer grid size for the dissolved district summary. Shared "
            "district edges snap to the same grid, so quantization never "
            "opens gaps between districts."
        ),
    )
    return parser.parse_args()


def find_input_paths(state_fips: str | None, cap: int) -> list[Path]:
    roots = [INPUT_ROOT / state_fips.zfill(2)] if state_fips else sorted(INPUT_ROOT.iterdir())
    paths: list[Path] = []
    for root in roots:
        if root.is_dir():
            paths.extend(sorted(root.glob(f"cap-{cap}-seats-*.json")))
    return paths


def output_path_for(input_path: Path) -> Path:
    state_fips = input_path.parent.name
    return OUTPUT_ROOT / state_fips / f"{input_path.stem}.topo.json"


def summary_path_for(input_path: Path) -> Path:
    state_fips = input_path.parent.name
    return SUMMARY_ROOT / state_fips / f"{input_path.stem}.summary.json"


def plan_metadata(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": plan["type"],
        "state_fips": plan["state_fips"],
        "state_name": plan["state_name"],
        "source_year": plan["source_year"],
        "unit": plan["unit"],
        "unit_count": len(plan["feature_collection"]["features"]),
        "cap": plan["cap"],
        "seats": plan["seats"],
        "target_population": plan["target_population"],
        "total_population": plan["total_population"],
        "district_populations": plan["district_populations"],
        "max_population_imbalance": plan["max_population_imbalance"],
        "iterations": plan["iterations"],
        "converged": plan["converged"],
        "centers": plan.get("centers"),
        "projection": plan.get("projection"),
    }


def build_topo_plan(plan: dict[str, Any], *, quantization: int) -> dict[str, Any]:
    features = plan["feature_collection"]["features"]
    return {
        **plan_metadata(plan),
        "display_unit": "tract",
        "display_topology": build_topology(features, quantization),
        "notes": [
            *plan.get("notes", []),
            "Display geometry is quantized TopoJSON derived from the cached tract GeoJSON artifact.",
        ],
    }


def build_summary_plan(plan: dict[str, Any], *, quantization: int) -> dict[str, Any]:
    features = dissolve_districts(plan)
    return {
        **plan_metadata(plan),
        "display_unit": "district",
        "display_topology": build_topology(features, quantization),
        "notes": [
            *plan.get("notes", []),
            "Display geometry is tract polygons dissolved into per-district outlines, quantized TopoJSON.",
        ],
    }


def dissolve_districts(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Union each district's tract polygons into a single display outline."""
    grouped: dict[int, list[Any]] = {}
    for feature in plan["feature_collection"]["features"]:
        district_id = feature["properties"]["district_id"]
        grouped.setdefault(district_id, []).append(shape(feature["geometry"]))

    district_populations = plan["district_populations"]
    features: list[dict[str, Any]] = []
    for district_id in sorted(grouped):
        merged = unary_union(grouped[district_id])
        geometry = mapping(polygonal_only(merged))
        features.append(
            {
                "geometry": geometry,
                "id": f"district-{district_id}",
                "properties": {
                    "geoid": f"district-{district_id}",
                    "name": f"District {district_id + 1}",
                    "population": district_populations.get(str(district_id), 0),
                    "district_id": district_id,
                },
            }
        )
    return features


def polygonal_only(geometry: Any) -> Any:
    """Drop stray points/lines a union can leave behind in a collection."""
    if geometry.geom_type != "GeometryCollection":
        return geometry
    polygons = [g for g in geometry.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
    return unary_union(polygons)


def build_topology(features: list[dict[str, Any]], quantization: int) -> dict[str, Any]:
    bbox = compute_bbox(features)
    transform = make_transform(bbox, quantization)
    arcs: list[list[list[int]]] = []
    geometries = []

    for feature in features:
        geometry = feature["geometry"]
        topo_geometry, next_arcs = convert_geometry(geometry, transform)
        arc_offset = len(arcs)
        arcs.extend(next_arcs)
        geometries.append(
            {
                "type": topo_geometry["type"],
                "arcs": offset_arcs(topo_geometry["arcs"], arc_offset),
                "id": feature.get("id"),
                "properties": feature["properties"],
            }
        )

    return {
        "type": "Topology",
        "bbox": bbox,
        "transform": transform,
        "objects": {
            "districts": {
                "type": "GeometryCollection",
                "geometries": geometries,
            }
        },
        "arcs": arcs,
    }


def compute_bbox(features: list[dict[str, Any]]) -> list[float]:
    xs: list[float] = []
    ys: list[float] = []
    for feature in features:
        for lon, lat in iter_positions(feature["geometry"]["coordinates"]):
            xs.append(lon)
            ys.append(lat)
    return [min(xs), min(ys), max(xs), max(ys)]


def iter_positions(coordinates: Any):
    # Tuples included: shapely's mapping() emits coordinates as tuples.
    if (
        isinstance(coordinates, (list, tuple))
        and coordinates
        and isinstance(coordinates[0], (int, float))
    ):
        yield coordinates
        return
    for child in coordinates:
        yield from iter_positions(child)


def make_transform(bbox: list[float], quantization: int) -> dict[str, list[float]]:
    x0, y0, x1, y1 = bbox
    denominator = max(1, quantization - 1)
    return {
        "scale": [(x1 - x0) / denominator, (y1 - y0) / denominator],
        "translate": [x0, y0],
    }


def convert_geometry(
    geometry: dict[str, Any],
    transform: dict[str, list[float]],
) -> tuple[dict[str, Any], list[list[list[int]]]]:
    arcs: list[list[list[int]]] = []
    if geometry["type"] == "Polygon":
        polygon_arcs = []
        for ring in geometry["coordinates"]:
            polygon_arcs.append([len(arcs)])
            arcs.append(encode_arc(ring, transform))
        return {"type": "Polygon", "arcs": polygon_arcs}, arcs
    if geometry["type"] == "MultiPolygon":
        multi_arcs = []
        for polygon in geometry["coordinates"]:
            polygon_arcs = []
            for ring in polygon:
                polygon_arcs.append([len(arcs)])
                arcs.append(encode_arc(ring, transform))
            multi_arcs.append(polygon_arcs)
        return {"type": "MultiPolygon", "arcs": multi_arcs}, arcs
    raise ValueError(f"Unsupported geometry type {geometry['type']!r}")


def encode_arc(
    ring: list[list[float]],
    transform: dict[str, list[float]],
) -> list[list[int]]:
    scale_x, scale_y = transform["scale"]
    translate_x, translate_y = transform["translate"]
    encoded: list[list[int]] = []
    prev_x = 0
    prev_y = 0
    for lon, lat in ring:
        qx = round((lon - translate_x) / scale_x) if scale_x else 0
        qy = round((lat - translate_y) / scale_y) if scale_y else 0
        encoded.append([qx - prev_x, qy - prev_y])
        prev_x = qx
        prev_y = qy
    return encoded


def offset_arcs(arcs: Any, offset: int) -> Any:
    if isinstance(arcs, int):
        return arcs + offset if arcs >= 0 else arcs - offset
    return [offset_arcs(child, offset) for child in arcs]


if __name__ == "__main__":
    raise SystemExit(main())
