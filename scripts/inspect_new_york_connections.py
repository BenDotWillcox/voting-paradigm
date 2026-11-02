"""Independently classify New York's proposed harbor connections.

Exact 2020 New Jersey blocks identify jurisdictional coverage; complete Hudson
County AREAWATER polygons locate water inside that coverage. Source geometry
and policy code remain unchanged. This is a diagnostic, not a district solve.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sys
import zipfile

import shapefile
import shapely
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, box, mapping, shape
from shapely.ops import nearest_points, substring

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.hawaii_population_links import select_population_aware_forest

OUTPUT = ROOT / '.cache/state-block-benchmark/suite-through-1000/diagnostics/new-york'
NJ_ARCHIVE = ROOT / '.cache/state-block-benchmark/source/34/tl_2020_34_tabblock20.zip'
NY_ARCHIVE = ROOT / '.cache/state-block-benchmark/source/36/tl_2020_36_tabblock20.zip'
WATER_ARCHIVE = OUTPUT / 'context-source/tl_2020_34017_areawater.zip'
WATER_URL = 'https://www2.census.gov/geo/tiger/TIGER2020/AREAWATER/tl_2020_34017_areawater.zip'
WATER_SHA256 = '6b4b4f89aa45cca7f6eed0bbe540550a69043721f8c938dee8298696bc148d61'
ISLAND_GEOIDS = ('360610001001000', '360610001001001')


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@contextmanager
def archive_reader(path: Path):
    with zipfile.ZipFile(path) as zipped:
        stems = [name[:-4] for name in zipped.namelist() if name.endswith('.shp')]
        if len(stems) != 1:
            raise ValueError('Expected exactly one shapefile in source archive.')
        stem = stems[0]
        with shapefile.Reader(shp=zipped.open(stem + '.shp'), shx=zipped.open(stem + '.shx'),
                              dbf=zipped.open(stem + '.dbf')) as reader:
            yield reader


def affine_for_bounds(bounds):
    xmin, ymin, xmax, ymax = bounds
    ys = 6_371_000.0 * math.pi / 180
    xs = ys * math.cos(math.radians((ymin + ymax) / 2))
    return [xs, 0, 0, ys, -(xmin + xmax) / 2 * xs, -(ymin + ymax) / 2 * ys]


def intervals(line, intersections):
    pending, result = list(intersections), []
    while pending:
        geometry = pending.pop()
        if geometry.is_empty:
            continue
        if geometry.geom_type in ('MultiLineString', 'GeometryCollection'):
            pending.extend(geometry.geoms)
        elif geometry.geom_type == 'LineString':
            positions = [max(0.0, min(1.0, line.project(Point(xy), normalized=True))) for xy in geometry.coords]
            result.append((min(positions), max(positions)))
    merged = []
    for start, end in sorted(result):
        if merged and start <= merged[-1][1] + 1e-12:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def complement(merged):
    cursor, output = 0.0, []
    for start, end in merged:
        if start > cursor:
            output.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < 1:
        output.append((cursor, 1.0))
    return output


def feature(geometry, properties):
    return {'type': 'Feature', 'properties': properties, 'geometry': mapping(geometry)}


def run():
    names = ('geography-context.json', 'new-jersey-context.geojson', 'area-water-context.geojson',
             'connection-surface-segments.geojson', 'island-to-water-distance.geojson')
    if any((OUTPUT / name).exists() for name in names):
        raise FileExistsError('Refusing to overwrite a completed connection audit.')
    candidate_path = OUTPUT / 'candidate-links.json'
    candidates = json.loads(candidate_path.read_text(encoding='utf-8'))
    diagnosis_path = OUTPUT / 'diagnosis.json'
    diagnosis = json.loads(diagnosis_path.read_text(encoding='utf-8'))
    if candidates != diagnosis['links']:
        raise ValueError('Final candidate records must match the authoritative completed topology diagnosis.')
    archive_hashes = {str(path.relative_to(ROOT)).replace('\\', '/'): digest(path)
                      for path in (NJ_ARCHIVE, NY_ARCHIVE, WATER_ARCHIVE)}
    for archive in (NJ_ARCHIVE, NY_ARCHIVE):
        manifest = json.loads(archive.with_suffix('.manifest.json').read_text(encoding='utf-8'))
        if digest(archive) != manifest['archive_sha256']:
            raise ValueError('Census archive does not match its preserved manifest.')
    if digest(WATER_ARCHIVE) != WATER_SHA256:
        raise ValueError('Downloaded area-water archive differs from audited checksum.')
    lines = {link['id']: LineString([end['coordinate'] for end in link['endpoints']]) for link in candidates}
    overall = shapely.union_all(list(lines.values())).bounds
    clip = box(overall[0] - .007, overall[1] - .007, overall[2] + .007, overall[3] + .007)
    nj_blocks, nj_features = [], []
    with archive_reader(NJ_ARCHIVE) as reader:
        nj_count = reader.numRecords
        for item in reader.iterShapeRecords(bbox=clip.bounds):
            geometry = shape(item.shape.__geo_interface__)
            props = item.record.as_dict()
            if not geometry.is_valid or not str(props['GEOID20']).startswith('34'):
                raise ValueError('Invalid New Jersey source geometry or state GEOID.')
            nj_blocks.append((geometry, props))
            displayed = geometry.intersection(clip).simplify(.000005, preserve_topology=True)
            if not displayed.is_empty:
                nj_features.append(feature(displayed, {'geoid': props['GEOID20'], 'state': 'New Jersey',
                    'land_area_m2': int(props['ALAND20']), 'water_area_m2': int(props['AWATER20']),
                    'population': int(props['POP20']), 'source': '2020 Census TABBLOCK20'}))
    water_geometries, water_features, water_records = [], [], []
    with archive_reader(WATER_ARCHIVE) as reader:
        water_count = reader.numRecords
        for item in reader.iterShapeRecords():
            geometry = shape(item.shape.__geo_interface__)
            if not geometry.is_valid:
                raise ValueError('Invalid official area-water source geometry.')
            props = item.record.as_dict()
            water_geometries.append(geometry)
            water_records.append(props)
            displayed = geometry.intersection(clip).simplify(.000005, preserve_topology=True)
            if not displayed.is_empty:
                water_features.append(feature(displayed, {'name': props['FULLNAME'], 'hydroid': props['HYDROID'],
                    'mtfcc': props['MTFCC'], 'source': '2020 Census TIGER AREAWATER', 'county_fips': '34017'}))
    water_union = shapely.union_all(water_geometries)
    reports, segment_features = [], []
    for candidate in candidates:
        line = lines[candidate['id']]
        affine = affine_for_bounds(line.bounds)
        length = float(affine_transform(line, affine).length)
        crossed = []
        nj_intersections = []
        for geometry, props in nj_blocks:
            interior = line.intersection(geometry).difference(geometry.boundary)
            interior_length = float(affine_transform(interior, affine).length)
            if interior_length > 1e-6:
                nj_intersections.append(interior)
                crossed.append({'geoid': props['GEOID20'], 'population': int(props['POP20']),
                    'land_area_m2': int(props['ALAND20']), 'water_area_m2': int(props['AWATER20']),
                    'candidate_interior_length_m': interior_length})
        if any(not row['geoid'].startswith('34017') for row in crossed):
            raise ValueError('Candidate crosses New Jersey coverage outside audited Hudson County.')
        coverage = min(1.0, math.fsum(b-a for a,b in intervals(line,nj_intersections)))
        water_intervals = intervals(line, [geometry.intersection(line) for geometry in water_geometries])
        nonwater = complement(water_intervals)
        fraction = min(1.0, math.fsum(b-a for a,b in water_intervals))
        water_only = 1 - fraction <= 1e-9
        if 1 - coverage > 1e-9:
            raise ValueError(f'Candidate {candidate["id"]} has unaudited non-New-Jersey gap coverage: {coverage}.')
        report = {'candidate_id': candidate['id'], 'candidate_endpoints': [list(xy) for xy in line.coords],
            'selected_k': candidate.get('selected_k', []), 'component_ids': candidate['component_ids'],
            'distance_m': candidate['distance_m'], 'candidate_planar_length_m': length,
            'new_jersey_interior_coverage_fraction': coverage, 'new_jersey_interior_coverage_m': coverage * length,
            'crossed_new_jersey_blocks': sorted(crossed, key=lambda row: row['geoid']),
            'mapped_water_fraction': fraction, 'mapped_water_length_m': fraction * length,
            'outside_mapped_water_length_m': (1 - fraction) * length,
            'water_only_under_2020_census_area_water': water_only,
            'classification': 'mapped_water_only' if water_only else 'crosses_mapped_water_and_new_jersey_land',
            'water_intervals_normalized': water_intervals, 'outside_water_intervals_normalized': nonwater,
            'crossed_water_features': [{'name': props['FULLNAME'], 'hydroid': props['HYDROID'], 'mtfcc': props['MTFCC']}
                for geometry, props in zip(water_geometries, water_records, strict=True) if geometry.intersection(line).length > 0]}
        reports.append(report)
        for kind, values in (('mapped_water', water_intervals), ('outside_mapped_water', nonwater)):
            for start, end in values:
                if end - start <= 1e-12:
                    continue
                segment_features.append(feature(substring(line,start,end,normalized=True),
                    {'candidate_id': candidate['id'], 'id': candidate['id'], 'classification': kind,
                     'length_m': length*(end-start)}))
    island_reports, island_features = [], []
    with archive_reader(NY_ARCHIVE) as reader:
        for record in reader.iterRecords(fields=['GEOID20','POP20','ALAND20','AWATER20','HOUSING20']):
            if record['GEOID20'] not in ISLAND_GEOIDS:
                continue
            geometry = shape(reader.shape(record.oid).__geo_interface__)
            affine = affine_for_bounds(geometry.bounds)
            projected = affine_transform(geometry, affine)
            projected_water = affine_transform(water_union, affine)
            a,b = nearest_points(projected, projected_water)
            gap = float(a.distance(b))
            inverse = [1/affine[0],0,0,1/affine[3],-affine[4]/affine[0],-affine[5]/affine[3]]
            near_line = affine_transform(LineString([a,b]), inverse)
            nj_land = shapely.union_all([g for g,p in nj_blocks]).difference(water_union)
            land_adjacency = float(affine_transform(geometry.boundary.intersection(nj_land),affine).length)
            boundary_length = float(projected.boundary.length)
            island_reports.append({'geoid':record['GEOID20'],'population':int(record['POP20']),
                'housing_units':int(record['HOUSING20']), 'land_area_m2':int(record['ALAND20']),
                'water_area_m2':int(record['AWATER20']), 'minimum_distance_to_hudson_county_mapped_water_m': gap,
                'water_intersects_island': bool(geometry.intersects(water_union)),
                'source_boundary_length_m': boundary_length, 'boundary_touching_new_jersey_nonwater_m':land_adjacency,
                'entire_boundary_touches_new_jersey_nonwater': abs(land_adjacency-boundary_length) <= 1e-6,
                'nearest_water_endpoint_coordinates':[list(xy) for xy in near_line.coords],
                'interpretation': 'Positive separation means any connection from this source block to mapped harbor water must first cross a nonwater gap.' if gap > .01 else 'The source block boundary reaches mapped harbor water.'})
            if gap > .01:
                island_features.append(feature(near_line, {'geoid': record['GEOID20'],
                    'classification':'nearest_mapped_water_gap', 'distance_m':gap}))
    if {row['geoid'] for row in island_reports} != set(ISLAND_GEOIDS):
        raise ValueError('Both isolated source islands must be inspected.')
    for name, expected in archive_hashes.items():
        if digest(ROOT / name) != expected:
            raise ValueError('Source archive changed during inspection.')
    # Apply the exact existing selector twice: once to the geometric candidates
    # and once to candidates independently corroborated as water-only. The
    # population arithmetic must not obscure the foreign-land distinction.
    component_populations = [component['population'] for component in diagnosis['components']]
    water_ids = {row['candidate_id'] for row in reports if row['water_only_under_2020_census_area_water']}
    water_candidates = [candidate for candidate in candidates if candidate['id'] in water_ids]
    assessments = []
    for count in (26,35,42,61):
        geometric = select_population_aware_forest(component_populations,candidates,count)
        try:
            water_selection = select_population_aware_forest(component_populations,water_candidates,count)
        except ValueError as error:
            water_selection = {'status':'no_connecting_water_only_forest','reason':str(error)}
        else:
            water_selection['status'] = 'selected'
        assessments.append({'district_count':count,'recorded_geometric_selection':geometric,
                            'water_only_selection':water_selection})
    selected_endpoint_geoid = '360610005000003'
    with archive_reader(NY_ARCHIVE) as reader:
        found = [record for record in reader.iterRecords(fields=['GEOID20','POP20','ALAND20','AWATER20'])
                 if record['GEOID20'] == selected_endpoint_geoid]
        if len(found) != 1:
            raise ValueError('Expected one main-component anchor block.')
        anchor_record = found[0]
        anchor_geometry = shape(reader.shape(anchor_record.oid).__geo_interface__)
        if anchor_geometry.geom_type != 'Polygon' or int(anchor_record['POP20']) != 0:
            raise ValueError('The conditional extension witness expects the verified single-part zero-population anchor.')
    if diagnosis['blocks_spanning_components'] or any(row['population'] != 0 for row in island_reports):
        raise ValueError('The conditional zero-population extension witness does not apply to this source.')
    if any({candidate['endpoints'][0]['geoid'] for candidate in candidates
            if candidate['id'] in assessment['recorded_geometric_selection']['selected_link_ids']} != {selected_endpoint_geoid}
           for assessment in assessments):
        raise ValueError('The two selected island branches must share the verified main-component anchor.')
    report = {'status':'complete','source_year':2020,'analysis':'new_york_harbor_candidate_water_and_land_classification',
        'links':reports,'isolated_island_water_access':sorted(island_reports,key=lambda row:row['geoid']),
        'new_jersey_source_feature_count':nj_count,'hudson_county_area_water_feature_count':water_count,
        'source_archive_sha256':archive_hashes,'source_archives_byte_identical_before_after':True,
        'source_geometry_modified':False,'candidate_file_sha256':digest(candidate_path),
        'diagnosis_file_sha256':digest(diagnosis_path),
        'script_sha256':digest(Path(__file__)),'shapely_version':shapely.__version__,'geos_version':shapely.geos_version_string,
        'source_urls':['https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_36_tabblock20.zip',
                       'https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_34_tabblock20.zip', WATER_URL],
        'geographic_explanation': {
            'liberty_island': 'Liberty Island belongs to New York, while surrounding water belongs to New Jersey under the 1834 compact. Its nearest selected boundary connection is mapped water-only.',
            'ellis_island': 'The original Ellis Island and main building belong to New York; most expanded island area belongs to New Jersey. The Census New York source block is enclosed by mapped New Jersey land, so the proposed connection includes a short land crossing.',
            'primary_context_sources': [
                {'title':'National Park Service: Statue of Liberty frequently asked questions','url':'https://www.nps.gov/stli/planyourvisit/frequently-asked-questions-statue-of-liberty.htm'},
                {'title':'National Park Service: Ellis Island frequently asked questions','url':'https://www.nps.gov/elis/faqs.htm'}],
            'territory_assignment': 'Connections grant adjacency only between the two New York source blocks. New Jersey land and water remain outside the New York assignments.'},
        'policy_assessments': assessments,
        'conditional_partition_extension': {
            'main_anchor_block_geoid':selected_endpoint_geoid,'main_anchor_population':int(anchor_record['POP20']),
            'main_anchor_land_area_m2':int(anchor_record['ALAND20']),'main_anchor_water_area_m2':int(anchor_record['AWATER20']),
            'main_anchor_polygon_part_count':1,'zero_population_island_blocks':list(ISLAND_GEOIDS),
            'statement':'Any valid part-connected partition of the main source component extends to these islands by assigning both zero-population island blocks to the district containing the common anchor block. Every district population stays unchanged, and the two recorded links connect that district under the augmented policy.',
            'prerequisite':'Explicit permission for the Ellis cross-New-Jersey-land exclave link, as well as the Liberty water link.',
            'limits':'This conditional construction does not produce or prove the quality/existence of a balanced main-component district plan. Physical polygon connectivity remains separate, and full graph/polygon-plus-link validation remains necessary.'},
        'measurement':'Local equirectangular lengths of exact source-polygon intersections. Overlapping intersections are merged as normalized intervals; no geometry is buffered or repaired.',
        'limits':['Area-water is mapped 2020 geography, not present water levels or navigability.',
                  'Connection lines are graph-policy proposals, not existing roads, bridges, ferries, or changes to state boundaries.',
                  'Water/land classification is independent of population-aware graph selection and final district validation.',
                  'Context display polygons are clipped and simplified; calculations use full unsimplified source geometry.']}
    payloads = [report, {'type':'FeatureCollection','features':nj_features},
                {'type':'FeatureCollection','features':water_features},
                {'type':'FeatureCollection','features':segment_features},
                {'type':'FeatureCollection','features':island_features}]
    for name,payload in zip(names,payloads,strict=True):
        with (OUTPUT/name).open('x',encoding='utf-8') as stream:
            stream.write(json.dumps(payload,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'links':reports,'islands':island_reports},indent=2))
    return report


if __name__ == '__main__':
    run()
