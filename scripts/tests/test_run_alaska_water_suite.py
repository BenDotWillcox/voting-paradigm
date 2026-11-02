"""Alaska launcher refuses ambiguous terminals and preserves serial ownership."""
from contextlib import nullcontext
import copy
import json
from types import SimpleNamespace

import pytest

from districting import Unit
from scripts import run_alaska_water_suite as launcher


def terminal_fixture(tmp_path, monkeypatch, *, count=2, failed=False):
    b=launcher.benchmark
    output=tmp_path/'child'; output.mkdir()
    code={'fixture.py':'frozen'}; inventory={'original.json':'unchanged'}
    monkeypatch.setattr(b,'runtime_code',lambda:code)
    monkeypatch.setattr(b,'protected_inventory',lambda:inventory)
    monkeypatch.setattr(b,'TOTAL',9); monkeypatch.setattr(b,'BLOCKS',4)
    hashes={}
    def artifact(name,value):
        path=output/name; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value))
        hashes[name]=launcher.sha256(path)
    artifact('preserved-file-inventory.json',inventory)
    connections=[{'id':'ak-test-water'}]
    artifact('water-connections.json',{'source_sha256':b.SOURCE_SHA,'connections':connections})
    report={'state_fips':'02','district_count':count,'house_sizes':b.HOUSE_SIZES[count],
        'configuration':b.configuration_for_run(count),'code_sha256':code,
        'source':{'archive_sha256':b.SOURCE_SHA},'status':'failed' if failed else 'complete_under_recorded_water_policy',
        'finished_at':'done','active_phase':None,'pid':1234,'water_connections':connections,
        'preservation_audit':{'original_files_byte_identical':True,'run_code_unchanged':True},
        'artifact_sha256':hashes,'timed_pipeline_wall_seconds':20.,'peak_process_working_set_bytes':1000,
        'solver_progress':[]}
    if count==2:
        passes=[]; events=[]
        for index in range(1,2 if failed else 3):
            optimizer={'success':not failed,'actual_maxiter':1000,'status':1 if failed else 0,
                'message':'budget exhausted' if failed else 'converged','iterations':1000 if failed else 2,
                'function_evaluations':1100 if failed else 3}
            entry={'balance_pass':index,'requested_maxiter':1000,'errors':[],
                'inner_optimizer':optimizer,'objective_evaluations':optimizer['function_evaluations'],
                'accepted_iterations':optimizer['iterations'],'wall_seconds':1.}
            if failed:
                entry['solver_exception']={'type':'DistrictingOptimizationError','message':'budget exhausted'}
            passes.append(entry)
            events.extend([{'event':'terminal','balance_pass':index,'optimizer':optimizer},
                {'event':'pass_complete',**{key:entry.get(key) for key in
                    ('balance_pass','inner_optimizer','objective_evaluations','accepted_iterations','wall_seconds','solver_exception')}}])
        trace_path=output/'optimizer-trace.jsonl'
        trace_path.write_text('\n'.join(json.dumps(row) for row in events)+'\n')
        hashes[trace_path.name]=launcher.sha256(trace_path)
        report.update(solver_progress=passes,optimizer_trace={'observation_ok':True,'passes':passes,'telemetry_errors':[]})
    if failed:
        report.update(failed_phase='solve',error='DistrictingOptimizationError: budget exhausted',
            optimizer_failure={'plan_returned':False,'reason':'iteration_limit',**{
                key:optimizer[key] for key in ('status','message','iterations','function_evaluations')}})
    else:
        report['solver']=({'kind':'direct_all_blocks_assignment','optimizer_ran':False,'centers_converged':None,
            'outer_iterations':0,'outer_iteration_limit_reached':False,'inner_optimization_status':'not_applicable'} if count==1 else
            {'kind':'balanced_power_diagram','optimizer_ran':True,'outer_iterations':1,'centers_converged':True,
             'outer_iteration_limit_reached':False,'all_inner_optimizer_passes_succeeded':True})
        pops=[9] if count==1 else [4,5]; physical=[2] if count==1 else [2,1]
        final={'district_populations':pops,'block_count':4,'policy_part_components':[1]*count,
            'all_districts_policy_connected':True,'physical_part_components':physical}
        report['final_plan']=final
        provenance={'source_sha256':b.SOURCE_SHA,'code_sha256':code,'configuration':report['configuration'],
            'water_connections_sha256':hashes['water-connections.json']}
        artifact('solver-result.json',{'plan_kind':'final','provenance':provenance,
            'assignments':{str(i):(0 if count==1 else int(i==3)) for i in range(4)}})
        for name in ('initial-solver-result.json','after-repair-result.json','move-audit.json'):
            artifact(name,{'saved':'evidence'})
        artifact('maps/index.html','viewer')
        payloads={}
        names=[f'{stem}.{frame}.geojson.gz' for stem in ('districts-full','districts-state','districts-national','connections')
               for frame in ('working','wrapped')]
        names+=['counties/001.working.geojson.gz','counties/001.wrapped.geojson.gz']
        for name in names:
            artifact('maps/'+name,{'compressed':'verified elsewhere'})
            payloads[name]={'sha256':hashes['maps/'+name],'gzip_verified':True}
        manifest={'status':'validated_complete_map','district_count':count,'total_population':9,'block_count':4,
            'district_populations':pops,'seam_validation':{'passed':True},'payloads':payloads,
            'counties':[{'block_count':4,'working_file':'counties/001.working.geojson.gz','wrapped_file':'counties/001.wrapped.geojson.gz'}],
            'connectivity_validation':{'passed':True,'source_coverage_preserved_exactly':True,
                'independent_source_coverage_valid':True,'independent_district_coverage_valid':True,
                'districts':[{'district_id':i,'connected_components_after_links':1,'physical_polygon_components':physical[i]} for i in range(count)]}}
        artifact('maps/manifest.json',manifest)
        report['maps']=manifest
    progress={'status':report['status'],'active_phase':None,'district_count':count,'pid':1234,'authoritative_report':'benchmark.json'}
    return output,code,inventory,report,progress


