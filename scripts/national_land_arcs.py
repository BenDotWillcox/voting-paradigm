"""Shared coordinate-subsequence arcs for a read-only national display.

District edge ownership and graph junctions determine each maximal arc. Shared
arcs simplify once. Exterior arcs approaching another state's footprint remain
exact. Reconstructed rings contain only original coordinates, never snapped or
interpolated vertices; callers must validate the resulting polygon coverage.
"""
from __future__ import annotations

from collections import defaultdict
import math
import re

import numpy as np
from shapely import STRtree, coverage_invalid_edges, coverage_is_valid, intersects, is_valid_reason, linestrings, prepare, union_all
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon


def shared_arc_partition(geometries: list, neighboring_states: list, tolerance: float, border_band: float):
    if not math.isfinite(tolerance) or tolerance <= 0 or border_band < tolerance * 2:
        raise ValueError("Invalid shared-arc display tolerance or border guard")
    rings = []
    part_layout = []
    owners = defaultdict(set)
    neighbors = defaultdict(set)
    for district, geometry in enumerate(geometries):
        layout = []
        parts = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
        for part in parts:
            ring_ids = []
            for ring in (part.exterior, *part.interiors):
                coordinates = [tuple(p[:2]) for p in ring.coords]
                if coordinates[0] != coordinates[-1] or len(set(coordinates[:-1])) < 3:
                    raise ValueError("Source display has a degenerate ring")
                ring_ids.append(len(rings))
                rings.append(coordinates)
                for first, second in zip(coordinates, coordinates[1:]):
                    if first == second:
                        continue
                    edge = tuple(sorted((first, second)))
                    owners[edge].add(district)
                    neighbors[first].add(second)
                    neighbors[second].add(first)
            layout.append(ring_ids)
        part_layout.append(layout)
    if any(len(value) > 2 for value in owners.values()):
        raise ValueError("More than two districts own one source display edge")
    locked = set()
    if neighboring_states:
        guard = union_all([geometry.buffer(border_band, quad_segs=4) for geometry in neighboring_states])
        prepare(guard)
        exterior = [edge for edge, labels in owners.items() if len(labels) == 1]
        for start in range(0, len(exterior), 8192):
            batch = exterior[start:start + 8192]
            flags = intersects(guard, linestrings(np.asarray(batch)))
            locked.update(edge for edge, flag in zip(batch, flags) if flag)
    signatures = {edge: (tuple(sorted(labels)), edge in locked) for edge, labels in owners.items()}
    junctions = set()
    for point, adjacent in neighbors.items():
        if len(adjacent) != 2 or len({signatures[tuple(sorted((point, other)))] for other in adjacent}) != 1:
            junctions.add(point)
    # Every closed degree-two chain needs two fixed anchors, including tiny
    # islands and holes. Distinct anchors avoid simplifying a whole ring to one
    # repeated point; a still-degenerate candidate is rejected by the caller.
    unseen = set(neighbors)
    while unseen:
        start = min(unseen)
        stack, component = [start], set()
        while stack:
            point = stack.pop()
            if point in component:
                continue
            component.add(point)
            stack.extend(other for other in neighbors[point] if other not in component)
        unseen.difference_update(component)
        if not component.intersection(junctions):
            junctions.add(start)
            junctions.add(max(component, key=lambda point: ((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2, point)))
    visited = set()
    arcs = []
    kept = set(junctions)
    for start in sorted(junctions):
        for adjacent in sorted(neighbors[start]):
            edge = tuple(sorted((start, adjacent)))
            if edge in visited:
                continue
            path = [start, adjacent]
            visited.add(edge)
            while path[-1] not in junctions:
                following = next(other for other in neighbors[path[-1]] if other != path[-2])
                next_edge = tuple(sorted((path[-1], following)))
                if next_edge in visited:
                    raise ValueError("Shared-arc traversal revisited an edge")
                visited.add(next_edge)
                path.append(following)
            is_locked = edge in locked
            # Additional original anchors bound the scope of a local rollback.
            # A single narrow inlet need not restore a whole state's coastline.
            section_edges = 1 if is_locked else 32
            for offset in range(0, len(path) - 1, section_edges):
                section = path[offset:offset + section_edges + 1]
                simplified = section if is_locked else list(LineString(section).simplify(tolerance, preserve_topology=True).coords)
                if simplified[0] != section[0] or simplified[-1] != section[-1] or not set(simplified).issubset(section):
                    raise ValueError("Arc simplification moved endpoints or introduced coordinates")
                kept.update(simplified)
                arcs.append((section, simplified, is_locked))
    if visited != set(owners):
        raise ValueError("Shared-arc traversal omitted source edges")
    # Simplify the unique shared linework together, so GEOS checks adjacent
    # islands/holes and other arcs while selecting source-coordinate subsequences.
    # This avoids creating local crossings that an independent-arc DP cannot see.
    joint = MultiLineString([arc[0] for arc in arcs]).simplify(tolerance, preserve_topology=True)
    if joint.geom_type != "MultiLineString" or len(joint.geoms) != len(arcs):
        raise ValueError("Joint arc simplification changed line membership")
    kept = set(junctions)
    for index, (arc, simplified) in enumerate(zip(arcs, joint.geoms)):
        original, _, locked_arc = arc
        if locked_arc and list(simplified.coords) != original:
            raise ValueError("Joint simplification changed a locked two-point source edge")
        selected = original if locked_arc else list(simplified.coords)
        if selected[0] != original[0] or selected[-1] != original[-1] or not set(selected).issubset(original):
            raise ValueError("Joint simplification changed source arc identity")
        kept.update(selected)
        arcs[index] = original, selected, locked_arc
    def reconstruct():
        for ring in rings:
            selected = [point for point in ring[:-1] if point in kept]
            if len(set(selected)) < 3:
                kept.update(ring)
        simplified_rings = []
        for ring in rings:
            selected = [point for point in ring[:-1] if point in kept]
            simplified_rings.append([*selected, selected[0]])
        result, all_parts = [], []
        for layout in part_layout:
            parts = [Polygon(simplified_rings[ids[0]], [simplified_rings[i] for i in ids[1:]]) for ids in layout]
            all_parts.extend(parts)
            result.append(parts[0] if len(parts) == 1 else MultiPolygon(parts))
        return result, all_parts, simplified_rings
    restored = set()
    rollback_rounds = 0
    for iteration in range(24):
        result, all_parts, simplified_rings = reconstruct()
        valid = all(g.is_valid and not g.is_empty for g in result)
        if valid and coverage_is_valid(result):
            break
        trouble = []
        for geometry in [*all_parts, *result]:
            if geometry.is_valid:
                continue
            reason = is_valid_reason(geometry)
            match = re.search(r"\[([^ ]+) ([^\]]+)\]", reason)
            if not match:
                raise ValueError(f"Cannot localize national topology failure: {reason}")
            trouble.append(Point(float(match[1]), float(match[2])).buffer(1e-8))
        if valid:
            trouble.extend(edge.buffer(1e-8) for edge in coverage_invalid_edges(result) if not edge.is_empty)
        # Exact original vertices can have been retained by another incident
        # section; reconstruct the current lines before locating repairs.
        current_lines = [LineString([p for p in original if p in kept]) for original, _, _ in arcs]
        arc_tree = STRtree(current_lines)
        restore = {int(i) for location in trouble for i in arc_tree.query(location, predicate="intersects")
                   if int(i) not in restored and not arcs[int(i)][2]}
        if not restore:
            raise ValueError("National topology repair could not identify an unrestored source arc")
        for i in restore:
            kept.update(arcs[i][0])
        restored.update(restore)
        rollback_rounds = iteration + 1
    else:
        raise ValueError("National topology repair exceeded its bounded local rollback budget")
    # Every locked exterior source segment remains an actual consecutive ring
    # segment; merely retaining its endpoints would not establish this proof.
    output_edges = {tuple(sorted((a, b))) for ring in simplified_rings for a, b in zip(ring, ring[1:]) if a != b}
    if not locked.issubset(output_edges):
        raise ValueError("A protected interstate segment changed")
    return result, {"method": "Joint topology-preserving coordinate-subsequence shared arcs with exact protected interstate exterior edges",
        "arcCount": len(arcs), "lockedArcCount": sum(a[2] for a in arcs), "lockedExteriorEdgeCount": len(locked),
        "protectedExteriorEdgesUnchanged": True, "introducedCoordinates": 0,
        "sharedArcsSimplifiedOnce": True, "junctionCount": len(junctions),
        "locallyRestoredArcSections": len(restored), "localRollbackRounds": rollback_rounds,
        "maximumOriginalEdgesPerArcSection": 32, "lockedEdgesAreFixedJointObstacles": True}
