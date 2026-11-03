"""The policy audit must never imply synthetic links are physical adjacency."""
from pathlib import Path

import pytest

from districting.part_connectivity import PartGraph
from scripts.benchmark_rhode_island_water import SUITE, audit_plan, validate_output


def test_water_link_keeps_physical_and_policy_connectivity_distinct() -> None:
    physical = PartGraph(((1,), (0,), ()), (0, 1, 2))
    augmented = PartGraph(((1,), (0, 2), (1,)), (0, 1, 2))
    result = audit_plan([0, 0, 0], [50, 40, 10], ['a', 'b', 'c'], physical, augmented, 1)
    assert result['physical_part_components'] == [2]
    assert result['all_districts_physically_part_connected'] is False
    assert result['all_districts_shared_edge_connected'] is False
    assert result['policy_part_components'] == [1]
    assert result['all_districts_policy_connected'] is True
    assert result['district_populations'] == [100]


def test_water_connection_cannot_traverse_a_different_district() -> None:
    physical = PartGraph(((), (), ()), (0, 1, 2))
    augmented = PartGraph(((1,), (0, 2), (1,)), (0, 1, 2))
    result = audit_plan([0, 1, 0], [50, 40, 10], ['a', 'b', 'c'], physical, augmented, 2)
    assert result['policy_part_components'] == [2, 1]
    assert result['all_districts_policy_connected'] is False


@pytest.mark.parametrize('relative', ['states/44/districts-2', 'diagnostics/rhode-island',
                                      'policies/island-water-v1/states/44'])
def test_output_guard_protects_historical_results(relative: str) -> None:
    with pytest.raises(ValueError, match='new run below'):
        validate_output((SUITE / relative).resolve())


def test_output_guard_refuses_reusing_an_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import benchmark_rhode_island_water as benchmark
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    output = tmp_path / 'policies/island-water-v1/states/44/districts-2'
    output.mkdir(parents=True)
    (output / 'benchmark.json').write_text('{"status":"failed"}')
    with pytest.raises(ValueError, match='earlier attempts are preserved'):
        validate_output(output.resolve())
