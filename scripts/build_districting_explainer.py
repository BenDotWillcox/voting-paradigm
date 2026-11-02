"""Build the static data for the Michigan algorithm walkthrough on /districts.

The walkthrough (prompts/demo-3-explainer.md) shows the inputs the saved
Michigan plans were computed from: the 2020 TIGER/Line block source and its
shared-edge block graph. Both are read from the block-plan cache, checked
against their recorded hashes and the saved K13 run's provenance, and reduced
to a few small files under public/data/districting-explainer/ with a hash
manifest. No districting solve runs here.

It also extracts the recorded-link detours (Hawaii, the Kentucky Bend, New York
County, Alaska) from their own block sources and the explorer bundle.

Usage: python scripts/build_districting_explainer.py --cache-root <BLOCK_PLAN_CACHE_ROOT>
"""
from __future__ import annotations

import argparse
from collections import deque
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

import numpy as np
import shapefile  # pyshp, the reader the block pipeline uses
import shapely
import shapely.ops
from shapely.geometry import Point, box, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "public" / "data" / "districting-explainer"
STATE_FIPS = "26"
DISTRICTS = 13
STEM = "tl_2020_26_tabblock20"
RUN = Path("state-block-benchmark/suite-through-1000/states/26/districts-13")
SOURCE = Path("state-block-benchmark/source/26")
GRAPH = Path("state-block-benchmark/graph-cache/26")
ENACTED = Path("enacted-cd118/26")  # TIGER/Line 2023 CD118, with its own manifest
CARTO = Path("block-comparison-sources-v1")  # the explorer's cartographic reference layers
# The Straits chain's shore blocks must have at least this much land, and be mostly land, to read as land on the slide.
MIN_SHORE_LAND_M2 = 50_000
MIN_SHORE_COMPACTNESS = 0.15  # Polsby-Popper; shoreline strips score near 0.02
MIN_MAINLAND_BLOCKS = 25  # land blocks connected to it in the window; an island has far fewer
UPPER_PENINSULA_COUNTIES = {
    "003", "013", "033", "041", "043", "053", "061", "071",
    "083", "095", "097", "103", "109", "131", "153",
}
# Story windows (west, south, east, north). Blocks touching a window are kept
# whole; their display geometry is clipped to a padded window and simplified.
WINDOWS = {
    "detroit": {"bbox": (-83.085, 42.320, -83.020, 42.360), "tolerance": 0.00001},
    "straits": {"bbox": (-84.90, 45.74, -84.55, 45.90), "tolerance": 0.0002},
}
BUNDLE = ROOT / "data" / "districting-block-plans"
# Recorded-link detours: states whose geography does not touch. Local windows
# use each state's own blocks; neighbors are dissolved from their own sources.
SPECIAL_CASES = {
    "hawaii": {"fips": "15"},
    "kentucky": {"fips": "21", "window": (-89.60, 36.44, -89.33, 36.60), "tolerance": 0.00008,
                 "neighbors": {"47": "Tennessee", "29": "Missouri"},
                 # A first view wide enough to place the Bend among its neighbors.
                 "context": {"21": "Kentucky", "29": "Missouri", "47": "Tennessee", "17": "Illinois", "05": "Arkansas"},
                 "contextBounds": (-91.3, 35.55, -87.4, 38.05)},
    "newYork": {"fips": "36", "window": (-74.060, 40.676, -74.005, 40.712), "tolerance": 0.00002,
                "neighbors": {"34": "New Jersey"}},
    "alaska": {"fips": "02"},
}


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_bytes(value) -> bytes:
    """The pipeline's canonical JSON, used for its GEOID-order fingerprints."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def rounded(geometry, digits: int = 6):
    def walk(value):
        if isinstance(value, (list, tuple)) and value and isinstance(value[0], (int, float)):
            return [round(float(value[0]), digits), round(float(value[1]), digits)]
        return [walk(item) for item in value]
    data = mapping(geometry)
    return {"type": data["type"], "coordinates": walk(data["coordinates"])}


def write(path: Path, payload: bytes) -> dict:
    path.write_bytes(payload)
    return {"path": path.name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def open_blocks(cache: Path, fips: str):
    """A reader over one state's 2020 TIGER/Line blocks, checked against its manifest."""
    folder = cache / "state-block-benchmark" / "source" / fips
    stem = f"tl_2020_{fips}_tabblock20"
    manifest = json.loads((folder / f"{stem}.manifest.json").read_text("utf-8"))
    archive = folder / f"{stem}.zip"
    if sha256_file(archive) != manifest["archive_sha256"]:
        raise SystemExit(f"Block source for state {fips} does not match its manifest.")
    with zipfile.ZipFile(archive) as zipped:
        parts = {ext: io.BytesIO(zipped.read(f"{stem}.{ext}")) for ext in ("shp", "shx", "dbf")}
    return shapefile.Reader(shp=parts["shp"], shx=parts["shx"], dbf=parts["dbf"]), manifest["archive_sha256"]


def blocks_in(reader, window):
    """(index, geometry) for every block whose polygon meets the window."""
    w, s, e, n = window
    area = box(*window)
    for index, shape_record in enumerate(reader.iterShapes()):
        west, south, east, north = shape_record.bbox
        if west <= e and east >= w and south <= n and north >= s:
            geom = shape(shape_record.__geo_interface__)
            if geom.intersects(area):
                yield index, geom


def bundle_asset(url: str, cache: Path):
    """A saved explorer asset, read through the bundle's allowlist and checked by hash."""
    assets = json.loads((BUNDLE / "server-index.json").read_text("utf-8"))["assets"]
    name = url.rsplit("/", 1)[-1]
    entry = assets.get(name) or next(value for key, value in assets.items() if url.endswith(key))
    path = next((base / entry["path"] for base in (ROOT, cache.parent) if (base / entry["path"]).exists()), None)
    if path is None:
        raise SystemExit(f"Explorer asset {entry['path']} is not available.")
    raw = path.read_bytes()
    data = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
    if hashlib.sha256(data).hexdigest() != entry["rawSha256"]:
        raise SystemExit(f"Explorer asset {entry['path']} does not match its recorded hash.")
    return json.loads(data)


def recorded_links(collection) -> list[dict]:
    links = []
    for feature in collection["features"]:
        properties = feature["properties"]
        endpoints = properties["endpoints"]
        if isinstance(endpoints, str):
            endpoints = json.loads(endpoints)
        kind = str(properties.get("kind") or properties["id"])
        links.append({
            "id": properties["id"], "kind": "exclave" if "exclave" in kind else "water",
            "distanceM": round(float(properties["distance_m"]), 1),
            "endpoints": [endpoint["geoid"] for endpoint in endpoints],
            "geometry": {"type": "LineString", "coordinates": [[round(x, 6), round(y, 6)] for x, y in feature["geometry"]["coordinates"]]},
        })
    return links


def clip_half_plane(polygon: list[tuple[float, float]], a: tuple[float, float], b: float) -> list[tuple[float, float]]:
    """Sutherland–Hodgman: keep the part of a convex polygon where a·x ≤ b."""
    kept = []
    for index, current in enumerate(polygon):
        previous = polygon[index - 1]
        inside_now = a[0] * current[0] + a[1] * current[1] <= b
        inside_before = a[0] * previous[0] + a[1] * previous[1] <= b
        if inside_now != inside_before:
            dx, dy = current[0] - previous[0], current[1] - previous[1]
            t = (b - a[0] * previous[0] - a[1] * previous[1]) / (a[0] * dx + a[1] * dy)
            kept.append((previous[0] + t * dx, previous[1] + t * dy))
        if inside_now:
            kept.append(current)
    return kept


