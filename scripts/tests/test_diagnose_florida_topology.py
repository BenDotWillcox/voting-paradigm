"""Keep a Florida topology inspection isolated from preserved evidence."""
from contextlib import nullcontext
import json

import pytest

from scripts import diagnose_florida_topology as diagnosis


def test_inspection_owns_the_florida_state_lock(monkeypatch):
    states = []
    monkeypatch.setattr(diagnosis, 'state_execution_lock', lambda state: states.append(state) or nullcontext())
    monkeypatch.setattr(diagnosis, '_run_locked', lambda: {'diagnostic': True})
    assert diagnosis.run() == {'diagnostic': True}
    assert states == ['12']


@pytest.mark.parametrize('artifact', ('diagnosis.json', 'preserved-file-inventory.json'))
def test_completed_and_partial_attempts_cannot_be_overwritten(artifact, tmp_path, monkeypatch):
    monkeypatch.setattr(diagnosis, 'OUTPUT', tmp_path)
    monkeypatch.setattr(diagnosis, 'inventory', lambda: {})
    prior = b'{"original":"retain even if prior diagnosis failed"}'
    (tmp_path / artifact).write_bytes(prior)
    monkeypatch.setattr(diagnosis, 'prepare_source', lambda *args: pytest.fail('No source preparation after duplicate refusal'))
    with pytest.raises(FileExistsError, match='earlier diagnostic attempt'):
        diagnosis._run_locked()
    assert (tmp_path / artifact).read_bytes() == prior


def test_inventory_protects_all_strict_files_and_excludes_new_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnosis, 'ROOT', tmp_path)
    suite = tmp_path / 'suite'
    monkeypatch.setattr(diagnosis, 'SUITE', suite)
    original_paths = [suite / 'suite.json', suite / 'states/12/districts-28/benchmark.json',
        suite / 'states/12/districts-28/progress.json', suite / 'states/12/original.log',
        tmp_path / '.cache/state-block-benchmark/source/12/tl_2020_12_tabblock20.zip']
    for path in original_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'original_path': str(path)}))
    fresh = suite / 'diagnostics/florida/diagnosis.json'
    fresh.parent.mkdir(parents=True)
    fresh.write_text('new diagnostic')
    inventory = diagnosis.inventory()
    assert set(inventory) == {path.relative_to(tmp_path).as_posix() for path in original_paths}
    fresh.write_text('new evidence updates')
    assert diagnosis.inventory() == inventory
    original_paths[2].write_text('unexpected old evidence change')
    assert diagnosis.inventory() != inventory


def test_missing_original_report_is_not_silently_omitted(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnosis, 'ROOT', tmp_path)
    monkeypatch.setattr(diagnosis, 'SUITE', tmp_path / 'suite')
    with pytest.raises(ValueError, match='Required Florida strict evidence'):
        diagnosis.inventory()
