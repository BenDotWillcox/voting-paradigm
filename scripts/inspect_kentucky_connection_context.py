"""Inspect a proposed Kentucky connection against Missouri census coverage.

Reads the existing official archive directly without extraction or mutation.
ALAND20/AWATER20 classify whole blocks, not locations inside mixed blocks.
No geometry or districting policy is changed by this diagnostic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import zipfile

import shapefile
import shapely
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, box, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT / ".cache/state-block-benchmark/source/29/tl_2020_29_tabblock20.zip"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_connection(archive: Path, endpoints: list[list[float]]) -> tuple[dict, dict]:
    if len(endpoints) != 2 or any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in endpoints):
        raise ValueError("Expected two finite longitude/latitude endpoints.")
    line = LineString(endpoints)
    if line.length <= 0:
        raise ValueError("Connection must have positive length.")
    digest_before = sha256(archive)
    manifest = archive.with_suffix(".manifest.json")
    expected_digest = json.loads(manifest.read_text(encoding="utf-8"))["archive_sha256"]
    if digest_before != expected_digest:
        raise ValueError("Missouri archive differs from the preserved source manifest hash.")
    xmin, ymin, xmax, ymax = line.bounds
    # This margin is only for visible contextual geometry. Intersections use the
    # exact unbuffered candidate line and unmodified source block geometries.
    query_bbox = (xmin - .025, ymin - .025, xmax + .025, ymax + .025)
    clip = box(*query_bbox)
    radius = 6_371_000.0
    lon0, lat0 = (xmin + xmax) / 2, (ymin + ymax) / 2
    ys = radius * math.pi / 180
    xs = ys * math.cos(math.radians(lat0))
    affine = [xs, 0, 0, ys, -lon0 * xs, -lat0 * ys]

    def length_m(geometry):
        return float(affine_transform(geometry, affine).length)

    def covered_fraction(geometries):
        # Overlay endpoints can differ from the input line by roundoff. Exact
        # line.difference(clipped_line) can then report the entire line as left
        # over despite complete coverage. Audit unioned linear-reference
        # intervals instead; projection here does not alter source geometry.
        intervals = []
        pending = list(geometries)
        while pending:
            geometry = pending.pop()
            if geometry.is_empty:
                continue
            if geometry.geom_type in ("MultiLineString", "GeometryCollection"):
                pending.extend(geometry.geoms)
            elif geometry.geom_type == "LineString":
                positions = [line.project(Point(coordinate), normalized=True) for coordinate in geometry.coords]
                intervals.append((min(positions), max(positions)))
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return min(1.0, math.fsum(end - start for start, end in merged))

    rows, features, intersections = [], [], []
    with zipfile.ZipFile(archive) as zipped:
        names = [n for n in zipped.namelist() if n.endswith(".shp")]
        if len(names) != 1:
            raise ValueError("Expected one block shapefile in Missouri archive.")
        stem = names[0][:-4]
        with shapefile.Reader(shp=zipped.open(stem + ".shp"), shx=zipped.open(stem + ".shx"),
                              dbf=zipped.open(stem + ".dbf")) as reader:
            for record in reader.iterShapeRecords(fields=["GEOID20", "ALAND20", "AWATER20", "POP20"], bbox=query_bbox):
                geometry = shape(record.shape.__geo_interface__)
                properties = record.record.as_dict()
                if not str(properties["GEOID20"]).startswith("29"):
                    raise ValueError("Archive contains a block outside Missouri.")
                land, water = int(properties["ALAND20"]), int(properties["AWATER20"])
                category = ("water_only" if land == 0 and water > 0 else
                            "land_only" if land > 0 and water == 0 else
                            "mixed_land_water" if land > 0 and water > 0 else "zero_recorded_area")
                exact_intersection = line.intersection(geometry)
                interior_intersection = exact_intersection.difference(geometry.boundary)
                interior_length = length_m(interior_intersection)
                props = {"state": "Missouri", "geoid": properties["GEOID20"], "land_area_m2": land,
                         "water_area_m2": water, "population": int(properties["POP20"]),
                         "block_area_class": category, "candidate_interior_length_m": interior_length}
                if interior_length > 0:
                    rows.append({**props, "intersection_geometry": mapping(interior_intersection)})
                    intersections.append(interior_intersection)
                display_geometry = geometry.intersection(clip).simplify(.00001, preserve_topology=True)
                if not display_geometry.is_empty:
                    features.append({"type": "Feature", "geometry": mapping(display_geometry), "properties": props})
    rows.sort(key=lambda row: row["geoid"])
    candidate_length = length_m(line)
    coverage = covered_fraction(intersections)
    category_lengths = {}
    for category in sorted({row["block_area_class"] for row in rows}):
        parts = [shape(row["intersection_geometry"]) for row in rows if row["block_area_class"] == category]
        category_lengths[category] = candidate_length * covered_fraction(parts)
    digest_after = sha256(archive)
    if digest_after != digest_before:
        raise ValueError("Source archive changed during diagnostic inspection.")
    report = {
        "status": "complete", "analysis": "candidate_line_in_missouri_census_coverage",
        "source_archive": str(archive.resolve()), "source_archive_sha256": digest_after,
        "source_archive_matches_preserved_manifest": True, "source_archive_byte_identical_before_after": True,
        "source_url": "https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_29_tabblock20.zip",
        "script_sha256": sha256(Path(__file__)),
        "shapely_version": shapely.__version__, "geos_version": shapely.geos_version_string,
        "source_geometry_modified": False, "source_archive_extracted": False,
        "candidate_endpoints": endpoints, "candidate_planar_length_m": candidate_length,
        "missouri_interior_coverage_m": candidate_length * coverage,
        "uncovered_candidate_length_m": candidate_length * (1 - coverage),
        "coverage_fraction": coverage,
        "coverage_by_whole_block_area_class_m": category_lengths,
        "crossed_missouri_blocks": rows,
        "measurement": "Local equirectangular lengths; exact source-polygon intersections are unioned as linear-reference intervals on the candidate to avoid collinear overlay roundoff.",
        "limits": ["Block ALAND20/AWATER20 totals do not locate water within mixed land/water blocks.",
                   "This is a conceptual policy connection, not an established bridge, ferry, travel route, or boundary change.",
                   "Displayed contextual blocks are clipped and simplified; the intersection audit uses unsimplified source geometry."],
    }
    return report, {"type": "FeatureCollection", "features": features}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--endpoints", type=float, nargs=4, required=True, metavar=("LON1", "LAT1", "LON2", "LAT2"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    names = ("missouri-connection-context.json", "missouri-context.geojson")
    if any((args.output / name).exists() for name in names):
        raise FileExistsError("Refusing to overwrite an existing connection context diagnostic.")
    report, context = inspect_connection(args.archive, [args.endpoints[:2], args.endpoints[2:]])
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in (("missouri-connection-context.json", report), ("missouri-context.geojson", context)):
        destination = args.output / name
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite an existing diagnostic: {destination}")
        destination.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "crossed_missouri_blocks"}, indent=2))
    print("Crossed blocks:", [(r["geoid"], r["block_area_class"], r["candidate_interior_length_m"]) for r in report["crossed_missouri_blocks"]])


if __name__ == "__main__":
    main()