def power_cells(centers, weights, frame) -> list[list[tuple[float, float]]]:
    """Exact power cells: x is in cell i when |x−cᵢ|² − wᵢ ≤ |x−cⱼ|² − wⱼ for every j."""
    cells = []
    for i, (ci, wi) in enumerate(zip(centers, weights)):
        polygon = list(frame)
        for j, (cj, wj) in enumerate(zip(centers, weights)):
            if i == j:
                continue
            # Expanding both sides leaves a half-plane: 2(cⱼ−cᵢ)·x ≤ |cⱼ|² − |cᵢ|² − (wⱼ − wᵢ).
            a = (2 * (cj[0] - ci[0]), 2 * (cj[1] - ci[1]))
            b = cj[0] ** 2 + cj[1] ** 2 - ci[0] ** 2 - ci[1] ** 2 - (wj - wi)
            polygon = clip_half_plane(polygon, a, b)
            if not polygon:
                break
        cells.append(polygon)
    return cells


def replay_seed_draws(recording: dict, lon, lat, population) -> list[dict]:
    """Each k-means++ draw with its exact chances, replayed from the run's seed.

    The solver draws block i with chance pᵢ / Σp for the first seed and
    pᵢ·Dᵢ² / Σ pⱼ·Dⱼ² afterwards, where Dᵢ is the distance to the nearest seed
    so far, using one uniform number per draw (numpy's Generator.choice). The
    replay must pick the recorded seeds exactly.
    """
    plane = recording["plane"]
    x = (lon - plane["lon0"]) * plane["metersPerDegreeLon"]
    y = (lat - plane["lat0"]) * plane["metersPerDegreeLat"]
    for seed in recording["seeds"]:
        if abs(x[seed["block"]] - seed["x"]) > 1e-6 or abs(y[seed["block"]] - seed["y"]) > 1e-6:
            raise SystemExit("Block internal points do not reproduce the solver's coordinates.")
    pops = population.astype(float)
    rng = np.random.default_rng(recording["seed"])
    dist_sq = None
    draws = []
    for order, seed in enumerate(recording["seeds"], 1):
        weighted = pops if dist_sq is None else pops * dist_sq
        total = float(weighted.sum())
        cdf = weighted.cumsum()
        cdf /= cdf[-1]
        u = float(rng.random())
        index = int(cdf.searchsorted(u, side="right"))
        if index != seed["block"]:
            raise SystemExit(f"Seed draw {order} does not reproduce the recorded seed.")
        chance = float(weighted[index] / total)
        draws.append({"order": order, "block": index, "u": round(u, 6), "chance": chance,
                      "rank": int((weighted > weighted[index]).sum()) + 1, "residents": int(pops[index]),
                      "distanceKm": None if dist_sq is None else round(math.sqrt(dist_sq[index]) / 1000, 2),
                      # Σ pⱼ (people) for the first draw; Σ pⱼDⱼ² in person·km² afterwards.
                      "total": total if dist_sq is None else total / 1e6})
        new = (x - x[index]) ** 2 + (y - y[index]) ** 2
        dist_sq = new if dist_sq is None else np.minimum(dist_sq, new)
    return draws


def build_power_diagram(cache: Path, recording_path: Path, lon, lat, population, archive_sha: str) -> dict:
    """Time-lapse frames from the verified rerun: seeds, then every inner solve."""
    if not recording_path.exists():
        raise SystemExit(f"Missing {recording_path}; run scripts/record_michigan_power_diagram.py first.")
    recording = json.loads(recording_path.read_text("utf-8"))
    if recording["provenance"]["sourceArchiveSha256"] != archive_sha:
        raise SystemExit("The power-diagram recording was made from a different block source.")
    plane = recording["plane"]
    to_degrees = lambda x, y: [round(plane["lon0"] + x / plane["metersPerDegreeLon"], 5), round(plane["lat0"] + y / plane["metersPerDegreeLat"], 5)]
    seeds = recording["seeds"]
    draws = replay_seed_draws(recording, lon, lat, population)
    xs = [(longitude - plane["lon0"]) * plane["metersPerDegreeLon"] for longitude in (lon.min(), lon.max())]
    ys = [(latitude - plane["lat0"]) * plane["metersPerDegreeLat"] for latitude in (lat.min(), lat.max())]
    pad = 150_000
    frame = [(xs[0] - pad, ys[0] - pad), (xs[1] + pad, ys[0] - pad), (xs[1] + pad, ys[1] + pad), (xs[0] - pad, ys[1] + pad)]
    target = recording["targetExact"]

    def snapshot(iteration, centers, weights, populations, max_move):
        floor = min(weights)
        return {
            "iteration": iteration,
            "centers": [to_degrees(x, y) for x, y in centers],
            # Adding a constant to every weight leaves the diagram unchanged, so
            # each weight reads as a reach: the radius √(wᵢ − min w).
            "reachKm": [round(math.sqrt(max(weight - floor, 0)) / 1000, 2) for weight in weights],
            "populations": populations,
            "maxDeviation": round(max(abs(population - target) for population in populations), 2),
            "maxMoveM": None if max_move is None else round(max_move, 4),
            "cells": [[to_degrees(x, y) for x, y in cell] for cell in power_cells(centers, weights, frame)],
        }

    frames = [snapshot(0, [(seed["x"], seed["y"]) for seed in seeds], [0.0] * len(seeds), recording["unweightedPopulations"], None)]
    frames += [snapshot(item["iteration"], item["centers"], item["weights"], item["populations"], item["maxMoveM"]) for item in recording["iterations"]]
    final = recording["final"]
    audit = json.loads((cache / RUN / "move-audit.json").read_text("utf-8"))
    frames.append({**snapshot(len(recording["iterations"]) + 1, final["centers"], final["weights"], final["populations"], None), "final": True})
    return {
        "seed": recording["seed"], "draws": draws, "settings": recording["settings"], "centersConverged": recording["centersConverged"],
        "target": target, "seeds": [{**seed, "point": to_degrees(seed["x"], seed["y"])} for seed in seeds],
        "plane": plane, "detachedPieces": len(audit["repair_moves"]),
        "frames": frames, "provenance": recording["provenance"],
    }