def validate(fixture, *, exit_code=0, fallback=False):
    output,code,inventory,report,progress=fixture
    launcher.write_json(output/('terminal-report.json' if fallback else 'benchmark.json'),report)
    launcher.write_json(output/'progress.json',progress)
    return launcher.validate_terminal(report['district_count'],output,exit_code,code,inventory)


@pytest.mark.parametrize('count',(1,2))
def test_accepts_corroborated_complete_terminal(tmp_path,monkeypatch,count):
    fixture=terminal_fixture(tmp_path,monkeypatch,count=count)
    result=validate(fixture)
    assert result['status']=='complete'
    assert result['report']=='benchmark.json'
    assert result['progress_sha256']==launcher.sha256(fixture[0]/'progress.json')


def test_accepts_only_corroborated_numerical_failure(tmp_path,monkeypatch):
    fixture=terminal_fixture(tmp_path,monkeypatch,failed=True)
    assert validate(fixture,exit_code=1)['status']=='verified_numerical_failure'


def test_actual_small_k2_solve_trace_satisfies_terminal_validator(tmp_path,monkeypatch):
    fixture=terminal_fixture(tmp_path,monkeypatch)
    output,_,_,report,_=fixture
    solve_dir=tmp_path/'actual-synthetic-solve'; solve_dir.mkdir()
    units=[Unit(str(i),(float(i)*1000.,0.),population) for i,population in enumerate((4,0,0,5))]
    observed={'artifact_sha256':{}}
    labels,_=launcher.benchmark.solve_initial(units,2,solve_dir,observed)
    assert len(labels)==4 and set(labels)=={0,1}
    (output/'optimizer-trace.jsonl').write_bytes((solve_dir/'optimizer-trace.jsonl').read_bytes())
    report['artifact_sha256']['optimizer-trace.jsonl']=launcher.sha256(output/'optimizer-trace.jsonl')
    for key in ('solver','solver_progress','optimizer_trace'):
        report[key]=observed[key]
    assert validate(fixture)['status']=='complete'


def test_explicit_terminal_write_fallback_is_selected(tmp_path,monkeypatch):
    fixture=terminal_fixture(tmp_path,monkeypatch,count=1)
    fixture[3]['terminal_write_error']='simulated sharing violation'
    fixture[4]['authoritative_report']='terminal-report.json'
    launcher.write_json(fixture[0]/'benchmark.json',{'status':'running'})
    result=validate(fixture,fallback=True)
    assert result['report']=='terminal-report.json'


