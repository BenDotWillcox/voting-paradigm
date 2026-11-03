"""Check the Kentucky candidate against official 2020 New Madrid area water.

The county's complete TIGER AREAWATER layer supplies spatial water boundaries,
unlike the whole-block ALAND/AWATER totals in the Missouri context audit.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import zipfile

import shapefile
import shapely
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, box, mapping, shape
from shapely.ops import substring

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".cache/state-block-benchmark/suite-through-1000/diagnostics/kentucky"
SOURCE_URL = "https://www2.census.gov/geo/tiger/TIGER2020/AREAWATER/tl_2020_29143_areawater.zip"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def merged_line_intervals(line, geometries):
    """Union clipped segments along the source line, robust to overlay roundoff."""
    intervals, pending = [], list(geometries)
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
    return merged


def run():
    archive = OUTPUT / "context-source/tl_2020_29143_areawater.zip"
    names = ("area-water-audit.json", "area-water-context.geojson", "connection-surface-segments.geojson")
    if any((OUTPUT / name).exists() for name in names):
        raise FileExistsError("Refusing to overwrite the completed area-water diagnostic.")
    archive_before = digest(archive)
    link_path = OUTPUT / "candidate-links.json"
    link = json.loads(link_path.read_text(encoding="utf-8"))[0]
    endpoints = [endpoint["coordinate"] for endpoint in link["endpoints"]]
    line = LineString(endpoints)
    xmin, ymin, xmax, ymax = line.bounds
    clip = box(xmin - .025, ymin - .025, xmax + .025, ymax + .025)
    ys = 6_371_000 * math.pi / 180
    xs = ys * math.cos(math.radians((ymin + ymax) / 2))
    affine = [xs, 0, 0, ys, -(xmin + xmax) / 2 * xs, -(ymin + ymax) / 2 * ys]
    planar_length = float(affine_transform(line, affine).length)
    source_features, parts, names_crossed = [], [], []
    with zipfile.ZipFile(archive) as zipped:
        stem = next(name[:-4] for name in zipped.namelist() if name.endswith(".shp"))
        with shapefile.Reader(shp=zipped.open(stem + ".shp"), shx=zipped.open(stem + ".shx"),
                              dbf=zipped.open(stem + ".dbf")) as reader:
            full_feature_count = reader.numRecords
            for record in reader.iterShapeRecords(bbox=clip.bounds):
                geometry = shape(record.shape.__geo_interface__)
                if not geometry.is_valid:
                    raise ValueError("Official area-water geometry is invalid.")
                props = record.record.as_dict()
                if geometry.intersects(line):
                    parts.append(geometry.intersection(line))
                    names_crossed.append({"name": props["FULLNAME"], "hydroid": props["HYDROID"], "mtfcc": props["MTFCC"]})
                display_geometry = geometry.intersection(clip).simplify(.00001, preserve_topology=True)
                if not display_geometry.is_empty:
                    source_features.append({"type": "Feature", "geometry": mapping(display_geometry),
                                            "properties": {"name": props["FULLNAME"], "hydroid": props["HYDROID"],
                                                           "mtfcc": props["MTFCC"], "source": "2020 Census TIGER AREAWATER"}})
    water_intervals = merged_line_intervals(line, parts)
    water_fraction = min(1.0, math.fsum(end - start for start, end in water_intervals))
    outside_intervals, cursor = [], 0.0
    for start, end in water_intervals:
        if start > cursor:
            outside_intervals.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < 1:
        outside_intervals.append((cursor, 1.0))
    segment_features = []
    for kind, intervals in (("mapped_water", water_intervals), ("outside_mapped_water", outside_intervals)):
        for start, end in intervals:
            segment_features.append({"type": "Feature", "properties": {"classification": kind,
                                     "length_m": planar_length * (end - start)},
                                     "geometry": mapping(substring(line, start, end, normalized=True))})
    context = json.loads((OUTPUT / "missouri-connection-context.json").read_text(encoding="utf-8"))
    if context["candidate_endpoints"] != endpoints or context["coverage_fraction"] != 1.0:
        raise ValueError("Area-water line must match the fully Missouri-covered candidate.")
    if any(not row["geoid"].startswith("29143") for row in context["crossed_missouri_blocks"]):
        raise ValueError("The candidate extends outside the county covered by this area-water layer.")
    if digest(archive) != archive_before:
        raise ValueError("Area-water source archive changed during inspection.")
    report = {
        "status": "complete", "classification": "crosses_mapped_water_and_land",
        "candidate_id": link["id"], "candidate_endpoints": endpoints,
        "candidate_planar_length_m": planar_length,
        "mapped_water_length_m": planar_length * water_fraction,
        "outside_mapped_water_length_m": planar_length * (1 - water_fraction),
        "mapped_water_fraction": water_fraction,
        "water_only_under_2020_census_area_water": water_fraction >= 1 - 1e-12,
        "water_intervals_normalized": water_intervals, "outside_water_intervals_normalized": outside_intervals,
        "crossed_water_features": names_crossed,
        "county_fips": "29143", "county": "New Madrid County, Missouri",
        "source_url": SOURCE_URL, "source_archive": archive.relative_to(ROOT).as_posix(),
        "source_archive_sha256": archive_before, "source_archive_bytes": archive.stat().st_size,
        "source_archive_byte_identical_before_after": True, "source_geometry_modified": False,
        "county_area_water_feature_count": full_feature_count,
        "candidate_file_sha256": digest(link_path), "script_sha256": digest(Path(__file__)),
        "shapely_version": shapely.__version__, "geos_version": shapely.geos_version_string,
        "measurement": "Local equirectangular lengths of line intervals intersected with exact 2020 area-water polygons.",
        "interpretation": "The nearest Kentucky census-coverage connection crosses the Mississippi River twice and Missouri land between those crossings; it is not water-only in the 2020 Census geography.",
        "limits": ["The water layer describes 2020 mapped geography, not current river levels, navigability, or a travel route.",
                   "This audit checks the nearest straight candidate; it does not search for a longer curved route that stays over water.",
                   "Displayed water polygons are clipped and simplified; line intersections use unsimplified source polygons."],
    }
    payloads = (report, {"type": "FeatureCollection", "features": source_features},
                {"type": "FeatureCollection", "features": segment_features})
    for name, value in zip(names, payloads, strict=True):
        (OUTPUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