def build_repair(cache: Path, geoids, population, land, lon, lat, neighbors_of, block_record, geometry) -> tuple[dict, bytes]:
    """Repair and rebalancing, replayed move by move from the saved run.

    The repair code that ran is not preserved byte for byte, so nothing is
    rerun: the ordered move audit is replayed from the saved power-diagram
    assignments and must reproduce the saved after-repair and final plans
    exactly. Each repair move must be a whole detached piece (never the
    district's largest-population anchor) that touches its new district; each
    balancing move must strictly improve the exact objective and keep the
    donor connected.
    """
    def saved(name: str) -> np.ndarray:
        assignments = json.loads((cache / RUN / name).read_text("utf-8"))["assignments"]
        return np.array([assignments[geoid] for geoid in geoids], dtype=np.int64)
    initial, repaired, final = (saved(name) for name in ("initial-solver-result.json", "after-repair-result.json", "solver-result.json"))
    audit = json.loads((cache / RUN / "move-audit.json").read_text("utf-8"))
    total, k = int(population.sum()), DISTRICTS

    def populations(labels: np.ndarray) -> np.ndarray:
        return np.bincount(labels, weights=population, minlength=k).astype(np.int64)

    def objective(labels: np.ndarray) -> tuple[int, int]:
        deviations = k * populations(labels) - total  # the solver's exact integer form
        return int(np.abs(deviations).max()), int((deviations * deviations).sum())

    def pieces(labels: np.ndarray, district: int) -> list[list[int]]:
        seen, found = set(), []
        for start in np.flatnonzero(labels == district).tolist():
            if start in seen:
                continue
            seen.add(start)
            queue, members = deque([start]), []
            while queue:
                unit = queue.popleft()
                members.append(unit)
                for neighbor in neighbors_of(unit).tolist():
                    if neighbor not in seen and labels[neighbor] == district:
                        seen.add(neighbor)
                        queue.append(neighbor)
            found.append(sorted(members))
        return found

    gap = lambda labels: round(objective(labels)[0] / k, 2)
    where = lambda units: [round(float(lon[units].mean()), 5), round(float(lat[units].mean()), 5)]
    current = initial.copy()
    detached = sum(len(pieces(initial, district)) - 1 for district in range(k))
    repair = []
    for order, move in enumerate(audit["repair_moves"], 1):
        units, source, target = sorted(move["units"]), move["source_district"], move["target_district"]
        options = pieces(current, source)
        anchor = max(options, key=lambda members: (int(population[members].sum()), len(members), -members[0]))
        if units not in options or units == anchor or int(population[units].sum()) != move["population"]:
            raise SystemExit(f"Repair move {order} is not a detached piece of district {source}.")
        if not any(current[neighbor] == target for unit in units for neighbor in neighbors_of(unit).tolist()):
            raise SystemExit(f"Repair move {order} joins district {target}, which it does not touch.")
        current[units] = target
        repair.append({"order": order, "units": units, "source": source, "target": target, "population": move["population"],
                       "landM2": int(land[units].sum()), "county": geoids[units[0]][2:5], "point": where(units), "maxDeviation": gap(current)})
    if detached != len(repair) or not np.array_equal(current, repaired):
        raise SystemExit("Replaying the repair moves does not reproduce the saved after-repair plan.")
    if any(len(pieces(current, district)) != 1 for district in range(k)):
        raise SystemExit("A district is still in pieces after repair.")

    rebalance = []
    for order, move in enumerate(audit["rebalance_moves"], 1):
        (unit,), source, target = move["units"], move["source_district"], move["target_district"]
        before = objective(current)
        if current[unit] != source or population[unit] != move["population"] or population[unit] == 0:
            raise SystemExit(f"Balancing move {order} does not match the saved plan.")
        if target not in {int(current[neighbor]) for neighbor in neighbors_of(unit).tolist()}:
            raise SystemExit(f"Balancing move {order} joins a district it does not touch.")
        current[unit] = target
        if not objective(current) < before or len(pieces(current, source)) != 1:
            raise SystemExit(f"Balancing move {order} does not improve balance while keeping its donor connected.")
        rebalance.append({"order": order, "unit": unit, "source": source, "target": target, "population": move["population"],
                          "county": geoids[unit][2:5], "point": where([unit]), "maxDeviation": gap(current)})
    if not np.array_equal(current, final):
        raise SystemExit("Replaying the balancing moves does not reproduce the saved final plan.")
    if any(len(pieces(final, district)) != 1 for district in range(k)):
        raise SystemExit("A final district is not connected in the block graph.")

    def window(name: str, units: list[int], minimum: float) -> dict:
        bounds = np.array([geometry(unit).bounds for unit in units])
        w, s, e, n = bounds[:, 0].min(), bounds[:, 1].min(), bounds[:, 2].max(), bounds[:, 3].max()
        half_w, half_h = max(e - w, minimum) * 0.9, max(n - s, minimum * 0.45) * 0.9
        # About the stage's shape at Michigan's latitude, so the camera stays inside the clip box.
        if half_w < half_h * 2.2:
            half_w = half_h * 2.2
        else:
            half_h = half_w / 2.2
        cx, cy = (w + e) / 2, (s + n) / 2
        frame = box(cx - half_w, cy - half_h, cx + half_w, cy + half_h)
        margin = 0.02  # internal points preselect; the shapes decide
        near = np.flatnonzero((lon > cx - half_w - margin) & (lon < cx + half_w + margin) & (lat > cy - half_h - margin) & (lat < cy + half_h + margin))
        blocks, members = [], set()
        for index in near.tolist():
            geom = geometry(index)
            if not geom.intersects(frame):
                continue
            members.add(index)
            clipped = shapely.simplify(geom.intersection(frame), half_w / 2000, preserve_topology=True)  # about a pixel
            blocks.append({**block_record(index), "geometry": rounded(clipped),
                           "labels": [int(initial[index]), int(repaired[index]), int(final[index])]})
        if not set(units) <= members:
            raise SystemExit(f"The {name} window misses its own blocks.")
        edges = sorted({(min(a, b), max(a, b)) for a in members for b in neighbors_of(a).tolist() if b in members})
        return {"bbox": [round(float(v), 6) for v in (cx - half_w, cy - half_h, cx + half_w, cy + half_h)], "focus": units,
                "blocks": blocks, "edges": [list(edge) for edge in edges]}

    widest = max(repair, key=lambda move: len(move["units"]))

    def nearest_own_block(units: list[int], district: int) -> dict:
        """The shortest line from a cut-off piece to the rest of its district."""
        piece = shapely.union_all([geometry(unit) for unit in units])
        bounds = piece.bounds
        near = np.flatnonzero((initial == district) & (lon > bounds[0] - 0.05) & (lon < bounds[2] + 0.05)
                              & (lat > bounds[1] - 0.05) & (lat < bounds[3] + 0.05))
        own = min((index for index in near.tolist() if index not in set(units)), key=lambda index: geometry(index).distance(piece))
        a, b = shapely.ops.nearest_points(piece, geometry(own))
        k = math.cos(math.radians(a.y))
        return {"from": [round(a.x, 6), round(a.y, 6)], "to": [round(b.x, 6), round(b.y, 6)],
                "distanceM": round(math.hypot((b.x - a.x) * k, b.y - a.y) * 111_195),
                "block": geoids[own], "touches": sorted({int(initial[n]) for unit in units for n in neighbors_of(unit).tolist()} - {district})}
    heaviest = max(repair, key=lambda move: move["population"])
    windows = {
        # Wide enough to show the whole island the widest piece belongs to.
        "widestPiece": {**window("widest piece", widest["units"], 0.05), "move": widest["order"],
                        "gap": nearest_own_block(widest["units"], widest["source"])},
        "heaviestPiece": {**window("heaviest piece", heaviest["units"], 0.008), "move": heaviest["order"]},
        "firstBalance": {**window("first balancing move", [rebalance[0]["unit"]], 0.008), "move": 1},
    }
    payload = {
        "target": total / k, "detachedPieces": detached, "stopReason": audit["stop_reason"],
        "populations": {"powerDiagram": populations(initial).tolist(), "repaired": populations(repaired).tolist(), "final": populations(final).tolist()},
        "maxDeviation": {"powerDiagram": gap(initial), "repaired": gap(repaired), "final": gap(final)},
        "piecesPerDistrict": [len(pieces(initial, district)) for district in range(k)],
        "repair": repair, "rebalance": rebalance, "windows": windows,
        "verified": "the ordered move audit replays the saved power-diagram plan into the saved after-repair and final plans exactly",
    }
    return payload, initial.astype("u1").tobytes(), final


