"""State-map adapter with compressed-only storage and explicit connectivity policy.

The measured Kansas exporter is deliberately left unchanged. This adapter adds
state identity, explicit unsupported-geography checks, independent output
reconciliation, and verified removal of raw GeoJSON created in a fresh owned
directory. It never repairs source geography. Optional recorded water or exclave
links are independently validated without claiming physical contiguity.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import gzip
import hashlib
import json
import math
from numbers import Integral
from pathlib import Path
import shutil
import time
from typing import Any

import shapefile
import shapely
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from scripts import district_block_map_export as original_exporter


class UnsupportedStateGeometryError(ValueError):
    """The original-coordinate planar adapter cannot certify this geography."""


class StateMapValidationError(ValueError):
    """Exported map diagnostics fail the strict state-plan acceptance checks."""


_ENDPOINT_BOUNDARY_TOLERANCE_DEGREES = 1e-9


def _polygon_parts(geometry: BaseGeometry) -> list[BaseGeometry]:
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type == "MultiPolygon":
        return list(geometry.geoms)
    raise StateMapValidationError("Connectivity validation requires Polygon or MultiPolygon geometry.")


def _part_container(part: BaseGeometry, components: Sequence[BaseGeometry]) -> int:
    """Use the whole source part, avoiding ambiguous shared boundary points."""
    containers = [index for index, component in enumerate(components) if component.covers(part)]
    if len(containers) != 1:
        raise StateMapValidationError("Endpoint source part does not belong to exactly one dissolved component.")
    return containers[0]


def _validate_recorded_connection_geometry(
    shapefile_path: Path, assignments: Mapping[str, int], output_dir: Path,
    state_fips: str, n_districts: int,
    connections: Sequence[Mapping[str, Any]],
    *, connection_type: str = "water",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Independently certify declared edges on unchanged, full-resolution polygons.

    Global ``part_node`` IDs follow assignment mapping insertion order, then
    original MultiPolygon part order, exactly as the caller's part graph must.
    Neither common ownership nor a line's visual intersection creates an edge.
    """
    if connection_type not in ("water", "exclave", "mixed"):
        raise ValueError("Unsupported recorded connection type.")
    label = connection_type.capitalize()
    with shapefile.Reader(str(shapefile_path)) as reader:
        fields = [field[0] for field in reader.fields[1:]]
        geoid_index = fields.index("GEOID20")
        blocks = {
            str(record.record[geoid_index]): shape(record.shape.__geo_interface__)
            for record in reader.iterShapeRecords()
        }
    if set(blocks) != set(assignments) or not all(geometry.is_valid for geometry in blocks.values()):
        raise StateMapValidationError(f"{label}-policy audit requires exactly the unchanged valid source blocks.")
    if not bool(shapely.coverage_is_valid(list(blocks.values()))):
        raise StateMapValidationError("Original source blocks fail independent nonoverlapping coverage validation.")
    source_union = unary_union(list(blocks.values()))
    source_components = _polygon_parts(source_union)
    full = json.loads((output_dir / "districts-full.geojson").read_text(encoding="utf-8"))
    district_geometries = {
        int(feature["properties"]["district_id"]): shape(feature["geometry"])
        for feature in full["features"]
    }
    if set(district_geometries) != set(range(n_districts)):
        raise StateMapValidationError("Full polygon district identifiers failed independent reconciliation.")
    if not bool(shapely.coverage_is_valid(list(district_geometries.values()))):
        raise StateMapValidationError("Full polygons fail independent nonoverlapping coverage validation.")
    difference = source_union.symmetric_difference(unary_union(list(district_geometries.values())))
    if not difference.is_empty:
        raise StateMapValidationError("Full district polygons do not exactly preserve source coverage.")
    district_parts = {district: _polygon_parts(geometry) for district, geometry in district_geometries.items()}
    offsets: dict[str, int] = {}
    node = 0
    for geoid in assignments:
        offsets[geoid] = node
        node += len(_polygon_parts(blocks[geoid]))

    parents = {district: list(range(len(parts))) for district, parts in district_parts.items()}

    def root(district: int, part: int) -> int:
        while parents[district][part] != part:
            part = parents[district][part]
        return part

    used: dict[int, list[str]] = {district: [] for district in range(n_districts)}
    features: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[int, int]] = set()
    for connection in connections:
        if not isinstance(connection, Mapping):
            raise StateMapValidationError(f"{label} connections must be records.")
        link_id = connection.get("id")
        if not isinstance(link_id, str) or not link_id or link_id in seen_ids:
            raise StateMapValidationError(f"{label} connection IDs must be nonempty and unique.")
        seen_ids.add(link_id)
        if connection.get("state_fips") != state_fips:
            raise StateMapValidationError(f"{label} connection {link_id} belongs to the wrong state.")
        if connection_type == "exclave" and connection.get("kind") != "recorded-exclave-connection":
            raise StateMapValidationError("Exclave connections must explicitly declare their recorded-exclave-connection kind.")
        if connection_type == "mixed":
            kind = connection.get("kind")
            context = connection.get("geographic_context")
            if kind not in ("recorded-water-connection", "recorded-exclave-connection"):
                raise StateMapValidationError("Mixed connections require an explicit water or exclave kind.")
            if not isinstance(context, Mapping):
                raise StateMapValidationError("Mixed connections require their audited geographic context.")
            water_only = kind == "recorded-water-connection"
            if context.get("water_only") is not water_only:
                raise StateMapValidationError("Mixed connection kind disagrees with its water/land classification.")
            land = context.get("mapped_land_length_m")
            water = context.get("mapped_water_length_m")
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 for value in (land, water)):
                raise StateMapValidationError("Mixed connection audited surface lengths must be finite and nonnegative.")
            if (water_only and land > 1e-6) or (not water_only and land <= 1e-6):
                raise StateMapValidationError("Mixed connection kind disagrees with its audited land crossing.")
        component_ids = connection.get("component_ids")
        if (not isinstance(component_ids, (list, tuple)) or len(component_ids) != 2
                or any(isinstance(value, bool) or not isinstance(value, Integral) or value < 0 for value in component_ids)
                or component_ids[0] == component_ids[1]):
            raise StateMapValidationError(f"{label} connection component IDs must identify two distinct components.")
        distance = connection.get("distance_m")
        if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance <= 0:
            raise StateMapValidationError(f"{label} connection distance must be finite and positive.")
        endpoints = connection.get("endpoints")
        if not isinstance(endpoints, (list, tuple)) or len(endpoints) != 2:
            raise StateMapValidationError(f"Every {connection_type} connection requires exactly two endpoint records.")
        coordinates: list[list[float]] = []
        endpoint_districts: list[int] = []
        endpoint_parts: list[int] = []
        global_components: list[int] = []
        endpoint_nodes: list[int] = []
        for endpoint in endpoints:
            if not isinstance(endpoint, Mapping):
                raise StateMapValidationError(f"{label} connection endpoints must be records.")
            geoid = endpoint.get("geoid")
            if geoid not in assignments or not isinstance(geoid, str) or not geoid.startswith(state_fips):
                raise StateMapValidationError(f"{label} connection endpoint is not an assigned source block in this state.")
            part_index, part_node = endpoint.get("part_index"), endpoint.get("part_node")
            parts = _polygon_parts(blocks[geoid])
            if (isinstance(part_index, bool) or not isinstance(part_index, Integral)
                    or not 0 <= part_index < len(parts)):
                raise StateMapValidationError(f"{label} connection endpoint has an invalid source part index.")
            if isinstance(part_node, bool) or not isinstance(part_node, Integral) or part_node != offsets[geoid] + part_index:
                raise StateMapValidationError(f"{label} connection endpoint global part ownership does not match the source.")
            coordinate = endpoint.get("coordinate")
            if (not isinstance(coordinate, (list, tuple)) or len(coordinate) != 2
                    or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in coordinate)):
                raise StateMapValidationError(f"{label} connection endpoint coordinates must be two finite numbers.")
            point = Point(coordinate)
            source_part = parts[part_index]
            if source_part.boundary.distance(point) > _ENDPOINT_BOUNDARY_TOLERANCE_DEGREES:
                raise StateMapValidationError(f"{label} connection endpoint is not on the declared source part boundary.")
            district = int(assignments[geoid])
            coordinates.append([float(value) for value in coordinate])
            endpoint_districts.append(district)
            endpoint_parts.append(_part_container(source_part, district_parts[district]))
            global_components.append(_part_container(source_part, source_components))
            endpoint_nodes.append(int(part_node))
        if global_components[0] == global_components[1]:
            raise StateMapValidationError(f"{label} links may only join genuinely disconnected source components.")
        edge = tuple(sorted(endpoint_nodes))
        if edge in seen_edges:
            raise StateMapValidationError(f"Duplicate {connection_type} connection endpoints.")
        seen_edges.add(edge)
        used_by_district = None
        if endpoint_districts[0] == endpoint_districts[1]:
            district = endpoint_districts[0]
            a, b = (root(district, part) for part in endpoint_parts)
            if a != b:
                parents[district][a] = b
            used[district].append(link_id)
            used_by_district = district
        features.append({
            "type": "Feature", "id": link_id,
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "properties": {
                "id": link_id, "state_fips": state_fips,
                "component_ids": list(component_ids), "distance_m": float(distance),
                "endpoints": [dict(endpoint) for endpoint in endpoints],
                "endpoint_districts": endpoint_districts,
                "used_by_district": used_by_district,
                "meaning": "declared connectivity edge; no source polygon or land bridge added",
            },
        })
        if connection_type in ("exclave", "mixed"):
            features[-1]["properties"].update({
                "kind": connection["kind"],
                "policy": connection.get("policy"),
                "geographic_context": connection.get("geographic_context"),
                "provenance": connection.get("provenance"),
                "meaning": "declared connectivity exception; no source polygon, foreign-state territory, bridge, or travel route added",
            })
    rows = []
    issues = []
    for district, parts in sorted(district_parts.items()):
        connected_components = len({root(district, index) for index in range(len(parts))})
        rows.append({
            "district_id": district, "physical_polygon_components": len(parts),
            "connected_components_after_links": connected_components,
            "used_link_ids": used[district],
        })
        if connected_components != 1:
            issues.append(f"District {district} still has {connected_components} components after eligible recorded {connection_type} connections.")
    validation = {
        "policy": f"shared_edges_plus_recorded_{connection_type}_connections", "passed": not issues,
        "issues": issues, "districts": rows,
        "used_link_ids": [link_id for district in sorted(used) for link_id in used[district]],
        "endpoint_boundary_tolerance_degrees": _ENDPOINT_BOUNDARY_TOLERANCE_DEGREES,
        "endpoint_global_part_order": "assignment mapping GEOID order, then original MultiPolygon parts",
        "source_coverage_preserved_exactly": True,
        "independent_source_coverage_valid": True,
        "independent_district_coverage_valid": True,
        "source_geometry_modified": False,
        "validation_basis": "full dissolved polygon components with validated source-part endpoints; independent of graph edges",
    }
    return validation, {"type": "FeatureCollection", "features": features}


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _stream_digest(stream: Any) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for chunk in iter(lambda: stream.read(1_048_576), b""):
        digest.update(chunk)
        count += len(chunk)
    return digest.hexdigest(), count


