"""Fresh Alaska K1/K2 plans in a declared continuous longitude frame.

Only new Alaska outputs are written. The numerical solver and all previous
state adapters remain unchanged. K1 is a direct assignment, not an optimization.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
from numbers import Integral
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from districting import Unit, balanced_power_diagram, DistrictingOptimizationError
from districting.connectivity import repair_and_rebalance
from districting.part_connectivity import part_component_counts
from scripts.alaska_geometry import load_normalized_parts, build_exact_part_graph
from scripts.alaska_recorded_links import build_alaska_connections
from scripts.alaska_map_export import export_alaska_maps
from scripts.benchmark_kansas_anchors import population_metrics
from scripts.benchmark_kansas_blocks import Measurements, process_memory, sha256
from scripts.correct_state_block_parts import block_adjacency, write_json
from scripts.district_optimizer_trace import trace_optimizer
from scripts.state_block_execution_lock import state_execution_lock

SUITE=ROOT/'.cache/state-block-benchmark/suite-through-1000'
OUTPUT=SUITE/'policies/alaska-water-v1'
ARCHIVE=ROOT/'.cache/state-block-benchmark/source/02/tl_2020_02_tabblock20.zip'
SOURCE_SHA='6fe96f3a8bbaf78945ee3a3897264ed74f1b72bc0cb46ffd434039729dccf493'
COUNTS=(1,2)
HOUSE_SIZES={1:[435,574],2:[692,1000]}
SEED=20200955
TOTAL=733391
BLOCKS=28568
RUNTIME_FILES=(
    'scripts/benchmark_alaska_water.py','scripts/run_alaska_water_suite.py',
    'scripts/alaska_geometry.py','scripts/alaska_recorded_links.py','scripts/alaska_map_export.py',
    'scripts/assets/alaska-block-viewer.html','scripts/diagnose_alaska_topology.py',
    'scripts/hawaii_population_links.py','scripts/district_block_island_links.py',
    'scripts/diagnose_hawaii_topology.py','scripts/district_optimizer_trace.py',
    'scripts/correct_state_block_parts.py','scripts/benchmark_kansas_anchors.py',
    'scripts/benchmark_kansas_blocks.py','scripts/state_block_execution_lock.py',
    'districting/__init__.py','districting/algorithm.py','districting/connectivity.py',
    'districting/part_connectivity.py',
    'scripts/district_block_sources.py','scripts/benchmark_state_blocks.py',
    'scripts/district_block_part_graph.py','scripts/district_block_adjacency.py',
    'scripts/district_block_graph_cache.py','scripts/district_block_map_export.py',
    'scripts/state_block_map_export.py','apportionment/methods.py',
    'districting/precompute.py','apportionment/data/apportionment_2020.py',
)


def now():
    return datetime.now(timezone.utc).isoformat()


def runtime_code():
    return {name:sha256(ROOT/name) for name in RUNTIME_FILES}


def protected_inventory():
    paths={SUITE/'suite.json',ARCHIVE,ARCHIVE.with_suffix('.manifest.json'),
           ROOT/'prompts/alaska-topology-diagnosis.md',ROOT/'prompts/alaska-topology-diagnosis.json'}
    for directory in (SUITE/'states/02',SUITE/'diagnostics/alaska',SUITE/'diagnostics/alaska-initial-v1'):
        if not directory.is_dir():
            raise ValueError('Missing preserved Alaska source or diagnosis evidence.')
        paths.update(p for p in directory.rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix():sha256(p) for p in sorted(paths)}


def configuration_for_run(k):
    if type(k) is not int or k not in COUNTS:
        raise ValueError('Only Alaska K1/K2 are authorized.')
    return {'seed':SEED,'inner_max_iterations':1000,'max_outer_iterations':80,
        'center_tolerance_m':1e-4,'max_rebalance_moves':1000,
        'population_policy':'population-aware-rooted-boundary-forest-v1',
        'population_group_tolerance':.01,'one_district_strategy':'direct_all_blocks_assignment',
        'normalization':'whole-block positive longitudes minus 360; exact source part ownership',
        'solver_projection':'population-centered equirectangular from normalized source internal points',
        'projection_change':'No Alaska Albers substitution; same approximate distance model as prior state benchmarks.',
        'physical_adjacency':'F***1**** on original polygon parts in the continuous Alaska frame',
        'policy_adjacency':'physical shared edges plus individually recorded water connections',
        'datum':'original TIGER NAD83; longitude representation change only'}


def validate_output(output,k):
    configuration_for_run(k)
    expected=(OUTPUT/f'states/02/districts-{k}').resolve()
    if Path(output).resolve()!=expected:
        raise ValueError('Output must be the matching new Alaska policy directory.')
    if expected.exists() and (not expected.is_dir() or any(expected.iterdir())):
        raise FileExistsError('Refusing to overwrite an earlier Alaska attempt.')


def units_from_records(records):
    if not records or len({r['geoid'] for r in records})!=len(records):
        raise ValueError('Source records must be nonempty with unique GEOIDs.')
    total=sum(r['population'] for r in records)
    if total<=0:
        raise ValueError('Positive source population is required.')
    lon0=sum(r['working_internal_point'][0]*r['population'] for r in records)/total
    lat0=sum(r['working_internal_point'][1]*r['population'] for r in records)/total
    ys=6371000*math.pi/180; xs=ys*math.cos(math.radians(lat0))
    units=[Unit(r['geoid'],((r['working_internal_point'][0]-lon0)*xs,
                           (r['working_internal_point'][1]-lat0)*ys),r['population']) for r in records]
    return units,{'kind':'population-centered-equirectangular','lon0':lon0,'lat0':lat0,
        'x_meters_per_degree':xs,'y_meters_per_degree':ys,'dateline_unwrapped':True,
        'distance_model':'approximate local plane; broad-state distortion remains',
        'location_source':'TIGER INTPT internal points, not household positions or population centroids'}


def audit_plan(labels, populations, physical, augmented, k):
    if (len(labels)!=len(populations) or len(labels)!=len(physical.unit_to_parts)
            or any(isinstance(x,bool) or not isinstance(x,Integral) or not 0<=x<k for x in labels)
            or set(labels)!=set(range(k))):
        raise ValueError('Assignments must cover each source block once and every district.')
    totals=[sum(p for label,p in zip(labels,populations,strict=True) if label==d) for d in range(k)]
    physical_counts=list(part_component_counts(physical,labels,n_districts=k))
    policy_counts=list(part_component_counts(augmented,labels,n_districts=k))
    return {**population_metrics(totals),'block_count':len(labels),
        'district_block_counts':[sum(label==d for label in labels) for d in range(k)],
        'physical_part_components':physical_counts,'policy_part_components':policy_counts,
        'all_districts_physically_connected':all(c==1 for c in physical_counts),
        'all_districts_policy_connected':all(c==1 for c in policy_counts)}


def solve_initial(units,k,output,report):
    if k==1:
        report['solver']={'kind':'direct_all_blocks_assignment','optimizer_ran':False,
            'centers_converged':None,'outer_iterations':0,'outer_iteration_limit_reached':False,
            'inner_optimization_status':'not_applicable'}
        return tuple(0 for _ in units),[]
    trace=None
    try:
        with trace_optimizer(output/'optimizer-trace.jsonl') as trace:
            report['solver_progress']=trace.passes
            initial=balanced_power_diagram(units,k,seed=SEED,max_outer_iterations=80,
                center_tol=1e-4,inner_max_iterations=1000)
    finally:
        if trace is not None:
            report['optimizer_trace']=trace.summary()
            if (output/'optimizer-trace.jsonl').is_file():
                report['artifact_sha256']['optimizer-trace.jsonl']=sha256(output/'optimizer-trace.jsonl')
    if trace is None or not trace.observation_ok or not trace.passes or not all(
            row.get('inner_optimizer',{}).get('success') for row in trace.passes):
        raise ValueError('Successful independently observed inner passes are required.')
    geoids=[u.geoid for u in units]
    if set(initial.assignments)!=set(geoids):
        raise ValueError('Solver assignments differ from source blocks.')
    report['solver']={'kind':'balanced_power_diagram','optimizer_ran':True,
        'outer_iterations':initial.iterations,'centers_converged':initial.converged,
        'outer_iteration_limit_reached':initial.iterations>=80,
        'all_inner_optimizer_passes_succeeded':True,
        'initial_population_balance':population_metrics([initial.populations[i] for i in range(k)])}
    return tuple(initial.assignments[g] for g in geoids),[asdict(c) for c in initial.centers]


def run(k,output):
    output=Path(output).resolve()
    validate_output(output,k)
    with state_execution_lock('02'):
        validate_output(output,k)
        return _run_locked(k,output)


def _run_locked(k,output):
    output.mkdir(parents=True)
    started=time.perf_counter()
    measure=Measurements()
    before=None
    report={'status':'running','state':'Alaska','state_fips':'02','district_count':k,
        'house_sizes':HOUSE_SIZES[k],'source_year':2020,'unit':'census_block','started_at':now(),
        'pid':os.getpid(),'configuration':configuration_for_run(k),'solver_progress':[],
        'artifact_sha256':{},'code_sha256':{},'phases':{},
        'environment':{'python':sys.version,'platform':platform.platform(),
            'packages':{n:version(n) for n in ('numpy','scipy','pyshp','shapely')}},
        'measurement_notes':['Fresh serial process. Imports and lock acquisition excluded from pipeline time.',
            'Original strict run stopped at antimeridian preflight; no solved strict baseline exists.',
            'K1 direct assignment has no optimizer. K2 uses unchanged normalized optimizer with observational tracing.',
            'Physical adjacency is distinct from connectivity using recorded links.',
            'No source blocks or zero-population water coverage removed. No foreign territory assigned.',
            'Existing source archive is reused; normalized graph built and independently verified in each process.',
            'Wrapped exports preserve original NAD83 coordinates; no datum or Alaska Albers transform.']}
    @contextmanager
    def phase(name):
        report['active_phase']=name
        write_json(output/'progress.json',{'status':report['status'],'active_phase':name,'district_count':k,'pid':os.getpid()})
        with measure.phase(name):
            yield
        report['phases']=dict(measure.phases)
        write_json(output/'benchmark.json',report)
    def save(name,data):
        write_json(output/name,data)
        report['artifact_sha256'][name]=sha256(output/name)
    try:
        with phase('preservation_and_configuration'):
            before=protected_inventory()
            save('preserved-file-inventory.json',before)
            report['code_sha256']=runtime_code()
            if sha256(ARCHIVE)!=SOURCE_SHA:
                raise ValueError('Original Alaska source archive identity changed.')
            report['source']={'archive_path':str(ARCHIVE),'archive_sha256':SOURCE_SHA,
                'resident_population':TOTAL,'block_count':BLOCKS}
            strict=SUITE/'states/02/districts-1/benchmark.json'
            old=json.loads(strict.read_text())
            if old['status']!='unsupported_antimeridian_topology' or old.get('solver_progress'):
                raise ValueError('Expected original unsolved Alaska antimeridian preflight.')
            report['strict_baseline']={'status':old['status'],'report':str(strict),'sha256':sha256(strict),'solver_ran':False}
        with phase('load_source_and_normalize_longitudes'):
            parts,records,owners,part_indices,normalization=load_normalized_parts(ARCHIVE)
            if len(records)!=BLOCKS or sum(r['population'] for r in records)!=TOTAL:
                raise ValueError('Official Alaska source totals do not reconcile.')
            units,projection=units_from_records(records)
            report['input']={**normalization,'projection':projection}
            geoids=[r['geoid'] for r in records]; populations=[r['population'] for r in records]
        with phase('build_physical_part_graph'):
            physical,report['physical_part_graph']=build_exact_part_graph(parts,owners)
        with phase('independently_verify_and_add_recorded_water_connections'):
            augmented,connections,report['island_policy_audit']=build_alaska_connections(
                parts,records,owners,part_indices,physical,k)
            if part_component_counts(augmented,[0]*BLOCKS,n_districts=1)!=(1,):
                raise ValueError('Proposed Alaska source graph is not connected.')
            save('water-connections.json',{'source_sha256':SOURCE_SHA,'connections':list(connections)})
            report['water_connections']=list(connections)
            adjacency=block_adjacency(augmented,BLOCKS)
        provenance={'source_sha256':SOURCE_SHA,'code_sha256':report['code_sha256'],
            'configuration':report['configuration'],'water_connections_sha256':report['artifact_sha256']['water-connections.json']}
        with phase('direct_assignment' if k==1 else 'solve'):
            labels,centers=solve_initial(units,k,output,report)
            report['initial_plan']=audit_plan(labels,populations,physical,augmented,k)
            save('initial-solver-result.json',{'assignments':dict(zip(geoids,labels,strict=True)),
                'centers':centers,'provenance':provenance,'plan_kind':'initial'})
        with phase('repair_and_rebalance'):
            corrected=repair_and_rebalance(adjacency,labels,populations,n_districts=k,max_moves=1000,part_graph=augmented)
        with phase('save_and_audit_final_assignments'):
            for name,stage_labels in [('after_repair',corrected.repaired_assignments),('final',corrected.assignments)]:
                audit=audit_plan(stage_labels,populations,physical,augmented,k)
                if not audit['all_districts_policy_connected'] or sum(audit['district_populations'])!=TOTAL:
                    raise ValueError('District policy connectivity or population audit failed.')
                report[name+'_plan']=audit
                save('solver-result.json' if name=='final' else 'after-repair-result.json',
                    {'assignments':dict(zip(geoids,stage_labels,strict=True)),'provenance':provenance,'plan_kind':name,
                     'initial_centers_for_provenance_only':centers})
            def moves(items):
                return [{**asdict(m),'geoids':[geoids[i] for i in m.units]} for m in items]
            save('move-audit.json',{'stop_reason':corrected.stop_reason,'provenance':provenance,
                'repair_moves':moves(corrected.repair_moves),'part_repair_moves':moves(corrected.part_repair_moves),
                'rebalance_moves':moves(corrected.rebalance_moves)})
            report['postprocessing']={'stop_reason':corrected.stop_reason,
                'repair_move_count':len(corrected.repair_moves),'part_repair_move_count':len(corrected.part_repair_moves),
                'rebalance_move_count':len(corrected.rebalance_moves)}
        with phase('independent_polygon_and_seam_validation_map_export'):
            report['maps']=export_alaska_maps(parts,records,owners,part_indices,
                dict(zip(geoids,corrected.assignments,strict=True)),connections,output/'maps',projection=projection)
            if not report['maps']['connectivity_validation']['passed']:
                raise ValueError('Independent polygon/link validation failed.')
            for path in sorted((output/'maps').rglob('*')):
                if path.is_file():
                    report['artifact_sha256'][path.relative_to(output).as_posix()]=sha256(path)
        with phase('final_preservation_validation'):
            if protected_inventory()!=before or runtime_code()!=report['code_sha256']:
                raise ValueError('Historical evidence or frozen runtime code changed.')
            report['preservation_audit']={'original_files_byte_identical':True,'run_code_unchanged':True,'protected_file_count':len(before)}
        report['status']='complete_under_recorded_water_policy'
    except BaseException as error:
        report.update(status='failed',error=f'{type(error).__name__}: {error}',failed_phase=report.get('active_phase'))
        if isinstance(error,DistrictingOptimizationError):
            report['optimizer_failure']={'reason':error.reason,'status':error.status,
                'message':error.optimizer_message,'iterations':error.iterations,
                'function_evaluations':error.function_evaluations,'plan_returned':False}
        raise
    finally:
        report.update(finished_at=now(),timed_pipeline_wall_seconds=time.perf_counter()-started,
            peak_process_working_set_bytes=process_memory()[1],phases=dict(measure.phases))
        measure.close()
        if 'preservation_audit' not in report:
            try:
                report['preservation_audit']={'original_files_byte_identical':before is not None and protected_inventory()==before,
                    'run_code_unchanged':bool(report['code_sha256']) and runtime_code()==report['code_sha256']}
            except Exception as error:
                report['preservation_error']=str(error)
        report['active_phase']=None
        try:
            write_json(output/'benchmark.json',report)
            report_path=output/'benchmark.json'
        except OSError as error:
            report['terminal_write_error']=str(error)
            report_path=output/'terminal-report.json'
            with report_path.open('x',encoding='utf-8') as stream:
                json.dump(report,stream,indent=2,allow_nan=False)
        try:
            write_json(output/'progress.json',{'status':report['status'],'active_phase':None,'district_count':k,
                'authoritative_report':report_path.name,'pid':os.getpid()})
        except OSError as error:
            print(f'Final progress display write failed: {error}',flush=True)
        print(f'Terminal report: {report_path}',flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--district-count',type=int,required=True,choices=COUNTS)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run(args.district_count,args.output)