def build_validation(cache: Path, archive_sha: str, final_populations: list[int], block_count: int) -> dict:
    """The pipeline validator's findings, checked against this build's own replay."""
    path = ROOT / "data" / "districting-explainer" / "michigan-validation.json"
    if not path.exists():
        raise SystemExit(f"Missing {path}; run scripts/record_michigan_validation.py first.")
    record = json.loads(path.read_text("utf-8"))
    result = record["result"]
    if record["report"]["sha256"] != sha256_file(cache / RUN / "benchmark.json"):
        raise SystemExit("The validation record is for a different saved report.")
    if (result["status"] != "validated_saved_plan" or result["source_archive_sha256"] != archive_sha
            or result["district_populations"] != final_populations or result["block_count"] != block_count
            or result["physical_polygon_components"] != [1] * DISTRICTS or result["policy_components"] != [1] * DISTRICTS):
        raise SystemExit("The validation record disagrees with this build's replay of the final plan.")
    return record


def polsby_popper(geometry) -> float:
    """4πA / P² in a plane local to the shape, so latitude stretches neither."""
    k = math.cos(math.radians(geometry.centroid.y))
    plane = shapely.transform(geometry, lambda xy: np.column_stack([xy[:, 0] * k, xy[:, 1]]) * 111_195.0)
    return 4 * math.pi * plane.area / plane.length ** 2


# Perimeter depends on boundary detail, so every map is measured on the same
# basis: clipped to one cartographic land outline and simplified to ~500 m.
COMPACTNESS_TOLERANCE = 0.005


def matched_polsby_popper(geometry, land) -> float:
    return round(polsby_popper(shapely.simplify(geometry.intersection(land), COMPACTNESS_TOLERANCE, preserve_topology=True)), 4)


def carto_districts(cache: Path) -> dict[str, list]:
    """The explorer's 119th-Congress cartographic districts, by state, checked against their source record."""
    sources = json.loads((cache / CARTO / "sources.json").read_text("utf-8"))
    carto = next(source for source in sources["sources"] if source["kind"] == "congressional")
    if sha256_file(cache / CARTO / carto["path"]) != carto["sha256"]:
        raise SystemExit("The cartographic district archive does not match its source record.")
    stem = carto["path"].removesuffix(".zip")
    with zipfile.ZipFile(cache / CARTO / carto["path"]) as zipped:
        reader = shapefile.Reader(**{ext: io.BytesIO(zipped.read(f"{stem}.{ext}")) for ext in ("shp", "shx", "dbf")})
        by_state: dict[str, list] = {}
        for record, item in zip(reader.records(), reader.iterShapes()):
            if record["CD119FP"].isdigit():
                by_state.setdefault(record["STATEFP"], []).append((int(record["CD119FP"]), shape(item.__geo_interface__)))
    return {fips: sorted(items) for fips, items in by_state.items()} | {"_source": carto}


# Recent partisan gerrymanders, both parties, compared with this method's plans at House 435.
EXTREMES = {"37": "North Carolina", "17": "Illinois", "48": "Texas", "24": "Maryland"}
# Approximate downtown coordinates (longitude, latitude), for city markers and for
# checking which cities a district takes in. The first city is each state's focus:
# the build counts districts within FOCUS_RADIUS_KM of it on both maps.
EXTREME_CITIES = {
    "37": {"Greensboro": (-79.7920, 36.0726), "Charlotte": (-80.8431, 35.2271), "Raleigh": (-78.6382, 35.7796), "Durham": (-78.8986, 35.9940),
           "Winston-Salem": (-80.2442, 36.0999), "Asheville": (-82.5515, 35.5951), "Wilmington": (-77.9447, 34.2257), "Fayetteville": (-78.8784, 35.0527),
           "Greenville": (-77.3664, 35.6127)},
    "17": {"Chicago": (-87.6298, 41.8781), "Springfield": (-89.6501, 39.7817), "Champaign": (-88.2434, 40.1164), "Peoria": (-89.5890, 40.6936),
           "Rockford": (-89.0940, 42.2711), "East St. Louis": (-90.1510, 38.6245), "Bloomington": (-88.9937, 40.4842), "Moline": (-90.5151, 41.5067),
           "Carbondale": (-89.2168, 37.7273)},
    "48": {"Austin": (-97.7431, 30.2672), "Houston": (-95.3698, 29.7604), "Dallas": (-96.7970, 32.7767), "San Antonio": (-98.4936, 29.4241),
           "Fort Worth": (-97.3308, 32.7555), "El Paso": (-106.4850, 31.7619), "Corpus Christi": (-97.3964, 27.8006), "Brownsville": (-97.4975, 25.9017),
           "Lubbock": (-101.8552, 33.5779)},
    "24": {"Baltimore": (-76.6122, 39.2904), "Annapolis": (-76.4922, 38.9784), "Frederick": (-77.4105, 39.4143), "Hagerstown": (-77.7200, 39.6418),
           "Salisbury": (-75.5994, 38.3607), "Rockville": (-77.1528, 39.0840)},
}
FOCUS_RADIUS_KM = 10


def circle_km(lon: float, lat: float, km: float):
    """A circle of radius km around a point, in degrees (an ellipse in longitude)."""
    disk = Point(lon, lat).buffer(km / 111.195, 64)
    return shapely.transform(disk, lambda xy: np.column_stack([lon + (xy[:, 0] - lon) / math.cos(math.radians(lat)), xy[:, 1]]))


def build_extremes(cache: Path, carto: dict) -> list[dict]:
    """Computed House-435 plans next to the serving (119th Congress) maps, measured the same way."""
    manifest = json.loads((BUNDLE / "manifest.json").read_text("utf-8"))
    anchor = next(item for item in manifest["anchors"] if item["houseSize"] == 435)
    plans = {manifest["plans"][pid]["stateFips"]: manifest["plans"][pid] for pid in anchor["planIds"]}
    states = []
    for fips, name in EXTREMES.items():
        enacted = carto[fips]
        k = plans[fips]["districtCount"]
        if len(enacted) != k:
            raise SystemExit(f"{name} has {len(enacted)} serving districts; the House-435 plan has {k}.")
        outlines = json.loads(gzip.decompress((cache / "state-block-benchmark/suite-through-1000/states" / fips / f"districts-{k}" / "maps" / "districts-full.geojson.gz").read_bytes()))
        computed = sorted((feature["properties"]["district_id"], shape(feature["geometry"])) for feature in outlines["features"])
        land = shapely.union_all([geometry for _, geometry in enacted])
        w, s, e, n = land.bounds
        tolerance = max(e - w, n - s) / 700

        def polygons(geometry):
            # Clipping can leave stray lines or points along shared edges.
            parts = [part for part in getattr(geometry, "geoms", [geometry]) if part.geom_type in ("Polygon", "MultiPolygon")]
            return shapely.union_all(parts)

        def display(items):
            clipped = [polygons(geometry.intersection(land)) for _, geometry in items]
            return [rounded(geometry, 4) for geometry in shapely.coverage_simplify(clipped, tolerance)]

        computed_pp = [matched_polsby_popper(geometry, land) for _, geometry in computed]
        enacted_pp = [matched_polsby_popper(geometry, land) for _, geometry in enacted]
        cities = EXTREME_CITIES[fips]
        focus_city, focus_point = next(iter(cities.items()))
        near = circle_km(*focus_point, FOCUS_RADIUS_KM)
        least = min(range(k), key=lambda index: enacted_pp[index])
        least_shape = enacted[least][1]
        taken_in = [city for city, point in cities.items() if least_shape.contains(Point(point))]
        anchor = least_shape.intersection(land).representative_point()
        callouts = {
            "focus": {"city": focus_city, "point": list(focus_point), "radiusKm": FOCUS_RADIUS_KM,
                      "enacted": sum(1 for _, geometry in enacted if geometry.intersects(near)),
                      "computed": sum(1 for _, geometry in computed if geometry.intersection(land).intersects(near))},
            "leastCompact": {"district": enacted[least][0], "index": least, "pp": enacted_pp[least], "cities": taken_in,
                             "labelPoint": [round(anchor.x, 4), round(anchor.y, 4)]},
            "cities": [{"name": city, "point": list(point)} for city, point in cities.items() if city == focus_city or city in taken_in],
        }
        states.append({
            "state": name, "stateFips": fips, "districts": k, "bbox": [round(v, 4) for v in (w, s, e, n)], "callouts": callouts,
            "computed": {"pp": computed_pp, "features": [{"district": d, "geometry": g} for (d, _), g in zip(computed, display(computed))]},
            "enacted": {"pp": enacted_pp, "features": [{"district": d, "geometry": g} for (d, _), g in zip(enacted, display(enacted))]},
        })
    return states