def _owned_file(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or path.is_symlink() or not path.is_file():
        raise ValueError(f"Refusing to compact a file outside the owned output: {path}.")
    return resolved


def _compress_if_needed(path: Path) -> Path:
    compressed = path.with_suffix(path.suffix + ".gz")
    # Failure recovery replaces only a gzip file in this fresh owned attempt.
    with path.open("rb") as source, compressed.open("wb") as destination:
        with gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=0, compresslevel=9) as output:
            shutil.copyfileobj(source, output, length=1_048_576)
    return compressed


def _compact_geojson(root: Path, *, partial_export: bool = False) -> dict[str, Any]:
    """Validate all copies before unlinking any owned raw GeoJSON files."""
    artifacts = []
    verified_paths: list[Path] = []
    for path in sorted(root.rglob("*.geojson")):
        path = _owned_file(path, root)
        compressed = path.with_suffix(path.suffix + ".gz")
        if partial_export or not compressed.exists():
            compressed = _compress_if_needed(path)
        compressed = _owned_file(compressed, root)
        with path.open("rb") as source:
            raw_digest, raw_bytes = _stream_digest(source)
        with gzip.open(compressed, "rb") as decoded:
            decoded_digest, decoded_bytes = _stream_digest(decoded)
        if (decoded_digest, decoded_bytes) != (raw_digest, raw_bytes):
            raise ValueError(f"Gzip roundtrip mismatch for {path.name}; raw files retained.")
        artifacts.append({
            "logical_path": path.relative_to(root).as_posix(),
            "gzip_path": compressed.relative_to(root).as_posix(),
            "raw_bytes": raw_bytes, "gzip_bytes": compressed.stat().st_size,
            "raw_sha256": raw_digest,
        })
        verified_paths.append(path)
    for path in verified_paths:
        path.unlink()
    return {
        "raw_geojson_retained": False,
        "gzip_roundtrip_verified": True,
        "geojson_artifact_count": len(artifacts),
        "artifacts": artifacts,
        "logical_urls_require_gzip_delivery": True,
        "delivery": "Serve logical .geojson URLs from their .geojson.gz files with Content-Encoding: gzip.",
        "partial_export": partial_export,
    }


