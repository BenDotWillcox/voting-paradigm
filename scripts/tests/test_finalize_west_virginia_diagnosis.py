"""Independent polygon acceptance for an already saved WV diagnostic probe."""
import pytest
import shapely
from shapely.geometry import Polygon, box

from scripts import finalize_west_virginia_diagnosis as finalizer


def connected_fixture():
    geometries = [box(i, 0, i + 1, 1) for i in range(3)]
    return geometries, [0, 1, 2], shapely.union_all(geometries)


def fragmented_fixture():
    geometries = [box(i, 0, i + 1, 1) for i in range(5)]
    return geometries, [0, 1, 0, 2, 2], shapely.union_all(geometries)


def test_connected_stage_passes_independent_strict_geometry_and_graph_checks():
    geometries, labels, source = connected_fixture()
    before = [g.wkb for g in geometries]
    full, audit = finalizer.audit_stage(geometries, labels, [1, 1, 1], source, initial=False)
    assert len(full) == 3
    assert audit['polygon_components'] == [1, 1, 1]
    assert audit['strict_polygon_validation_passed'] is True
    assert audit['graph_polygon_component_counts_agree'] is True
    assert audit['source_coverage_preserved_exactly'] is True
    assert audit['district_coverage_valid'] is True
    assert [g.wkb for g in geometries] == before
    assert labels == [0, 1, 2]


def test_initial_fragmentation_is_recorded_without_presenting_a_valid_plan():
    geometries, labels, source = fragmented_fixture()
    full, audit = finalizer.audit_stage(geometries, labels, [2, 1, 1], source, initial=True)
    assert full[0].geom_type == 'MultiPolygon'
    assert audit['polygon_components'] == [2, 1, 1]
    assert audit['strict_polygon_validation_passed'] is False
    assert audit['polygons_valid'] is True
    assert audit['graph_polygon_component_counts_agree'] is True


def test_initial_graph_polygon_discrepancy_remains_explicit():
    geometries, labels, source = fragmented_fixture()
    _, audit = finalizer.audit_stage(geometries, labels, [3, 1, 1], source, initial=True)
    assert audit['polygon_components'] == [2, 1, 1]
    assert audit['graph_polygon_component_counts_agree'] is False
    assert audit['strict_polygon_validation_passed'] is False


def test_final_stage_rejects_disconnected_polygons_even_if_graph_claims_connected():
    geometries, labels, source = fragmented_fixture()
    with pytest.raises(ValueError, match='strict connectivity'):
        finalizer.audit_stage(geometries, labels, [1, 1, 1], source, initial=False)


def test_final_stage_rejects_disconnected_graph_even_if_polygons_are_connected():
    geometries, labels, source = connected_fixture()
    with pytest.raises(ValueError, match='strict connectivity'):
        finalizer.audit_stage(geometries, labels, [2, 1, 1], source, initial=False)


@pytest.mark.parametrize('initial', [False, True])
def test_source_coverage_mismatch_is_rejected_for_every_stage(initial):
    geometries, labels, _ = connected_fixture()
    with pytest.raises(ValueError, match='exactly preserve source coverage'):
        finalizer.audit_stage(geometries, labels, [1, 1, 1], box(0, 0, 4, 1), initial=initial)


def test_missing_district_rejects_empty_geometry():
    geometries, _, source = connected_fixture()
    with pytest.raises(ValueError, match='unsimplified geometry validity'):
        finalizer.audit_stage(geometries, [0, 0, 1], [1, 1, 0], source, initial=False)


def test_invalid_fast_union_is_diagnostic_only_when_robust_union_passes(monkeypatch):
    geometries, labels, source = connected_fixture()
    bowtie = Polygon([(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)])
    assert not bowtie.is_valid
    monkeypatch.setattr(finalizer.shapely, 'coverage_union_all', lambda members: bowtie)
    _, audit = finalizer.audit_stage(geometries, labels, [1, 1, 1], source, initial=False)
    assert audit['strict_polygon_validation_passed'] is True
    assert all(item['valid'] is False for item in audit['coverage_union_diagnostic'])
    assert all('Self-intersection' in item['validity_reason']
               for item in audit['coverage_union_diagnostic'])


@pytest.mark.parametrize('artifact', ['diagnosis-attempt-1.json', 'finalization-admitted.json'])
def test_existing_finalization_attempt_is_refused_and_preserved(tmp_path, monkeypatch, artifact):
    monkeypatch.setattr(finalizer.d, 'OUTPUT', tmp_path)
    saved = b'{"original": "preserve partial and terminal attempts"}'
    (tmp_path / artifact).write_bytes(saved)
    monkeypatch.setattr(finalizer.d, 'read', lambda *args: pytest.fail('No reads/reruns after refusal.'))
    monkeypatch.setattr(finalizer, 'state_execution_lock',
                        lambda *args: pytest.fail('No launch after refusal.'))
    with pytest.raises(FileExistsError, match='finalization attempt already exists'):
        finalizer.main()
    assert (tmp_path / artifact).read_bytes() == saved


def test_unrecognized_failure_cannot_be_relabelled_as_the_known_audit_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(finalizer.d, 'OUTPUT', tmp_path)
    monkeypatch.setattr(finalizer.d, 'read', lambda *args: {
        'status': 'failed_diagnosis', 'error': 'ValueError: Probe graph connectivity failed.',
    })
    monkeypatch.setattr(finalizer, 'state_execution_lock',
                        lambda *args: pytest.fail('Unknown failure must not be finalized.'))
    with pytest.raises(ValueError, match='Only the known initial-stage audit failure'):
        finalizer.main()
    assert not list(tmp_path.iterdir())