def build_enacted(cache: Path, geoids, population, lon, lat, final_labels: np.ndarray) -> dict:
    """Michigan's enacted 118th-Congress map next to the computed one.

    TIGER/Line CD118 boundaries are built from 2020 blocks, so every block's
    internal point falls in exactly one enacted district and enacted
    populations come from the same block counts as the computed plan.
    Compactness compares both maps on one basis: full-resolution shapes clipped
    to the same 1:500,000 cartographic land outline.
    """
    manifest = json.loads((cache / ENACTED / "manifest.json").read_text("utf-8"))
    archive = cache / ENACTED / manifest["file"]
    if sha256_file(archive) != manifest["sha256"]:
        raise SystemExit("The enacted-district archive does not match its manifest.")
    stem = manifest["file"].removesuffix(".zip")
    with zipfile.ZipFile(archive) as zipped:
        reader = shapefile.Reader(**{ext: io.BytesIO(zipped.read(f"{stem}.{ext}")) for ext in ("shp", "shx", "dbf")})
        enacted = sorted(((int(record["CD118FP"]), shape(item.__geo_interface__)) for record, item in zip(reader.records(), reader.iterShapes())))
    if [number for number, _ in enacted] != list(range(1, DISTRICTS + 1)):
        raise SystemExit("The enacted map does not have exactly 13 numbered districts.")

    labels = np.full(len(geoids), -1, dtype=np.int64)
    for index, (_, geometry) in enumerate(enacted):
        shapely.prepare(geometry)
        inside = shapely.contains_xy(geometry, lon, lat)
        if (labels[inside] != -1).any():
            raise SystemExit("A block falls in two enacted districts.")
        labels[inside] = index
    # The 2023 boundary moved slightly at the Detroit River border; a few empty
    # water-side blocks fall outside it. Any resident left unplaced stops the build.
    unplaced = labels == -1
    if population[unplaced].any():
        raise SystemExit(f"{int(population[unplaced].sum())} residents fall in no enacted district.")

    sources = json.loads((cache / CARTO / "sources.json").read_text("utf-8"))
    carto = next(source for source in sources["sources"] if source["kind"] == "congressional")
    if sha256_file(cache / CARTO / carto["path"]) != carto["sha256"]:
        raise SystemExit("The cartographic district archive does not match its source record.")
    with zipfile.ZipFile(cache / CARTO / carto["path"]) as zipped:
        stem = carto["path"].removesuffix(".zip")
        reader = shapefile.Reader(**{ext: io.BytesIO(zipped.read(f"{stem}.{ext}")) for ext in ("shp", "shx", "dbf")})
        land = shapely.union_all([shape(item.__geo_interface__) for record, item in zip(reader.records(), reader.iterShapes()) if record["STATEFP"] == STATE_FIPS])

    outlines = json.loads(gzip.decompress((cache / RUN / "maps" / "districts-full.geojson.gz").read_bytes()))
    computed = sorted((feature["properties"]["district_id"], shape(feature["geometry"])) for feature in outlines["features"])
    compactness = {
        "computed": [matched_polsby_popper(geometry, land) for _, geometry in computed],
        "enacted": [matched_polsby_popper(geometry, land) for _, geometry in enacted],
    }

    def summary(assigned: np.ndarray) -> dict:
        placed = assigned >= 0
        counts = np.bincount(assigned[placed], weights=population[placed], minlength=DISTRICTS).astype(np.int64)
        deviations = DISTRICTS * counts - int(population.sum())
        counties: dict[str, set[int]] = {}
        for index in np.flatnonzero(population > 0).tolist():
            counties.setdefault(geoids[index][2:5], set()).add(int(assigned[index]))
        return {"populations": counts.tolist(), "maxDeviation": round(int(np.abs(deviations).max()) / DISTRICTS, 2),
                "spread": int(counts.max() - counts.min()), "countiesSplit": sum(len(found) > 1 for found in counties.values()),
                "countyPieces": sum(len(found) for found in counties.values()), "counties": len(counties)}

    # Display shapes stay whole over water; the page clips them to the explorer's land outline.
    simplified = shapely.coverage_simplify([geometry for _, geometry in enacted], 0.002)
    features = [{"type": "Feature", "properties": {"district": number, "labelPoint": [round(c, 5) for c in geometry.intersection(land).representative_point().coords[0]]},
                 "geometry": rounded(display, 5)} for (number, geometry), display in zip(enacted, simplified)]
    return {
        "source": {key: manifest[key] for key in ("url", "sha256", "bytes", "lastModified")},
        "landOutline": {"url": carto["url"], "sha256": carto["sha256"], "scale": carto["scale"]},
        "computed": summary(final_labels), "enacted": summary(labels), "compactness": compactness,
        "unplacedEmptyBlocks": int(unplaced.sum()),
        "features": features,
        "method": "Enacted districts assign each 2020 block by its internal point; Polsby-Popper uses shapes clipped to the 1:500,000 cartographic land outline and simplified to about 500 m, measured in a plane local to each district.",
    }