@pytest.mark.parametrize('change',('no-provenance','wrong-selected-report','running-phase','stale-status','wrong-pid','unfinished'))
def test_stale_or_ambiguous_terminal_is_rejected(tmp_path,monkeypatch,change):
    fixture=terminal_fixture(tmp_path,monkeypatch,count=1)
    report,progress=fixture[3:]
    if change=='no-provenance':
        progress['authoritative_report']='terminal-report.json'
    elif change=='wrong-selected-report': progress['authoritative_report']='terminal-report.json'
    elif change=='running-phase': progress['active_phase']='export'
    elif change=='stale-status': progress['status']='running'
    elif change=='wrong-pid': progress['pid']=4321
    elif change=='unfinished': report.pop('finished_at')
    with pytest.raises(ValueError,match='terminal|fallback'):
        validate(fixture,fallback=change=='no-provenance')


@pytest.mark.parametrize('change',('failed-pass','observation','budget','missing-pass','file-disagrees','outer-count'))
def test_k2_trace_and_solver_claims_must_agree(tmp_path,monkeypatch,change):
    fixture=terminal_fixture(tmp_path,monkeypatch)
    output,_,_,report,_=fixture
    if change=='failed-pass': report['solver_progress'][0]['inner_optimizer']['success']=False
    elif change=='observation': report['optimizer_trace']['observation_ok']=False
    elif change=='budget': report['solver_progress'][0]['inner_optimizer']['actual_maxiter']=300
    elif change=='missing-pass': report['solver_progress'].pop()
    elif change=='file-disagrees':
        path=output/'optimizer-trace.jsonl'; events=[json.loads(row) for row in path.read_text().splitlines()]
        events[-1]['accepted_iterations']=999
        path.write_text('\n'.join(json.dumps(row) for row in events)+'\n')
        report['artifact_sha256'][path.name]=launcher.sha256(path)
    elif change=='outer-count': report['solver']['outer_iterations']=80
    with pytest.raises(ValueError,match='trace|pass|solves'):
        validate(fixture)


@pytest.mark.parametrize('change',('optimizer-ran','trace-present','convergence-claim'))
def test_k1_cannot_claim_optimizer_activity_or_convergence(tmp_path,monkeypatch,change):
    fixture=terminal_fixture(tmp_path,monkeypatch,count=1)
    if change=='optimizer-ran': fixture[3]['solver']['optimizer_ran']=True
    elif change=='trace-present': (fixture[0]/'optimizer-trace.jsonl').write_text('unexpected')
    else: fixture[3]['solver']['centers_converged']=True
    with pytest.raises(ValueError,match='K1 must be a direct assignment'):
        validate(fixture)


@pytest.mark.parametrize('change',('failure-status','wrong-phase','claimed-plan','successful-exit','wrong-exception','map-file'))
def test_numerical_failure_requires_matching_trace_and_no_final_plan(tmp_path,monkeypatch,change):
    fixture=terminal_fixture(tmp_path,monkeypatch,failed=True)
    report=fixture[3]
    if change=='failure-status': report['optimizer_failure']['status']=99
    elif change=='wrong-phase': report['failed_phase']='export'
    elif change=='claimed-plan': report['final_plan']={}
    elif change=='wrong-exception': report['error']='PermissionError: cannot write'
    elif change=='map-file': (fixture[0]/'maps').mkdir()
    with pytest.raises(ValueError,match='failure|artifacts'):
        validate(fixture,exit_code=0 if change=='successful-exit' else 1)


