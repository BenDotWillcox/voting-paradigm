#!/usr/bin/env python3
"""
One-shot script: download the US-states cartographic boundary shapefile
from the Census Bureau and convert it to a GeoJSON FeatureCollection.

Source: US Census Bureau, *2020 Cartographic Boundary Files*, 1:20,000,000
resolution. This is the smallest official simplification that's still
suitable for national-scale display (~700KB unzipped, ~1MB GeoJSON).
The 1:5m and 1:500k variants are larger and aimed at sub-national zoom.

Why not us-atlas's pre-projected blob (what we used in step 2)? Because
us-atlas applies `d3.geoAlbersUsa()` *before* shipping — Alaska and
Hawaii get translated into insets in the lower-left of the contiguous
48. That's perfect for a national overview but wrong for a state detail
view: cropping to AK's bbox renders the inset, not real Alaska.

Working in raw lat/lon (NAD83/EPSG:4269 in this file; ≤ 1m off WGS84
in CONUS — invisible at our zoom levels) lets the renderer apply the
*right* projection per context: AlbersUSA composite for the national
overview, a state-fitted Albers Equal-Area Conic for each state
detail view.

Output: public/data/us-states.json — a GeoJSON FeatureCollection where
each feature has:
  - id: 2-char zero-padded FIPS state code (e.g. "06")
  - properties.name: state name (e.g. "California")
  - properties.abbr: 2-char postal code (e.g. "CA")
  - geometry: Polygon or MultiPolygon in [lon, lat] degrees

Re-run any time the upstream Census data updates. Output is checked in.

Usage:
    python scripts/fetch_map_data.py
"""

from __future__ import annotations

import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

import shapefile  # pyshp


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Census Bureau 2020 cartographic boundary file, simplified to ~1:20M.
# https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html
CB_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2020/shp/"
    "cb_2020_us_state_20m.zip"
)
OUT_PATH = PROJECT_ROOT / "public" / "data" / "us-states.json"

# State FIPS codes to keep. DC and the territories receive no voting
# House representation under current law and are out of scope for v1
# (see prompts/demo-3-districting.md decision #5). We strip them at
# conversion time so the file we ship matches what the renderer will
# actually display.
STATE_FIPS_KEEP = {
    "01", "02", "04", "05", "06", "08", "09", "10",
    "12", "13", "15", "16", "17", "18", "19", "20",
    "21", "22", "23", "24", "25", "26", "27", "28",
    "29", "30", "31", "32", "33", "34", "35", "36",
    "37", "38", "39", "40", "41", "42", "44", "45",
    "46", "47", "48", "49", "50", "51", "53", "54",
    "55", "56",
}


def _download_zip(url: str) -> bytes:
    sys.stdout.write(f"Downloading {url}\n")
    with urllib.request.urlopen(url) as resp:  # noqa: S310 — trusted source
        data = resp.read()
    sys.stdout.write(f"  got {len(data) / 1024:.1f} KB\n")
    return data


def _shapefile_reader_from_zip(zip_bytes: bytes) -> shapefile.Reader:
    """
    pyshp wants three streams (.shp, .dbf, .shx). The Census zip has
    them at the top level; pull each into an in-memory buffer.
    """
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    members = {Path(n).suffix.lower(): n for n in z.namelist()}
    required = (".shp", ".dbf", ".shx")
    missing = [ext for ext in required if ext not in members]
    if missing:
        raise RuntimeError(
            f"Census zip is missing required members: {missing}; "
            f"saw {sorted(members)}"
        )
    # Read into memory rather than streaming — pyshp seeks inside .shx.
    streams = {ext: io.BytesIO(z.read(members[ext])) for ext in required}
    return shapefile.Reader(
        shp=streams[".shp"], dbf=streams[".dbf"], shx=streams[".shx"]
    )


def _shape_to_geojson_geometry(shape: shapefile.Shape) -> dict:
    """
    Convert a pyshp Shape (polygon or polygonZ) into a GeoJSON Polygon
    or MultiPolygon. Census state shapes are MultiPolygon for any state
    with islands or Great Lakes coastline (most of them).
    """
    parts = list(shape.parts) + [len(shape.points)]
    rings = [
        [list(pt) for pt in shape.points[parts[i]:parts[i + 1]]]
        for i in range(len(parts) - 1)
    ]
    # In the Census shapefile each part is its own outer ring; there
    # are no holes. (If there were, they'd appear as inner rings of the
    # parent polygon — pyshp doesn't tell us that, so we'd need a
    # ring-orientation pass. For state outlines this is fine.)
    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": [rings[0]]}
    return {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}


def _build_features(reader: shapefile.Reader) -> list[dict]:
    """
    Walk the shapefile's records; emit one GeoJSON feature per kept
    state. The dbf field layout for cb_2020_us_state_20m is:
        STATEFP   2-char FIPS
        STATENS
        AFFGEOID
        GEOID
        STUSPS    2-char postal
        NAME      "California" etc.
        LSAD
        ALAND
        AWATER
    """
    field_names = [f[0] for f in reader.fields[1:]]  # skip DeletionFlag
    fips_idx = field_names.index("STATEFP")
    name_idx = field_names.index("NAME")
    abbr_idx = field_names.index("STUSPS")

    features: list[dict] = []
    for sr in reader.shapeRecords():
        rec = sr.record
        fips = rec[fips_idx]
        if fips not in STATE_FIPS_KEEP:
            continue
        feature = {
            "type": "Feature",
            "id": fips,  # 2-char zero-padded; matches our Python/JS conventions
            "properties": {
                "name": rec[name_idx],
                "abbr": rec[abbr_idx],
            },
            "geometry": _shape_to_geojson_geometry(sr.shape),
        }
        features.append(feature)
    # Stable order: sort by FIPS so file diffs are review-friendly.
    features.sort(key=lambda f: f["id"])
    return features


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    zip_bytes = _download_zip(CB_URL)
    reader = _shapefile_reader_from_zip(zip_bytes)
    features = _build_features(reader)

    if len(features) != 50:
        sys.stderr.write(
            f"Expected 50 states; got {len(features)}. "
            "Did the Census schema change?\n"
        )
        return 1

    fc = {"type": "FeatureCollection", "features": features}
    payload = json.dumps(fc, separators=(",", ":"), ensure_ascii=False)
    OUT_PATH.write_text(payload, encoding="utf-8")
    size_kb = OUT_PATH.stat().st_size / 1024
    sys.stdout.write(
        f"Wrote {len(features)} states to {OUT_PATH.relative_to(PROJECT_ROOT)} "
        f"({size_kb:.1f} KB)\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