def build_special_cases(cache: Path) -> tuple[dict, dict]:
    """Hawaii, the Kentucky Bend, New York County and Alaska with their recorded links."""
    manifest = json.loads((BUNDLE / "manifest.json").read_text("utf-8"))
    outlines = {feature["properties"]["state_fips"]: feature for feature in bundle_asset(manifest["stateOutlines"]["url"], cache)["features"]}
    def plan(fips: str, house: int) -> dict:
        anchor = next(item for item in manifest["anchors"] if item["houseSize"] == house)
        return next(manifest["plans"][pid] for pid in anchor["planIds"] if manifest["plans"][pid]["stateFips"] == fips)
    cases, sources = {}, {}
    for name, spec in SPECIAL_CASES.items():
        fips = spec["fips"]
        at435 = plan(fips, 435)
        links = recorded_links(bundle_asset(at435["assets"]["connections"]["url"], cache))
        if len(links) != at435["recordedLinkCount"]:
            raise SystemExit(f"{at435['stateName']} has {len(links)} recorded links; its plan records {at435['recordedLinkCount']}.")
        case = {
            "state": at435["stateName"], "stateFips": fips, "coordinateFrame": at435["coordinateFrame"],
            "districtsAt435": at435["districtCount"], "districtsAt1000": plan(fips, 1000)["districtCount"],
            "links": links, "longestLinkM": max(link["distanceM"] for link in links),
        }
        if "window" not in spec:
            outline = outlines[fips]
            case["outline"] = {"type": "Feature", "properties": {}, "geometry": outline["geometry"]}
        else:
            window, tolerance = spec["window"], spec["tolerance"]
            w, s, e, n = window
            display = box(w - (e - w) * 0.25, s - (n - s) * 0.25, e + (e - w) * 0.25, n + (n - s) * 0.25)
            reader, sources[fips] = open_blocks(cache, fips)
            endpoints = {geoid for link in links for geoid in link["endpoints"]}
            members = [(index, geom) for index, geom in blocks_in(reader, window)]
            # An endpoint is the cut-off side (exclave or island) when its piece of
            # this state lies entirely inside the window instead of running off it.
            pieces = list(getattr(shapely.union_all([geom for _, geom in members]), "geoms", []))
            inner = box(*window).buffer(-1e-6)
            blocks = []
            for index, geom in members:
                row = reader.record(index)
                geoid = str(row["GEOID20"])
                piece = next(p for p in pieces if p.covers(geom.representative_point()))
                block = {"geoid": geoid, "population": int(row["POP20"]), "landM2": int(row["ALAND20"]),
                         "endpoint": geoid in endpoints, "cutOff": bool(piece.within(inner)),
                         "geometry": rounded(shapely.simplify(geom.intersection(display), tolerance, preserve_topology=True))}
                if block["endpoint"]:
                    anchor = (piece if block["cutOff"] else geom).representative_point()
                    block["labelPoint"] = [round(anchor.x, 6), round(anchor.y, 6)]
                blocks.append(block)
            if not endpoints <= {block["geoid"] for block in blocks}:
                raise SystemExit(f"The {at435['stateName']} window does not contain every link endpoint.")
            neighbors = []
            for neighbor_fips, label in spec["neighbors"].items():
                neighbor_reader, sources[neighbor_fips] = open_blocks(cache, neighbor_fips)
                union = shapely.union_all([geom for _, geom in blocks_in(neighbor_reader, window)]).intersection(display)
                anchor = union.intersection(box(*window)).representative_point()
                neighbors.append({"state": label, "stateFips": neighbor_fips, "labelPoint": [round(anchor.x, 6), round(anchor.y, 6)],
                                  "geometry": rounded(shapely.simplify(union, tolerance, preserve_topology=True))})
            case.update({"window": list(window), "blocks": blocks, "neighbors": neighbors})
        if "context" in spec:
            w, s, e, n = spec["contextBounds"]
            frame = box(w - 1.5, s - 1.5, e + 1.5, n + 1.5)
            context = []
            for fips, label in spec["context"].items():
                shape_ = shape(outlines[fips]["geometry"]).intersection(frame)
                anchor = shape_.intersection(box(w, s, e, n)).representative_point()
                context.append({"state": label, "stateFips": fips, "labelPoint": [round(anchor.x, 4), round(anchor.y, 4)],
                                "geometry": rounded(shapely.simplify(shape_, 0.003, preserve_topology=True), 4)})
            case.update({"context": context, "contextBounds": list(spec["contextBounds"])})
        cases[name] = case
    anchor = next(item for item in manifest["anchors"] if item["houseSize"] == 435)
    linked = [manifest["plans"][pid] for pid in anchor["planIds"] if manifest["plans"][pid]["recordedLinkCount"] > 0]
    cases["summary"] = {"statesWithLinks": len(linked), "states": len(anchor["planIds"]),
                         "links": sum(plan["recordedLinkCount"] for plan in linked),
                         "linkedStates": sorted(plan["stateName"] for plan in linked)}
    return cases, sources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache-root", type=Path, required=True)
    cache = parser.parse_args().cache_root.resolve()

    # --- Provenance: the archive and GEOID order must be the saved run's. ----
    archive = cache / SOURCE / f"{STEM}.zip"
    source_manifest = json.loads((cache / SOURCE / f"{STEM}.manifest.json").read_text("utf-8"))
    run = json.loads((cache / RUN / "initial-solver-result.json").read_text("utf-8"))["provenance"]
    archive_sha = sha256_file(archive)
    if not archive_sha == source_manifest["archive_sha256"] == run["source_sha256"]:
        raise SystemExit("Block source archive does not match the saved Michigan K13 run.")

    with zipfile.ZipFile(archive) as zipped:
        parts = {ext: io.BytesIO(zipped.read(f"{STEM}.{ext}")) for ext in ("shp", "shx", "dbf")}
    reader = shapefile.Reader(shp=parts["shp"], shx=parts["shx"], dbf=parts["dbf"])
    fields = [field[0] for field in reader.fields[1:]]
    records = reader.records()
    column = {name: fields.index(name) for name in fields}
    geoids = [str(row[column["GEOID20"]]) for row in records]
    population = np.array([int(row[column["POP20"]]) for row in records], dtype=np.int64)
    land = np.array([int(row[column["ALAND20"]]) for row in records], dtype=np.int64)
    water = np.array([int(row[column["AWATER20"]]) for row in records], dtype=np.int64)
    housing = [int(row[column["HOUSING20"]]) for row in records] if "HOUSING20" in column else None
    urban = [str(row[column["UR20"]]) for row in records] if "UR20" in column else None
    lon = np.array([float(row[column["INTPTLON20"]]) for row in records])
    lat = np.array([float(row[column["INTPTLAT20"]]) for row in records])
    order_sha = hashlib.sha256(json_bytes(geoids)).hexdigest()
    if order_sha != run["ordered_geoids_sha256"]:
        raise SystemExit("Source GEOID order differs from the saved run.")

    graph_file = next((cache / GRAPH).glob("shared-edge-*.npz"))
    with np.load(graph_file, allow_pickle=False) as graph_archive:
        offsets, neighbors = graph_archive["offsets"], graph_archive["neighbors"]
        graph_manifest = json.loads(graph_archive["manifest"].tobytes().decode("utf-8"))
    identity, graph_meta = graph_manifest["identity"], graph_manifest["graph_metadata"]
    if (identity["ordered_geoids_sha256"] != order_sha or identity["source_archive_sha256"] != archive_sha
            or graph_meta["node_count"] != len(geoids) or len(offsets) != len(geoids) + 1):
        raise SystemExit("Cached shared-edge graph does not belong to this source and order.")

    def neighbors_of(index: int) -> np.ndarray:
        return neighbors[offsets[index]:offsets[index + 1]]

    # --- One pass over shapes: window membership and multipart blocks. ----
    window_members = {name: [] for name in WINDOWS}
    window_boxes = {name: box(*spec["bbox"]) for name, spec in WINDOWS.items()}
    multipart = []
    for index, shape_record in enumerate(reader.iterShapes()):
        west, south, east, north = shape_record.bbox
        for name, spec in WINDOWS.items():
            w, s, e, n = spec["bbox"]
            if west <= e and east >= w and south <= n and north >= s:
                window_members[name].append(index)
        if shape_record.__geo_interface__["type"] == "MultiPolygon":
            multipart.append(index)
    if len(multipart) != graph_meta["multipart_block_count"]:
        raise SystemExit(f"Found {len(multipart)} multipart blocks; the graph recorded {graph_meta['multipart_block_count']}.")

    def geometry(index: int):
        return shape(reader.shape(index).__geo_interface__)

    def block_record(index: int) -> dict:
        record = {"i": index, "geoid": geoids[index], "population": int(population[index]),
                  "landM2": int(land[index]), "waterM2": int(water[index]), "point": [round(lon[index], 6), round(lat[index], 6)]}
        if housing is not None:
            record["housingUnits"] = housing[index]
        if urban is not None:
            record["urban"] = urban[index]
        return record

    windows = {}
    for name, spec in WINDOWS.items():
        members = []
        for index in window_members[name]:
            geom = geometry(index)
            if geom.intersects(window_boxes[name]):
                members.append((index, geom))
        index_set = {index for index, _ in members}
        w, s, e, n = spec["bbox"]
        pad_w, pad_h = (e - w) * 0.5, (n - s) * 0.5
        display_box = box(w - pad_w, s - pad_h, e + pad_w, n + pad_h)
        blocks = []
        for index, geom in members:
            clipped = shapely.simplify(geom.intersection(display_box), spec["tolerance"], preserve_topology=True)
            blocks.append({**block_record(index), "geometry": rounded(clipped)})
        edges = sorted({(min(a, int(b)), max(a, int(b))) for a, _ in members for b in neighbors_of(a) if int(b) in index_set})
        windows[name] = {"bbox": list(spec["bbox"]), "blocks": blocks, "edges": [list(edge) for edge in edges],
                         "clippedTo": [round(v, 6) for v in display_box.bounds]}
        windows[name]["_geoms"] = dict(members)

    # --- Detroit: a typical populated block and a corner-only contact near it. ----
    detroit = windows["detroit"]
    dw, ds, de, dn = WINDOWS["detroit"]["bbox"]
    center = ((dw + de) / 2, (ds + dn) / 2)
    candidates = [b for b in detroit["blocks"] if 50 <= b["population"] <= 400 and 0 < b["landM2"] <= 60_000]
    featured = min(candidates, key=lambda b: (math.hypot(b["point"][0] - center[0], b["point"][1] - center[1]), b["geoid"]))
    geoms = detroit["_geoms"]
    tree_indices = list(geoms)
    tree = shapely.STRtree([geoms[i] for i in tree_indices])
    near = sorted(tree_indices, key=lambda i: math.hypot(lon[i] - featured["point"][0], lat[i] - featured["point"][1]))[:400]
    corner = None
    for a in near:
        for position in tree.query(geoms[a]):
            b = tree_indices[int(position)]
            if b <= a:
                continue
            relation = shapely.relate(geoms[a], geoms[b])
            if relation[0] == "F" and relation[4] == "0":
                point = geoms[a].boundary.intersection(geoms[b].boundary)
                at = point.representative_point()
                around = [i for i in near if geoms[i].distance(at) < 1e-9]
                if len(around) == 4:
                    corner = {"point": [round(at.x, 7), round(at.y, 7)], "cornerPair": [geoids[a], geoids[b]],
                              "blocks": [geoids[i] for i in around]}
                    break
        if corner:
            break
    if corner is None:
        raise SystemExit("No four-block corner found near the featured Detroit block.")
    detroit["featured"] = featured["geoid"]
    detroit["corner"] = corner

    # --- Upper Peninsula: the largest populated block by land area. ----
    up_index = max((i for i in range(len(geoids)) if geoids[i][2:5] in UPPER_PENINSULA_COUNTIES and population[i] > 0),
                   key=lambda i: (land[i], geoids[i]))
    up_geom = geometry(up_index)
    upper = {**block_record(up_index), "geometry": rounded(shapely.simplify(up_geom, 0.0003, preserve_topology=True)),
             "neighbors": []}
    for neighbor in neighbors_of(up_index):
        n = int(neighbor)
        upper["neighbors"].append({**block_record(n), "geometry": rounded(shapely.simplify(geometry(n), 0.0003, preserve_topology=True))})

    # --- Straits: the fewest blocks from Upper Peninsula land to Lower Peninsula land. ----
    straits = windows["straits"]
    members = {b["i"] for b in straits["blocks"]}
    land_blocks = {b["i"] for b in straits["blocks"] if b["landM2"] > 0}
    upper_land = sorted(i for i in land_blocks if geoids[i][2:5] in UPPER_PENINSULA_COUNTIES)
    lower_land = {i for i in land_blocks if geoids[i][2:5] not in UPPER_PENINSULA_COUNTIES}
    depth = {i: 0 for i in upper_land}
    queue = deque(upper_land)
    while queue:
        node = queue.popleft()
        if node in lower_land:  # the far shore ends a chain
            continue
        for neighbor in neighbors_of(node).tolist():
            if neighbor in members and neighbor not in depth:
                depth[neighbor] = depth[node] + 1
                queue.append(neighbor)
    shores = [i for i in lower_land if i in depth]
    if not shores:
        raise SystemExit("The peninsulas are not connected inside the Straits window.")
    hops = min(depth[i] for i in shores)

    def chains(node: int):
        """Every fewest-block chain from the Upper Peninsula ending at this block."""
        if depth[node] == 0:
            yield [node]
            return
        for neighbor in sorted(neighbors_of(node).tolist()):
            if depth.get(neighbor) == depth[node] - 1 and neighbor not in lower_land:
                for chain in chains(neighbor):
                    yield chain + [node]

    by_index = {b["i"]: b for b in straits["blocks"]}
    view = box(*WINDOWS["straits"]["bbox"])
    k_lon = math.cos(math.radians(45.8))

    def length(points) -> float:
        return sum(math.hypot((b[0] - a[0]) * k_lon, b[1] - a[1]) for a, b in zip(points, points[1:]))

    def route(chain: list[int]) -> list[list[float]]:
        """The shortest line through the chain, crossing each shared boundary once.

        Large water blocks share long boundaries whose midpoints can lie far
        outside the view, so one crossing point per boundary is chosen by
        dynamic programming over points sampled along it (inside the window).
        """
        options = []
        for a, b in zip(chain, chain[1:]):
            shared = straits["_geoms"][a].boundary.intersection(straits["_geoms"][b].boundary)
            lines = [part for part in getattr(shared, "geoms", [shared]) if part.geom_type == "LineString"]
            if not lines:
                raise SystemExit(f"Chain blocks {geoids[a]} and {geoids[b]} share no boundary line.")
            samples = [line.interpolate(t / 60, normalized=True) for line in lines for t in range(61)]
            inside = [p for p in samples if view.contains(p)] or samples
            options.append([(p.x, p.y) for p in inside])
        start, goal = tuple(by_index[chain[0]]["point"]), tuple(by_index[chain[-1]]["point"])
        best = {point: (length([start, point]), [point]) for point in options[0]}
        for layer in options[1:]:
            best = {point: min((cost + length([prev, point]), via + [point]) for prev, (cost, via) in best.items()) for point in layer}
        _, via = min((cost + length([point, goal]), via) for point, (cost, via) in best.items())
        return [list(start), *([round(x, 6), round(y, 6)] for x, y in via), list(goal)]

    candidates = [chain for shore in sorted(shores) if depth[shore] == hops for chain in chains(shore)]
    # Prefer chains whose shore blocks read as peninsula land at the slide's zoom:
    # big enough to see (the closest Upper Peninsula one is about 80 m across),
    # mostly land (one candidate is a bay with a sliver of shore), not a thin
    # shoreline strip, and part of the mainland rather than an island. Then the
    # shortest line.
    def land_group(index: int) -> int:
        seen, queue = {index}, deque([index])
        while queue:
            for neighbor in neighbors_of(queue.popleft()).tolist():
                if neighbor in land_blocks and neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        return len(seen)

    def reads_as_land(index: int) -> bool:
        block = by_index[index]
        return (block["landM2"] >= MIN_SHORE_LAND_M2 and block["landM2"] >= block["waterM2"]
                and polsby_popper(straits["_geoms"][index]) >= MIN_SHORE_COMPACTNESS
                and land_group(index) >= MIN_MAINLAND_BLOCKS)
    visible = [chain for chain in candidates if reads_as_land(chain[0]) and reads_as_land(chain[-1])]
    path = min(visible or candidates, key=lambda chain: (length(route(chain)), chain))
    straits["path"] = [geoids[node] for node in path]
    straits["route"] = route(path)
    straits["doorways"] = straits["route"][1:-1]
    straits["chainCount"] = len(candidates)
    straits["waterTouchingBothShores"] = sum(
        1 for b in straits["blocks"] if b["landM2"] == 0
        and any(n in upper_land for n in neighbors_of(b["i"]).tolist())
        and any(n in lower_land for n in neighbors_of(b["i"]).tolist()))

    # --- Multipart blocks: the one whose second-largest piece is biggest, so every piece shows. ----
    def part_count(index):
        geom = geometry(index)
        return len(geom.geoms) if geom.geom_type == "MultiPolygon" else 1
    def second_piece(index):
        geom = geometry(index)
        return sorted((part.area for part in geom.geoms), reverse=True)[1]
    multipart_index = max(multipart, key=lambda i: (second_piece(i), geoids[i]))
    multipart_geom = geometry(multipart_index)
    multipart_block = {**block_record(multipart_index), "parts": part_count(multipart_index),
                       "geometry": rounded(shapely.simplify(multipart_geom, 0.00005, preserve_topology=True)), "neighbors": []}
    mw, ms, me, mn = multipart_geom.bounds
    context = box(mw - (me - mw), ms - (mn - ms), me + (me - mw), mn + (mn - ms))
    for neighbor in neighbors_of(multipart_index):
        n = int(neighbor)
        clipped = shapely.simplify(geometry(n).intersection(context), 0.00005, preserve_topology=True)
        if not clipped.is_empty:
            multipart_block["neighbors"].append({**block_record(n), "geometry": rounded(clipped)})

    for window in windows.values():
        window.pop("_geoms")

    # --- Every block as a point: the algorithm's input, in graph order. ----
    pad = 0.01
    bbox = [float(lon.min() - pad), float(lat.min() - pad), float(lon.max() + pad), float(lat.max() + pad)]
    quantize = lambda values, low, high: np.round((values - low) / (high - low) * 65535).astype("<u2")
    if population.max() > 65535:
        raise SystemExit("A block population does not fit the uint16 point format.")
    water_only = (land == 0) & (water > 0)
    points = b"".join([
        quantize(lon, bbox[0], bbox[2]).tobytes(), quantize(lat, bbox[1], bbox[3]).tobytes(),
        population.astype("<u2").tobytes(), water_only.astype("u1").tobytes(),
    ])

    total = int(population.sum())
    stats = {
        "state": "Michigan", "stateFips": STATE_FIPS, "sourceYear": 2020, "districts": DISTRICTS,
        "blocks": len(geoids), "residents": total, "targetPerDistrict": total / DISTRICTS,
        "populatedBlocks": int((population > 0).sum()), "zeroPopulationBlocks": int((population == 0).sum()),
        "waterOnlyBlocks": int(water_only.sum()), "tracts": len({g[:11] for g in geoids}),
        "largestBlockPopulation": int(population.max()), "multipartBlocks": len(multipart),
        "graph": {key: graph_meta[key] for key in (
            "edge_count", "component_count", "isolated_node_count", "candidate_pair_count",
            "excluded_corner_pair_count", "interior_overlap_pair_count", "source_coordinate_count",
            "de9im_pattern", "definition")},
        "featured": {
            "detroit": featured,
            "upperPeninsula": {key: value for key, value in upper.items() if key not in ("geometry", "neighbors")},
            "multipart": {key: value for key, value in multipart_block.items() if key not in ("geometry", "neighbors")},
        },
    }

    special_cases, special_sources = build_special_cases(cache)
    power = build_power_diagram(cache, ROOT / "data" / "districting-explainer" / "michigan-k13-recording.json", lon, lat, population, archive_sha)
    repair, power_labels, final_labels = build_repair(cache, geoids, population, land, lon, lat, neighbors_of, block_record, geometry)
    checks = {"validation": build_validation(cache, archive_sha, repair["populations"]["final"], len(geoids)),
              "enacted": build_enacted(cache, geoids, population, lon, lat, final_labels),
              "extremes": build_extremes(cache, carto_districts(cache)), "compactnessToleranceDegrees": COMPACTNESS_TOLERANCE}
    bundle = json.loads((BUNDLE / "manifest.json").read_text("utf-8"))
    county_index = bundle_asset(bundle["stateExplorers"][STATE_FIPS]["plans"][f"{STATE_FIPS}-{DISTRICTS}"]["summary"]["url"], cache)
    stats["countyNames"] = {county["fips"]: county.get("displayName") or f"{county['name']} County" for county in county_index["counties"]}

    OUTPUT.mkdir(parents=True, exist_ok=True)
    files = [
        write(OUTPUT / "michigan-points.bin", points),
        write(OUTPUT / "michigan-windows.json", json_bytes({"windows": windows, "upperPeninsula": upper, "multipart": multipart_block})),
        write(OUTPUT / "michigan-stats.json", json_bytes(stats)),
        write(OUTPUT / "special-cases.json", json_bytes(special_cases)),
        write(OUTPUT / "michigan-power-diagram.json", json_bytes(power)),
        write(OUTPUT / "michigan-repair.json", json_bytes(repair)),
        write(OUTPUT / "michigan-labels-power.bin", power_labels),
        write(OUTPUT / "michigan-checks.json", json_bytes(checks)),
    ]
    manifest = {
        "schemaVersion": 1,
        "state": "Michigan", "stateFips": STATE_FIPS, "planDistricts": DISTRICTS,
        "points": {"count": len(geoids), "bbox": bbox, "layout": ["lon:u16", "lat:u16", "population:u16", "waterOnly:u8"],
                   "order": "source record order = shared-edge graph node order = saved run order"},
        "files": files,
        "provenance": {
            "sourceArchiveSha256": archive_sha, "sourceUrl": source_manifest["url"],
            "orderedGeoidsSha256": order_sha, "graphCacheFile": graph_file.name,
            "run": str(RUN).replace("\\", "/"), "settingsSha256": run["settings_sha256"],
            "displayGeometry": "window blocks clipped to a padded window and simplified for display only",
            "specialCaseSources": special_sources,
            "specialCaseLinks": "recorded links from each state's House-435 plan, read through the explorer bundle's hash allowlist",
        },
    }
    (OUTPUT / "manifest.json").write_bytes(json_bytes(manifest))
    print(json.dumps({"files": files, "featured": {k: v.get("geoid") for k, v in stats["featured"].items()},
                      "windows": {k: {"blocks": len(v["blocks"]), "edges": len(v["edges"])} for k, v in windows.items()},
                      "straitsPath": straits["path"], "corner": corner, "multipartParts": multipart_block["parts"],
                      "specialCases": {name: {"links": len(case["links"]), "longestKm": round(case["longestLinkM"] / 1000, 1),
                                               "blocks": len(case.get("blocks", [])), "neighbors": [n["state"] for n in case.get("neighbors", [])]}
                                        for name, case in special_cases.items() if name != "summary"},
                      "linkSummary": special_cases["summary"]}, indent=1))


if __name__ == "__main__":
    main()