def source_geometry_context(shapefile_path: Path) -> dict[str, Any]:
    """Inspect the cheap source extent before using the original planar adapter."""
    with shapefile.Reader(str(shapefile_path)) as source:
        bbox = [float(value) for value in source.bbox]
    if len(bbox) != 4 or not all(math.isfinite(value) for value in bbox):
        raise UnsupportedStateGeometryError("Source extent is not a finite longitude/latitude box.")
    if not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
        raise UnsupportedStateGeometryError("Source extent is outside the supported longitude/latitude domain.")
    longitude_span = bbox[2] - bbox[0]
    if longitude_span > 180:
        raise UnsupportedStateGeometryError(
            "Source spans the antimeridian; original-longitude planar adjacency/export "
            "cannot certify cross-dateline connectivity. Explicit longitude normalization "
            "and matching topology/export support are required; no bridges were added."
        )
    return {
        "source_bbox": bbox, "longitude_span_degrees": longitude_span,
        "antimeridian_normalization_applied": False,
        "shared_edge_antimeridian_normalization_supported": False,
        "area_and_simplification_projection": "approximate source-bbox-centered equirectangular plane",
    }


def _validate_assignments(
    assignments: Mapping[str, int], populations: Mapping[str, int], state_fips: str,
    n_districts: int,
) -> tuple[list[int], list[int]]:
    if not isinstance(state_fips, str) or len(state_fips) != 2 or not state_fips.isascii() or not state_fips.isdigit():
        raise ValueError("state_fips must be a two-digit ASCII identifier.")
    if isinstance(n_districts, bool) or not isinstance(n_districts, Integral) or n_districts < 1:
        raise ValueError("n_districts must be a positive integer.")
    if not assignments or set(assignments) != set(populations):
        raise ValueError("Assignments and populations must cover the same nonempty block set.")
    totals, counts = [0] * n_districts, [0] * n_districts
    for geoid, district in assignments.items():
        if not isinstance(geoid, str) or len(geoid) != 15 or not geoid.isascii() or not geoid.isdigit() or not geoid.startswith(state_fips):
            raise ValueError(f"Block GEOID {geoid!r} does not belong to state {state_fips}.")
        if isinstance(district, bool) or not isinstance(district, Integral) or not 0 <= district < n_districts:
            raise ValueError("District assignments must be integer indices in [0, n_districts).")
        population = populations[geoid]
        if isinstance(population, bool) or not isinstance(population, Integral) or population < 0:
            raise ValueError("Block populations must be nonnegative integers.")
        totals[district] += int(population)
        counts[district] += 1
    if not all(counts):
        raise ValueError("Every requested district must contain at least one block.")
    return totals, counts


