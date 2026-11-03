"""Preservation and independent connectivity invariants for Hawaii policy runs."""
from pathlib import Path

import pytest

from districting.part_connectivity import PartGraph
from scripts.benchmark_hawaii_water import SUITE, audit_plan, validate_output


@pytest.mark.parametrize('relative', ['states/15/districts-2', 'diagnostics/hawaii',
                                      'policies/hawaii-water-v1/states/15',
                                      'policies/island-water-v1/states/44/districts-2'])
def test_historical_outputs_are_not_run_destinations(relative: str) -> None:
    with pytest.raises(ValueError, match='new run below'):
        validate_output((SUITE / relative).resolve())


def test_prior_attempt_cannot_be_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import benchmark_hawaii_water as benchmark
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    output = tmp_path / 'policies/hawaii-water-v1/states/15/districts-4'
    output.mkdir(parents=True)
    (output / 'benchmark.json').write_text('{"status":"failed"}')
    with pytest.raises(ValueError, match='earlier attempts are preserved'):
        validate_output(output.resolve())


def test_island_chain_cannot_borrow_another_districts_link() -> None:
    physical = PartGraph(((), (), (), ()), (0, 1, 2, 3))
    linked = PartGraph(((1,), (0, 2), (1, 3), (2,)), (0, 1, 2, 3))
    invalid = audit_plan([0, 1, 0, 0], [40, 50, 5, 5], ['a', 'b', 'c', 'd'],
                         physical, linked, 2)
    assert not invalid['all_districts_policy_connected']
    assert invalid['policy_part_components'] == [2, 1]
    valid = audit_plan([0, 0, 1, 1], [40, 10, 25, 25], ['a', 'b', 'c', 'd'],
                       physical, linked, 2)
    assert valid['all_districts_policy_connected']
    assert not valid['all_districts_physically_part_connected']
    assert valid['district_populations'] == [50, 50]