@pytest.mark.parametrize('change',('missing-required-hash','changed-file','path-escape','map-counts','seam-failure','changed-provenance'))
def test_incomplete_or_changed_artifacts_are_rejected(tmp_path,monkeypatch,change):
    fixture=terminal_fixture(tmp_path,monkeypatch,count=1)
    output,_,_,report,_=fixture
    if change=='missing-required-hash': report['artifact_sha256'].pop('maps/districts-full.wrapped.geojson.gz')
    elif change=='changed-file': (output/'solver-result.json').write_text('changed')
    elif change=='path-escape': report['artifact_sha256']['../outside']='digest'
    elif change in ('map-counts','seam-failure'):
        manifest=copy.deepcopy(report['maps'])
        if change=='map-counts': manifest['connectivity_validation']['districts'][0]['connected_components_after_links']=2
        else: manifest['seam_validation']['passed']=False
        launcher.write_json(output/'maps/manifest.json',manifest)
        report['artifact_sha256']['maps/manifest.json']=launcher.sha256(output/'maps/manifest.json')
        report['maps']=manifest
    else:
        path=output/'solver-result.json'; data=json.loads(path.read_text()); data['provenance']['source_sha256']='other'
        launcher.write_json(path,data); report['artifact_sha256'][path.name]=launcher.sha256(path)
    with pytest.raises(ValueError): validate(fixture)


def main_fixture(tmp_path,monkeypatch):
    output=tmp_path/'suite'; output.mkdir()
    monkeypatch.setattr(launcher,'ROOT',tmp_path)
    monkeypatch.setattr(launcher,'OUTPUT',output)
    monkeypatch.setattr(launcher,'state_execution_lock',lambda state:nullcontext())
    monkeypatch.setattr(launcher.benchmark,'validate_output',lambda *args:None)
    monkeypatch.setattr(launcher.benchmark,'runtime_code',lambda:{})
    monkeypatch.setattr(launcher.benchmark,'protected_inventory',lambda:{})
    launcher.write_json(output/'prelaunch-tests.json',{'exit_code':0,'runtime_code_sha256':{}})
    events=[]
    def launch(command,**kwargs):
        count=int(command[command.index('--district-count')+1]); events.append(('launch',count))
        assert kwargs['stdout'] is not None and kwargs['stderr']==launcher.subprocess.STDOUT
        if launcher.os.name=='nt': assert kwargs['creationflags']==launcher.subprocess.CREATE_NO_WINDOW
        def wait():
            events.append(('wait',count)); return 0
        return SimpleNamespace(pid=1000+count,wait=wait)
    monkeypatch.setattr(launcher.subprocess,'Popen',launch)
    def terminal(count,*args):
        assert events[-1]==('wait',count)
        return {'status':'complete','report':'benchmark.json','report_sha256':'saved'}
    monkeypatch.setattr(launcher,'validate_terminal',terminal)
    return output,events


def test_parent_runs_serially_and_refuses_second_launch(tmp_path,monkeypatch):
    output,events=main_fixture(tmp_path,monkeypatch)
    launcher.main()
    assert events==[('launch',1),('wait',1),('launch',2),('wait',2)]
    assert json.loads((output/'run.json').read_text())['status']=='complete'
    with pytest.raises(FileExistsError): launcher.main()
    assert len(events)==4


def test_ambiguous_first_child_stops_before_second(tmp_path,monkeypatch):
    output,events=main_fixture(tmp_path,monkeypatch)
    def ambiguous(*args): raise ValueError('ambiguous terminal')
    monkeypatch.setattr(launcher,'validate_terminal',ambiguous)
    with pytest.raises(ValueError,match='ambiguous terminal'): launcher.main()
    record=json.loads((output/'run.json').read_text())
    assert events==[('launch',1),('wait',1)]
    assert record['status']=='stopped'
    assert record['jobs'][0]['status']=='needs_inspection'
    assert record['jobs'][1]['status']=='pending'


def test_emergency_terminal_manifest_is_saved_but_write_failure_propagates(tmp_path,monkeypatch):
    output,_=main_fixture(tmp_path,monkeypatch)
    original=launcher.write_json
    def final_write_failure(path,value):
        if path.name=='run.json' and value.get('finished_at'):
            raise PermissionError('simulated final manifest sharing error')
        original(path,value)
    monkeypatch.setattr(launcher,'write_json',final_write_failure)
    with pytest.raises(PermissionError,match='final manifest sharing error'): launcher.main()
    emergency=list(output.glob('emergency-*.json'))
    assert len(emergency)==1
    saved=json.loads(emergency[0].read_text())
    assert saved['status']=='complete'
    assert 'sharing error' in saved['manifest_write_error']
