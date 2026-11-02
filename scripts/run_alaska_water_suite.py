"""Own the serial first Alaska K1 and K2 water-policy attempts."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from scripts import benchmark_alaska_water as benchmark
from scripts.correct_state_block_parts import write_json
from scripts.benchmark_kansas_blocks import sha256
from scripts.state_block_execution_lock import state_execution_lock

OUTPUT=benchmark.OUTPUT


def _artifact(output, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('Artifact path must be relative to this attempt.')
    path=(output/name).resolve()
    if not path.is_relative_to(output.resolve()) or not path.is_file():
        raise ValueError(f'Invalid or missing artifact: {name}')
    return path


def _validate_trace(output, report):
    trace, passes=report.get('optimizer_trace',{}),report.get('solver_progress')
    if (trace.get('observation_ok') is not True or trace.get('telemetry_errors')
            or not isinstance(passes,list) or not passes or trace.get('passes')!=passes
            or [p.get('balance_pass') for p in passes]!=list(range(1,len(passes)+1))
            or any(p.get('errors') or p.get('requested_maxiter')!=1000
                or p.get('inner_optimizer',{}).get('actual_maxiter')!=1000 for p in passes)):
        raise ValueError('Optimizer trace is incomplete, inconsistent or has another budget.')
    completed=[]; terminals=[]
    with _artifact(output,'optimizer-trace.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row.get('event')=='telemetry_error':
                raise ValueError('Saved optimizer trace contains a telemetry error.')
            if row.get('event')=='pass_complete':
                completed.append(row)
            if row.get('event')=='terminal':
                terminals.append(row)
    if len(completed)!=len(passes) or len(terminals)!=len(passes):
        raise ValueError('Saved optimizer trace lacks terminal observations for every pass.')
    for index,(saved,terminal,reported) in enumerate(zip(completed,terminals,passes,strict=True),1):
        if (saved.get('balance_pass')!=index or terminal.get('balance_pass')!=index
                or saved.get('inner_optimizer')!=reported['inner_optimizer']
                or terminal.get('optimizer')!=reported['inner_optimizer']
                or saved.get('solver_exception')!=reported.get('solver_exception')
                or any(saved.get(name)!=reported.get(name) for name in
                    ('objective_evaluations','accepted_iterations','wall_seconds'))):
            raise ValueError('Saved optimizer pass evidence differs from its terminal report.')
    return passes


def validate_terminal(k,output,exit_code,code,inventory):
    output=Path(output)
    benchmark.configuration_for_run(k)
    fallback=output/'terminal-report.json'
    selected=fallback if fallback.exists() else output/'benchmark.json'
    report=json.loads(selected.read_text(encoding='utf-8'))
    progress_path=output/'progress.json'
    progress=json.loads(progress_path.read_text(encoding='utf-8'))
    if (report['state_fips']!='02' or report['district_count']!=k
            or report['configuration']!=benchmark.configuration_for_run(k)
            or report['code_sha256']!=code or report['house_sizes']!=benchmark.HOUSE_SIZES[k]
            or report.get('source',{}).get('archive_sha256')!=benchmark.SOURCE_SHA):
        raise ValueError('Terminal report identity/configuration mismatch.')
    if (report.get('status') not in ('complete_under_recorded_water_policy','failed')
            or not report.get('finished_at') or report.get('active_phase') is not None
            or progress.get('active_phase') is not None or progress.get('status')!=report['status']
            or progress.get('district_count')!=k or progress.get('pid')!=report.get('pid')
            or progress.get('authoritative_report')!=selected.name):
        raise ValueError('Final progress and report do not describe the same terminal attempt; inspect before continuing.')
    if (selected==fallback and not report.get('terminal_write_error')) or (
            selected!=fallback and report.get('terminal_write_error')):
        raise ValueError('Terminal report fallback lacks explicit write-failure provenance.')
    if benchmark.runtime_code()!=code or benchmark.protected_inventory()!=inventory:
        raise ValueError('Original evidence or frozen runtime code changed.')
    audit=report.get('preservation_audit',{})
    if (audit.get('original_files_byte_identical') is not True or audit.get('run_code_unchanged') is not True
            or report.get('preservation_error')):
        raise ValueError('Terminal preservation audit did not pass.')
    hashes=report['artifact_sha256']
    required={'preserved-file-inventory.json','water-connections.json'}
    if k==2:
        required.add('optimizer-trace.jsonl')
    if not required.issubset(hashes):
        raise ValueError('Terminal report lacks required hashed preservation/link/trace artifacts.')
    for name,digest in hashes.items():
        if sha256(_artifact(output,name))!=digest:
            raise ValueError(f'Invalid or changed artifact: {name}')
    if json.loads((output/'preserved-file-inventory.json').read_text())!=inventory:
        raise ValueError('Child preserved inventory differs from its parent.')
    connection_file=json.loads((output/'water-connections.json').read_text())
    if connection_file!={'source_sha256':benchmark.SOURCE_SHA,'connections':report.get('water_connections')}:
        raise ValueError('Saved water connections differ from the terminal report.')
    duration,peak=report.get('timed_pipeline_wall_seconds'),report.get('peak_process_working_set_bytes')
    if (type(duration) not in (int,float) or not math.isfinite(duration) or duration<0
            or type(peak) is not int or peak<=0):
        raise ValueError('Terminal runtime or memory measurement is invalid.')
    if k==1:
        solver=report.get('solver',{})
        if (report.get('solver_progress')!=[] or 'optimizer_trace' in report
                or 'optimizer-trace.jsonl' in hashes or (output/'optimizer-trace.jsonl').exists()
                or solver.get('kind')!='direct_all_blocks_assignment'
                or solver.get('optimizer_ran') is not False or solver.get('centers_converged') is not None
                or solver.get('outer_iterations')!=0 or solver.get('outer_iteration_limit_reached') is not False
                or solver.get('inner_optimization_status')!='not_applicable'):
            raise ValueError('K1 must be a direct assignment without any optimizer or trace.')
        passes=[]
    else:
        passes=_validate_trace(output,report)
    if report['status']=='failed':
        failure=report.get('optimizer_failure',{})
        last=passes[-1]['inner_optimizer'] if passes else {}
        if (k!=2 or exit_code==0 or report.get('failed_phase')!='solve'
                or not str(report.get('error','')).startswith('DistrictingOptimizationError:')
                or failure.get('plan_returned') is not False or last.get('success') is not False
                or any(failure.get(name)!=last.get(name) for name in
                    ('status','message','iterations','function_evaluations'))
                or not all(p['inner_optimizer'].get('success') is True for p in passes[:-1])
                or passes[-1].get('solver_exception',{}).get('type')!='DistrictingOptimizationError'
                or any(name in report for name in ('initial_plan','final_plan','maps','solver'))):
            raise ValueError(f'Operational or geometry failure requires inspection: {report.get("error")}')
        if any((output/name).exists() for name in ('maps','initial-solver-result.json','after-repair-result.json','solver-result.json')):
            raise ValueError('Failed solver unexpectedly produced plan/map artifacts.')
        return {'status':'verified_numerical_failure','report':selected.name,
            'report_sha256':sha256(selected),'progress_sha256':sha256(progress_path),'error':report['error']}
    if report['status']!='complete_under_recorded_water_policy' or exit_code!=0:
        raise ValueError('Child exit code and completion report disagree.')
    if k==2:
        solver=report.get('solver',{})
        outer=solver.get('outer_iterations')
        if (solver.get('kind')!='balanced_power_diagram' or solver.get('optimizer_ran') is not True
                or solver.get('all_inner_optimizer_passes_succeeded') is not True
                or type(outer) is not int or not 1<=outer<=80 or len(passes)!=outer+1
                or solver.get('outer_iteration_limit_reached')!=(outer==80)
                or type(solver.get('centers_converged')) is not bool
                or not all(p['inner_optimizer'].get('success') is True and not p.get('solver_exception') for p in passes)):
            raise ValueError('Completed K2 lacks successful observed inner solves and consistent outer convergence.')
    required.update({'initial-solver-result.json','after-repair-result.json','solver-result.json',
        'move-audit.json','maps/manifest.json','maps/index.html'})
    required.update(f'maps/{stem}.{frame}.geojson.gz' for stem in
        ('districts-full','districts-state','districts-national','connections') for frame in ('working','wrapped'))
    if not required.issubset(hashes):
        raise ValueError('Completed child lacks required hashed assignments or map artifacts.')
    final=report['final_plan']
    if (sum(final['district_populations'])!=benchmark.TOTAL or final['block_count']!=benchmark.BLOCKS
            or final['policy_part_components']!=[1]*k or not final['all_districts_policy_connected']
            or not report['maps']['connectivity_validation']['passed']):
        raise ValueError('Final graph/polygon/population audit failed.')
    manifest=json.loads((output/'maps/manifest.json').read_text())
    if (any(report['maps'].get(name)!=value for name,value in manifest.items() if name!='elapsed_seconds')
            or manifest.get('status')!='validated_complete_map' or manifest.get('district_count')!=k
            or manifest.get('total_population')!=benchmark.TOTAL or manifest.get('block_count')!=benchmark.BLOCKS
            or manifest.get('district_populations')!=final['district_populations']
            or manifest.get('seam_validation',{}).get('passed') is not True):
        raise ValueError('Saved map manifest differs from the accepted terminal maps or source totals.')
    validation=manifest['connectivity_validation']; rows=validation.get('districts',[])
    if (validation.get('source_coverage_preserved_exactly') is not True
            or validation.get('independent_source_coverage_valid') is not True
            or validation.get('independent_district_coverage_valid') is not True
            or [row.get('district_id') for row in rows]!=list(range(k))
            or [row.get('connected_components_after_links') for row in rows]!=[1]*k
            or [row.get('physical_polygon_components') for row in rows]!=final['physical_part_components']):
        raise ValueError('Independent unsimplified polygon connectivity does not match graph acceptance.')
    for name,payload in manifest.get('payloads',{}).items():
        if hashes.get('maps/'+name)!=payload.get('sha256') or payload.get('gzip_verified') is not True:
            raise ValueError('Map payload hashes or compressed validation are incomplete.')
    counties=manifest.get('counties',[])
    if not counties or sum(row.get('block_count',0) for row in counties)!=benchmark.BLOCKS:
        raise ValueError('Map county coverage is incomplete.')
    for county in counties:
        for field in ('working_file','wrapped_file'):
            if 'maps/'+county[field] not in hashes:
                raise ValueError('Map county payload is missing its artifact hash.')
    saved=json.loads((output/'solver-result.json').read_text())
    if (len(saved['assignments'])!=benchmark.BLOCKS or set(saved['assignments'].values())!=set(range(k))
            or any(type(label) is not int for label in saved['assignments'].values())
            or saved.get('plan_kind')!='final'):
        raise ValueError('Saved assignment universe is incomplete.')
    provenance={'source_sha256':benchmark.SOURCE_SHA,'code_sha256':code,
        'configuration':report['configuration'],'water_connections_sha256':hashes['water-connections.json']}
    if saved.get('provenance')!=provenance:
        raise ValueError('Final assignment provenance differs from the accepted attempt.')
    return {'status':'complete','report':selected.name,'report_sha256':sha256(selected),
        'progress_sha256':sha256(progress_path),'timed_pipeline_wall_seconds':duration,
        'peak_process_working_set_bytes':peak}


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    manifest=OUTPUT/'run.json'
    with state_execution_lock('02'):
        for k in benchmark.COUNTS:
            benchmark.validate_output(OUTPUT/f'states/02/districts-{k}',k)
            if (OUTPUT/f'districts-{k}.log').exists():
                raise FileExistsError('Prior child log exists; no duplicate attempt.')
        with manifest.open('x',encoding='utf-8') as stream:
            json.dump({'status':'admitted','pid':os.getpid(),'started_at':benchmark.now()},stream)
    started=time.perf_counter()
    record={'status':'running','pid':os.getpid(),'started_at':benchmark.now(),
        'execution':'serial_fresh_processes','jobs':[{'district_count':k,'status':'pending'} for k in benchmark.COUNTS]}
    child=None
    job=None
    try:
        code=benchmark.runtime_code(); inventory=benchmark.protected_inventory()
        tests=json.loads((OUTPUT/'prelaunch-tests.json').read_text())
        if tests.get('exit_code')!=0 or tests.get('runtime_code_sha256')!=code:
            raise ValueError('Required passing tests do not match frozen runtime code.')
        record.update(code_sha256=code,protected_file_count=len(inventory),
            prelaunch_tests_sha256=sha256(OUTPUT/'prelaunch-tests.json'))
        write_json(OUTPUT/'preserved-file-inventory.json',inventory)
        write_json(manifest,record)
        for job in record['jobs']:
            if benchmark.runtime_code()!=code or benchmark.protected_inventory()!=inventory:
                raise ValueError('Code/source changed before child launch.')
            k=job['district_count']; out=OUTPUT/f'states/02/districts-{k}'
            command=[sys.executable,'-X','utf8','-u',str(ROOT/'scripts/benchmark_alaska_water.py'),
                '--district-count',str(k),'--output',str(out)]
            job.update(status='starting',started_at=benchmark.now(),command=command)
            write_json(manifest,record)
            child_start=time.perf_counter()
            with (OUTPUT/f'districts-{k}.log').open('xb') as log:
                child=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                job.update(status='running',pid=child.pid)
                write_json(manifest,record)
                print(f'Alaska K{k} running, launcher {child.pid}.',flush=True)
                exit_code=child.wait()
            child=None
            job.update(exit_code=exit_code,finished_at=benchmark.now(),process_wall_seconds=time.perf_counter()-child_start)
            with state_execution_lock('02'):
                validation=validate_terminal(k,out,exit_code,code,inventory)
            job.update(status=validation['status'],terminal_validation=validation)
            write_json(manifest,record)
            print(f'Alaska K{k}: {job["status"]}.',flush=True)
        record['status']='complete' if all(j['status']=='complete' for j in record['jobs']) else 'complete_with_numerical_failures'
    except BaseException as error:
        if child is not None:
            job['exit_code']=child.wait()
            job['finished_at']=benchmark.now()
            job['process_wall_seconds']=time.perf_counter()-child_start
        if job is not None and 'terminal_validation' not in job:
            job['status']='needs_inspection'
        record.update(status='stopped',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        record.update(finished_at=benchmark.now(),elapsed_wall_seconds=time.perf_counter()-started)
        try:
            write_json(manifest,record)
        except OSError as error:
            record['manifest_write_error']=str(error)
            with (OUTPUT/f'emergency-{os.getpid()}.json').open('x',encoding='utf-8') as stream:
                json.dump(record,stream,indent=2)
            raise


if __name__=='__main__':
    main()
