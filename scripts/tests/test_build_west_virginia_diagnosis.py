"""The viewer must not promote provisional or inconsistent probe evidence."""
from copy import deepcopy

import pytest

from scripts import build_west_virginia_diagnosis as viewer
from scripts.build_west_virginia_diagnosis import validate_diagnosis


def metrics(populations):
    total = sum(populations)
    error = max(abs(3 * p - total) for p in populations) / 3
    return {
        "populations": populations,
        "max_deviation_people": error,
        "max_deviation_percent": error / (total / 3) * 100,
    }


@pytest.fixture
def evidence():
    stage = {**metrics([100, 90, 110]), "components": [1, 1, 1],
             "strict_polygon_validation_passed": True, "accepted_map": False}
    stages = {name: deepcopy(stage) for name in ("initial", "repaired", "original", "probe")}
    stages["initial"].update(components=[2, 1, 1], strict_polygon_validation_passed=False)
    stages["original"]["accepted_map"] = True
    stages["probe"].update(metrics([100, 91, 109]))
    return {
        "status": "diagnosis_complete", "diagnostic_only": True,
        "historical_preservation": {"unchanged": True}, "stages": stages,
        "trace": [{"moves": i, **metrics([100, 90, 110])} for i in range(1001)]
                 + [{"moves": 1001, **metrics([100, 91, 109])}],
        "probe": {"accepted_map": False, "solver_rerun": False, "additional_moves": 1,
                  "additional_move_limit": 100, "cumulative_moves": 1001,
                  "strict_polygon_validation_passed": True, "elapsed_seconds": 2.5,
                  "guard_calls": 2, "guard_failed_calls": 1, "guard_wall_seconds": 1.0},
    }


def test_independent_objective_derived_from_populations(evidence):
    trace = validate_diagnosis(evidence, 300)
    assert trace[0]["squared_deviation_people"] == 200
    assert trace[-1]["squared_deviation_people"] == 162
    assert "squared_deviation_people" not in evidence["trace"][0]
    assert evidence["stages"]["probe"]["accepted_map"] is False


@pytest.mark.parametrize("status", ["running", "failed_diagnosis", "complete"])
def test_nonterminal_or_wrong_result_cannot_be_rendered(evidence, status):
    evidence["status"] = status
    with pytest.raises(ValueError, match="completed diagnostic"):
        validate_diagnosis(evidence, 300)


@pytest.mark.parametrize("where", ["probe", "stage"])
def test_probe_cannot_be_promoted_to_accepted_map(evidence, where):
    target = evidence["probe"] if where == "probe" else evidence["stages"]["probe"]
    target["accepted_map"] = True
    with pytest.raises(ValueError, match="diagnostic"):
        validate_diagnosis(evidence, 300)


def test_provisional_polygon_result_is_not_assumed_success(evidence):
    evidence["probe"]["strict_polygon_validation_passed"] = False
    with pytest.raises(ValueError, match="full strict polygon audit"):
        validate_diagnosis(evidence, 300)


def test_diagnostic_intermediate_may_show_a_failed_polygon_audit(evidence):
    evidence["stages"]["repaired"].update(
        strict_polygon_validation_passed=False, polygons_valid=False,
        polygon_audit_note="Intermediate graph connectivity is not a geometry certificate.",
    )
    validate_diagnosis(evidence, 300)
    assert evidence["stages"]["repaired"]["accepted_map"] is False


@pytest.mark.parametrize("name", ["original", "probe"])
def test_final_or_probe_polygon_failure_blocks_publication(evidence, name):
    evidence["stages"][name]["strict_polygon_validation_passed"] = False
    with pytest.raises(ValueError, match="endpoints require full strict polygon audits"):
        validate_diagnosis(evidence, 300)


@pytest.mark.parametrize("field", ["elapsed_seconds", "guard_calls", "guard_failed_calls", "guard_wall_seconds"])
def test_negative_profile_values_rejected(evidence, field):
    evidence["probe"][field] = -1
    with pytest.raises(ValueError, match="Invalid probe"):
        validate_diagnosis(evidence, 300)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), 0])
def test_inconsistent_or_nonfinite_population_metric_rejected(evidence, value):
    evidence["trace"][1001]["max_deviation_people"] = value
    with pytest.raises(ValueError, match="Inconsistent max_deviation_people"):
        validate_diagnosis(evidence, 300)


def test_missing_trace_move_rejected(evidence):
    del evidence["trace"][500]
    with pytest.raises(ValueError, match="complete recorded-move trace"):
        validate_diagnosis(evidence, 300)


def test_population_total_and_preservation_are_required(evidence):
    evidence["historical_preservation"]["unchanged"] = False
    with pytest.raises(ValueError, match="Historical preservation"):
        validate_diagnosis(evidence, 300)
    evidence["historical_preservation"]["unchanged"] = True
    evidence["stages"]["probe"]["populations"] = [100, -1, 201]
    with pytest.raises(ValueError, match="Invalid stage/trace populations"):
        validate_diagnosis(evidence, 300)


@pytest.mark.parametrize("status,passed", [("failed", True), ("complete", False)])
def test_failed_historical_map_is_not_labelled_valid(monkeypatch, status, passed):
    monkeypatch.setattr(viewer, "load", lambda _: {
        "status": status, "maps": {"strict_validation": {"passed": passed}},
    })
    with pytest.raises(ValueError, match="not a validated complete map"):
        viewer.saved_context({})