def export_state_block_maps(
    shapefile_path: Path, assignments: Mapping[str, int], populations: Mapping[str, int],
    output_dir: Path, *, state_fips: str, state_name: str, n_districts: int,
    water_connections: Sequence[Mapping[str, Any]] | None = None,
    exclave_connections: Sequence[Mapping[str, Any]] | None = None,
    recorded_connections: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Export strict state maps, retaining verified gzip copies of all GeoJSON.

    ``output_dir`` must be absent or empty. Its new files belong exclusively to
    this attempt. Logical uncompressed URLs remain in the manifest, while a
    gzip-aware server must deliver the retained compressed files. Small JSON
    indexes/manifests remain directly readable. Failed exports retain compressed
    diagnostics and are never declared usable strict plans.

    An explicit ``water_connections`` list opts into separately named policy
    connectivity. Physical strict validation remains false for multipart
    districts. Endpoints must name their source GEOID, within-block part index,
    global part node (assignment mapping order, then source part order), and
    original-coordinate boundary point. No bridge geometry is created.
    ``exclave_connections`` opts into a separately labeled exception that may
    cross another state's land. ``recorded_connections`` accepts a mixed list
    with each link explicitly classified as water or exclave. All three policy
    arguments are mutually exclusive; no connection changes source geography.
    """
    started = time.perf_counter()
    if sum(value is not None for value in (water_connections, exclave_connections, recorded_connections)) > 1:
        raise ValueError("Choose exactly one explicit recorded connection policy; policy arguments cannot be combined.")
    totals, counts = _validate_assignments(assignments, populations, state_fips, n_districts)
    if not isinstance(state_name, str) or not state_name.strip():
        raise ValueError("state_name must be nonempty.")
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Map output directory must be empty; prior artifacts are preserved.")
    geography = source_geometry_context(shapefile_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        manifest = original_exporter.export_maps(shapefile_path, assignments, populations, output_dir)
    except Exception as error:
        storage = _compact_geojson(output_dir, partial_export=True)
        _write_json(output_dir / "failed-export-storage.json", {
            "status": "failed", "state_fips": state_fips, "state_name": state_name,
            "error": f"{type(error).__name__}: {error}", "storage": storage,
            "note": "Partial compressed bytes are diagnostics, not validated complete map artifacts.",
        })
        raise

    manifest["state_fips"] = state_fips
    manifest["state_name"] = state_name
    manifest["geography"] = geography
    manifest["load_scenarios"]["national_state_only"] = manifest["load_scenarios"].pop("national_kansas_only")
    quality = manifest["quality"]
    issues = []
    physical_connectivity_issues = []
    if quality["source_invalid_geometries"] or quality["repaired_source_area_change_square_meters"] != 0:
        issues.append("Source geometry was repaired; strict runs require unchanged valid source polygons.")
    if quality["district_coverage_is_valid"] is not True or not quality["dissolved_geometries_valid"]:
        issues.append("Full district coverage did not pass geometry validation.")
    if quality["source_blocks"] != len(assignments) or quality["assigned_source_blocks"] != len(assignments):
        issues.append("Exported block coverage disagrees with assignments.")
    districts = quality["districts"]
    if set(districts) != {str(index) for index in range(n_districts)}:
        issues.append("Exported district identifiers disagree with the requested count.")
    else:
        for district in range(n_districts):
            result = districts[str(district)]
            if result["population"] != totals[district] or result["block_count"] != counts[district]:
                issues.append(f"District {district} population/block count failed independent reconciliation.")
            if result["polygon_components"] != 1:
                physical_connectivity_issues.append(f"District {district} has {result['polygon_components']} polygon components.")
    for level, simplified in quality["simplification"].items():
        if simplified["coverage_is_valid"] is not True or not simplified["geometries_valid"]:
            issues.append(f"{level} display coverage failed validation.")
    strict_issues = issues + physical_connectivity_issues
    manifest["strict_validation"] = {"passed": not strict_issues, "issues": strict_issues}
    acceptance_issues = list(strict_issues)
    connections = recorded_connections if recorded_connections is not None else water_connections if water_connections is not None else exclave_connections
    connection_type = "mixed" if recorded_connections is not None else "water" if water_connections is not None else "exclave"
    if connections is not None:
        try:
            validation, connections_geojson = _validate_recorded_connection_geometry(
                shapefile_path, assignments, output_dir, state_fips, n_districts,
                connections, connection_type=connection_type,
            )
            validation["issues"] = issues + validation["issues"]
            validation["passed"] = not validation["issues"]
            manifest["connectivity_validation"] = validation
            artifact_prefix = "recorded" if connection_type == "mixed" else connection_type
            connection_path = output_dir / f"{artifact_prefix}-connections.geojson"
            _write_json(connection_path, connections_geojson)
            connection_key = f"{artifact_prefix}_connections"
            manifest[connection_key] = original_exporter._artifact_sizes(connection_path, output_dir)
            manifest[connection_key]["connection_count"] = len(connections_geojson["features"])
            if connection_type == "water":
                manifest["notes"].append(
                    "Declared water connections are display lines and graph exceptions, not land bridges. "
                    "Physical polygon connectivity and policy connectivity are reported separately."
                )
            elif connection_type == "exclave":
                manifest["notes"].append(
                    "Declared exclave connections are explicit graph exceptions that may cross another state's land and water. "
                    "No source polygons, foreign-state territory, bridges, or travel routes are added. "
                    "Physical polygon connectivity and policy connectivity are reported separately."
                )
            else:
                manifest["notes"].append(
                    "Recorded connections retain distinct water-only and exclave labels and audited surface crossings. "
                    "No source polygons, foreign-state territory, bridges, or travel routes are added. "
                    "Physical polygon connectivity and policy connectivity are reported separately."
                )
            acceptance_issues = validation["issues"]
        except (ValueError, TypeError, KeyError, shapely.errors.GEOSException) as error:
            acceptance_issues = issues + [f"{connection_type.capitalize()} connection validation failed: {error}"]
            manifest["connectivity_validation"] = {
                "policy": f"shared_edges_plus_recorded_{connection_type}_connections", "passed": False,
                "issues": acceptance_issues,
            }
    manifest["storage"] = _compact_geojson(output_dir)
    manifest["timing_seconds"]["state_adapter_total_export"] = time.perf_counter() - started
    manifest["notes"].append("Raw GeoJSON copies are removed only after gzip roundtrip/hash verification; logical URLs require gzip-aware delivery.")
    _write_json(output_dir / "map-manifest.json", manifest)
    if acceptance_issues:
        raise StateMapValidationError("; ".join(acceptance_issues) + f" Diagnostics: {output_dir / 'map-manifest.json'}")
    return manifest
