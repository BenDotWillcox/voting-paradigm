"""Export cached block assignments without loading all block coordinates at once.

County GeoJSON shards retain the source coordinate precision. District outlines
are dissolved in bounded batches, then simplified as a coverage when supported
by Shapely. These are benchmark artifacts, not an application data contract.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from contextlib import ExitStack
import gzip
import json
import math
from pathlib import Path
import shutil
import time
from typing import Any, TextIO

import shapefile
import shapely
from shapely.affinity import affine_transform
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


_DISSOLVE_BATCH_SIZE = 2_000
_EARTH_RADIUS_METERS = 6_371_000.0
_DISPLAY_TOLERANCES_METERS = {"state": 30.0, "national": 250.0}


def _write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, separators=(",", ":"), allow_nan=False)
        output.write("\n")


def _artifact_sizes(path: Path, output_dir: Path) -> dict[str, Any]:
    """Persist a repeatable gzip representation, excluding names and timestamps."""
    gzip_path = path.with_suffix(path.suffix + ".gz")
    with path.open("rb") as source, gzip_path.open("wb") as destination:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=destination, mtime=0, compresslevel=9
        ) as compressed:
            shutil.copyfileobj(source, compressed, length=1_048_576)
    return {
        "path": path.relative_to(output_dir).as_posix(),
        "gzip_path": gzip_path.relative_to(output_dir).as_posix(),
        "raw_bytes": path.stat().st_size,
        "gzip_bytes": gzip_path.stat().st_size,
    }


def _polygonal_only(geometry: BaseGeometry) -> BaseGeometry:
    if geometry.geom_type in ("Polygon", "MultiPolygon"):
        return geometry
    if geometry.geom_type == "GeometryCollection":
        return unary_union(
            [
                _polygonal_only(part)
                for part in geometry.geoms
                if part.geom_type in ("Polygon", "MultiPolygon", "GeometryCollection")
            ]
        )
    raise ValueError(f"Expected polygonal block geometry, got {geometry.geom_type}.")


def _component_summary(geometry: BaseGeometry) -> dict[str, Any]:
    components = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    areas = sorted((float(part.area) for part in components), reverse=True)
    return {
        "polygon_components": len(areas),
        "largest_component_area_fraction": areas[0] / sum(areas) if sum(areas) else None,
    }


def _features(
    district_ids: list[int],
    geometries: list[BaseGeometry],
    populations: Mapping[int, int],
    block_counts: Mapping[int, int],
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": f"district-{district_id}",
                "properties": {
                    "district_id": district_id,
                    "population": populations[district_id],
                    "block_count": block_counts[district_id],
                },
                "geometry": mapping(geometry),
            }
            for district_id, geometry in zip(district_ids, geometries, strict=True)
        ],
    }


def export_maps(
    shapefile_path: Path,
    assignments: Mapping[str, int],
    populations: Mapping[str, int],
    output_dir: Path,
) -> dict[str, Any]:
    """Write outlines and lazy county detail; return measured size/quality metadata.

    Every source block, including zero-population blocks, must have exactly one
    assignment and an explicit population. Missing or extra GEOIDs fail closed.
    Geometry checks refer to the supplied block coverage, not an independent
    official state boundary. Areas are approximate local planar measurements.
    """
    started = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    block_dir = output_dir / "blocks"
    block_dir.mkdir(exist_ok=True)
    pending: dict[int, list[BaseGeometry]] = defaultdict(list)
    dissolved_batches: dict[int, list[BaseGeometry]] = defaultdict(list)
    district_populations: dict[int, int] = defaultdict(int)
    district_counts: dict[int, int] = defaultdict(int)
    county_stats: dict[str, dict[str, Any]] = {}
    county_outputs: dict[str, TextIO] = {}
    seen: set[str] = set()
    source_area = 0.0
    repaired_area = 0.0
    invalid_geoids: list[str] = []
    invalid_count = 0
    multipart_count = 0
    zero_population_count = 0
    source_coordinate_count = 0

    def flush_batch(district_id: int) -> None:
        if pending[district_id]:
            dissolved_batches[district_id].append(unary_union(pending[district_id]))
            pending[district_id].clear()

    with shapefile.Reader(str(shapefile_path)) as reader, ExitStack() as stack:
        fields = [field[0] for field in reader.fields[1:]]
        geoid_index = fields.index("GEOID20")
        county_index = fields.index("COUNTYFP20")
        population_index = fields.index("POP20") if "POP20" in fields else None
        bbox = [float(value) for value in reader.bbox]
        print(f"Map export: reading {len(reader):,} source blocks and writing county shards.", flush=True)
        for record in reader.iterShapeRecords():
            geoid = str(record.record[geoid_index])
            county = str(record.record[county_index]).zfill(3)
            if geoid in seen:
                raise ValueError(f"Duplicate source block GEOID {geoid}.")
            seen.add(geoid)
            if geoid not in assignments or geoid not in populations:
                raise ValueError(f"Missing assignment or population for source block {geoid}.")
            district_id = int(assignments[geoid])
            population = int(populations[geoid])
            if population < 0:
                raise ValueError(f"Negative population for source block {geoid}.")
            if population_index is not None and int(record.record[population_index]) != population:
                raise ValueError(f"Population mapping disagrees with source POP20 for {geoid}.")
            raw_geometry = record.shape.__geo_interface__
            geometry = shape(raw_geometry)
            source_area += float(geometry.area)
            if not geometry.is_valid:
                invalid_count += 1
                if len(invalid_geoids) < 20:
                    invalid_geoids.append(geoid)
                geometry = _polygonal_only(shapely.make_valid(geometry))
                raw_geometry = mapping(geometry)
            if geometry.is_empty or geometry.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError(f"Block {geoid} has empty or nonpolygonal geometry.")
            if not geometry.is_valid:
                raise ValueError(f"Geometry repair failed for source block {geoid}.")
            repaired_area += float(geometry.area)
            source_coordinate_count += len(record.shape.points)
            multipart_count += int(geometry.geom_type == "MultiPolygon")
            zero_population_count += int(population == 0)
            pending[district_id].append(geometry)
            district_populations[district_id] += population
            district_counts[district_id] += 1
            if len(pending[district_id]) >= _DISSOLVE_BATCH_SIZE:
                flush_batch(district_id)

            bounds = geometry.bounds
            if county not in county_outputs:
                destination = stack.enter_context(
                    (block_dir / f"county-{county}.geojson").open(
                        "w", encoding="utf-8", newline="\n"
                    )
                )
                destination.write('{"type":"FeatureCollection","features":[')
                county_outputs[county] = destination
                county_stats[county] = {
                    "county_fips": county,
                    "block_count": 0,
                    "population": 0,
                    "bbox": list(bounds),
                }
            stats = county_stats[county]
            if stats["block_count"]:
                county_outputs[county].write(",")
            json.dump(
                {
                    "type": "Feature",
                    "id": geoid,
                    "properties": {
                        "geoid": geoid,
                        "district_id": district_id,
                        "population": population,
                    },
                    "geometry": raw_geometry,
                },
                county_outputs[county],
                separators=(",", ":"),
                allow_nan=False,
            )
            stats["block_count"] += 1
            stats["population"] += population
            stats["bbox"] = [
                min(stats["bbox"][0], bounds[0]),
                min(stats["bbox"][1], bounds[1]),
                max(stats["bbox"][2], bounds[2]),
                max(stats["bbox"][3], bounds[3]),
            ]
            if len(seen) % 25_000 == 0:
                print(f"Map export: {len(seen):,} blocks processed.", flush=True)
        for destination in county_outputs.values():
            destination.write("]}\n")

    if set(assignments) != seen or set(populations) != seen:
        raise ValueError("Assignment/population GEOIDs do not exactly match the source shapefile.")
    if not seen:
        raise ValueError("Cannot export an empty block shapefile.")
    read_and_batch_seconds = time.perf_counter() - started
    district_ids = sorted(district_counts)
    for district_id in district_ids:
        flush_batch(district_id)
    geometries = []
    for district_id in district_ids:
        print(f"Map export: dissolving district {district_id}.", flush=True)
        geometries.append(unary_union(dissolved_batches[district_id]))
    del dissolved_batches, pending
    if not all(geometry.is_valid for geometry in geometries):
        raise ValueError("Dissolved district geometry is invalid.")
    source_union = unary_union(geometries)
    union_area = float(source_union.area)
    district_area_sum = sum(float(geometry.area) for geometry in geometries)
    lat0 = (bbox[1] + bbox[3]) / 2
    lon0 = (bbox[0] + bbox[2]) / 2
    y_scale = math.pi / 180 * _EARTH_RADIUS_METERS
    x_scale = y_scale * math.cos(math.radians(lat0))
    area_scale = x_scale * y_scale
    projection = [x_scale, 0, 0, y_scale, -lon0 * x_scale, -lat0 * y_scale]
    inverse_projection = [1 / x_scale, 0, 0, 1 / y_scale, lon0, lat0]
    coverage_checker = getattr(shapely, "coverage_is_valid", None)
    source_coverage_valid = bool(coverage_checker(geometries)) if coverage_checker else None
    full_path = output_dir / "districts-full.geojson"
    _write_json(full_path, _features(district_ids, geometries, district_populations, district_counts))
    outline_artifacts = {"full": _artifact_sizes(full_path, output_dir)}
    outline_artifacts["full"]["coordinate_count"] = sum(
        int(shapely.get_num_coordinates(geometry)) for geometry in geometries
    )
    quality: dict[str, Any] = {
        "source_blocks": len(seen),
        "assigned_source_blocks": len(seen),
        "zero_population_blocks": zero_population_count,
        "source_coordinate_count": source_coordinate_count,
        "source_invalid_geometries": invalid_count,
        "source_invalid_geoid_examples": invalid_geoids,
        "source_multipart_blocks": multipart_count,
        "invalid_geometry_policy": "make_valid, retain polygonal components; fail if empty or still invalid",
        "repaired_source_area_change_square_meters": (repaired_area - source_area) * area_scale,
        "dissolved_geometries_valid": True,
        "district_coverage_is_valid": source_coverage_valid,
        "source_block_area_sum_square_meters": repaired_area * area_scale,
        "source_union_area_square_meters": union_area * area_scale,
        "source_area_sum_minus_union_square_meters": (repaired_area - union_area) * area_scale,
        "district_overlap_area_square_meters": max(0.0, district_area_sum - union_area) * area_scale,
        "coverage_reference": "all supplied source blocks; no independent state boundary comparison",
        "area_measurement": "approximate state-centered equirectangular plane, including water",
        "projection_center": {"longitude": lon0, "latitude": lat0},
        "districts": {
            str(district_id): {
                **_component_summary(geometry),
                "population": district_populations[district_id],
                "block_count": district_counts[district_id],
            }
            for district_id, geometry in zip(district_ids, geometries, strict=True)
        },
        "simplification": {},
    }
    coverage_simplifier = getattr(shapely, "coverage_simplify", None)
    projected = [affine_transform(geometry, projection) for geometry in geometries]
    for level, tolerance in _DISPLAY_TOLERANCES_METERS.items():
        print(f"Map export: deriving {level} district outlines.", flush=True)
        use_coverage = source_coverage_valid is True and coverage_simplifier is not None
        if use_coverage:
            simplified_projected = list(coverage_simplifier(projected, tolerance))
            method = "shared-edge Visvalingam-Whyatt coverage simplification"
        else:
            simplified_projected = [
                geometry.simplify(tolerance, preserve_topology=True) for geometry in projected
            ]
            method = "independent topology-preserving simplification; shared borders may diverge"
        simplified = [affine_transform(geometry, inverse_projection) for geometry in simplified_projected]
        if not all(geometry.is_valid for geometry in simplified):
            raise ValueError(f"Simplified {level} display geometry is invalid.")
        simplified_union = unary_union(simplified)
        overlap_area = max(
            0.0, sum(float(geometry.area) for geometry in simplified) - simplified_union.area
        )
        simplified_path = output_dir / f"districts-{level}.geojson"
        _write_json(
            simplified_path,
            _features(district_ids, simplified, district_populations, district_counts),
        )
        outline_artifacts[level] = _artifact_sizes(simplified_path, output_dir)
        outline_artifacts[level]["coordinate_count"] = sum(
            int(shapely.get_num_coordinates(geometry)) for geometry in simplified
        )
        quality["simplification"][level] = {
            "method": method,
            "tolerance_meters": tolerance,
            "tolerance_meaning": "square root of removed triangle area" if use_coverage else "distance",
            "geometries_valid": True,
            "coverage_is_valid": bool(coverage_checker(simplified)) if coverage_checker else None,
            "overlap_square_meters": overlap_area * area_scale,
            "union_symmetric_difference_square_meters": float(
                source_union.symmetric_difference(simplified_union).area
            ) * area_scale,
            "changes_assignments_or_population": False,
        }

    county_artifacts = []
    print(f"Map export: compressing {len(county_stats)} county detail shards.", flush=True)
    for county_number, county in enumerate(sorted(county_stats), start=1):
        county_artifacts.append({
            **county_stats[county],
            **_artifact_sizes(block_dir / f"county-{county}.geojson", output_dir),
        })
        if county_number % 25 == 0:
            print(f"Map export: {county_number} county shards compressed.", flush=True)
    index_path = output_dir / "block-index.json"
    _write_json(index_path, {"bbox": bbox, "counties": county_artifacts})
    index_artifact = _artifact_sizes(index_path, output_dir)
    detail_raw = sum(artifact["raw_bytes"] for artifact in county_artifacts)
    detail_gzip = sum(artifact["gzip_bytes"] for artifact in county_artifacts)
    largest_county = max(county_artifacts, key=lambda artifact: artifact["gzip_bytes"])
    manifest = {
        "shapely_version": shapely.__version__,
        "source_bbox": bbox,
        "district_outlines": outline_artifacts,
        "block_index": index_artifact,
        "county_blocks": county_artifacts,
        "load_scenarios": {
            "national_kansas_only": outline_artifacts["national"],
            "state_entry_outlines_and_detail_index": {
                "raw_bytes": outline_artifacts["state"]["raw_bytes"] + index_artifact["raw_bytes"],
                "gzip_bytes": outline_artifacts["state"]["gzip_bytes"] + index_artifact["gzip_bytes"],
            },
            "all_county_detail_shards": {"raw_bytes": detail_raw, "gzip_bytes": detail_gzip},
            "largest_county_detail_shard": largest_county,
        },
        "quality": quality,
        "timing_seconds": {
            "read_blocks_write_detail_and_partial_dissolve": read_and_batch_seconds,
            "total_export": time.perf_counter() - started,
        },
        "notes": [
            "Gzip sizes are measured bytes for these saved artifacts, not browser memory or latency.",
            "County shards are fetched lazily after state selection; detailed block coordinates are not needed for national or state outline views.",
            "Detail shards retain source coordinate precision. District display simplification changes geometry only, never block assignments or populations.",
            "Polygon component counts describe geometric fragmentation; no adjacency repair is performed by this exporter.",
        ],
    }
    _write_json(output_dir / "map-manifest.json", manifest)
    return manifest
