"""Selection, accounting and failure reporting without opening real cached plans."""
from copy import deepcopy
import json
from pathlib import Path
import statistics
import sys

import pytest

from apportionment.data.apportionment_2020 import US_2020_KNOWN_APPORTIONMENT
from scripts import finalize_state_block_catalog as catalog
from scripts import final_state_plan_validation as validator


def candidate(fips="01", count=2, path="saved/alabama/benchmark.json"):
    return {"state_fips": fips, "district_count": count, "report_path": path,
            "report_sha256": "a" * 64, "selection_reason": "synthetic test",
            "evidence": []}


@pytest.fixture(scope="module")
def grid():
    return catalog.expected_grid()


def test_exact_apportionment_matches_official_current_house_and_four_anchor_grid(grid):
    assert catalog.exact_apportionment(435) == US_2020_KNOWN_APPORTIONMENT
    assert len(grid) == 181
    assert sum(len(caps) for caps in grid.values()) == 200
    assert [next(k for (f, k), caps in grid.items() if f == "20" and cap in caps)
            for cap in catalog.CAPS] == [4, 5, 6, 9]
    for cap in catalog.CAPS:
        rows = [(f, k) for (f, k), caps in grid.items() if cap in caps]
        assert len(rows) == 50
        assert sum(k for _, k in rows) == cap
    assert all(11037 not in caps for caps in grid.values())


def test_exact_priority_tie_uses_fips_independent_of_dictionary_order(monkeypatch):
    monkeypatch.setattr(catalog, "US_2020_APPORTIONMENT_POPULATIONS", {"02": 100, "01": 100})
    assert catalog.exact_apportionment(3) == {"02": 1, "01": 2}


def test_grid_rejects_disagreement_with_production_scheduler(monkeypatch):
    monkeypatch.setattr(catalog, "apportion_us_2020", lambda cap: {})
    with pytest.raises(ValueError, match="apportionment mismatch"):
        catalog.expected_grid()


def test_selection_uses_exact_grid_and_records_replacement_without_mutating_inputs():
    base = candidate()
    base["house_sizes"] = [11037]
    replacement = candidate(path="corrected/alabama/benchmark.json")
    original = deepcopy([base, replacement])
    rows = catalog.assemble_selection([base], [replacement], {("01", 2): [435, 574]})
    assert rows[0]["supersedes_report_path"] == base["report_path"]
    assert rows[0]["report_path"] == replacement["report_path"]
    assert rows[0]["house_sizes"] == [435, 574]
    assert rows[0]["plan_id"] == "01-2"
    assert [base, replacement] == original


@pytest.mark.parametrize("baseline,overrides,message", [
    ([], [], "Missing accepted"),
    ([candidate(), candidate()], [], "Duplicate selected"),
    ([], [candidate(), candidate()], "Duplicate selected"),
    ([candidate(count=3)], [], "Out-of-scope"),
    ([candidate(fips="02")], [], "Out-of-scope"),
])
def test_missing_duplicate_extra_or_wrong_selection_identity_fails(baseline, overrides, message):
    with pytest.raises(ValueError, match=message):
        catalog.assemble_selection(baseline, overrides, {("01", 2): [435]})


def test_one_report_cannot_supply_two_plan_identities():
    entries = [candidate(), candidate("02", 1)]
    with pytest.raises(ValueError, match="multiple state/count"):
        catalog.assemble_selection(entries, [], {("01", 2): [435], ("02", 1): [435]})


def test_repeated_identical_evidence_hashes_deduplicate_without_mutation():
    record = {"path": "saved/source.json", "sha256": "a" * 64}
    entries = [{"evidence": [dict(record)]}, {"evidence": [dict(record)]}, {}]
    before = deepcopy(entries)
    assert catalog.collect_evidence(entries) == {record["path"]: record["sha256"]}
    assert entries == before


@pytest.mark.parametrize("same_entry", [True, False])
def test_conflicting_evidence_hashes_are_rejected_within_or_across_selected_entries(same_entry):
    a = {"path": "saved/source.json", "sha256": "a" * 64}
    b = {"path": "saved/source.json", "sha256": "b" * 64}
    entries = [{"evidence": [a, b]}] if same_entry else [{"evidence": [a]}, {"evidence": [b]}]
    with pytest.raises(ValueError, match="Conflicting selection evidence hashes"):
        catalog.collect_evidence(entries)


@pytest.mark.parametrize("count", [True, False, 2.0, "2", 0, -1])
def test_selected_count_must_be_positive_exact_integer_even_when_boolean_or_float_matches_grid(count):
    # True == 1 and 2.0 == 2 in Python; dictionary membership alone is insufficient.
    with pytest.raises(ValueError, match="exact valid identity"):
        catalog.assemble_selection([candidate(count=count)], [], {("01", 1): [435], ("01", 2): [574]})


@pytest.mark.parametrize("fips", [1, True, "1", "00", "99", None])
def test_selected_state_must_be_known_exact_string_fips(fips):
    with pytest.raises(ValueError, match="exact valid identity"):
        catalog.assemble_selection([candidate(fips=fips)], [], {("01", 2): [435]})


def test_repository_path_escape_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="escapes repository"):
        catalog.resolve_local("../outside.json")
    assert catalog.resolve_local("inside/report.json") == tmp_path / "inside/report.json"


@pytest.mark.parametrize("relative", [".", "states/54/districts-3", "policies/new", "final-anchors-v0", "final-anchors-v1/nested"])
def test_output_cannot_write_into_historical_or_arbitrary_namespace(tmp_path, monkeypatch, relative):
    monkeypatch.setattr(catalog, "SUITE", tmp_path)
    with pytest.raises(ValueError, match="namespace"):
        catalog.validate_output_path((tmp_path / relative).resolve())


def test_output_refuses_even_an_empty_existing_audit_namespace(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "SUITE", tmp_path)
    output = tmp_path / "final-anchors-v2"
    catalog.validate_output_path(output)
    output.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        catalog.validate_output_path(output)


def metric_row(fips, count, caps, index=1):
    return {"state_fips": fips, "district_count": count, "house_sizes": caps,
            "plan_id": f"{fips}-{count}", "resident_population": 100,
            "block_count": 10, "max_deviation_percent": index / 100,
            "max_deviation_people": index, "national_outline_gzip_bytes": 20,
            "connectivity_policy": "strict_shared_edge", "pipeline_seconds": index,
            "peak_process_working_set_bytes": index * 1000,
            "optimizer": {"unsuccessful_inner_pass_count": 0,
                          "outer_iteration_limit_reached": False}}


def test_aggregate_counts_unique_plans_once_but_anchor_memberships_200_times(grid):
    rows = [metric_row(f, k, caps, i) for i, ((f, k), caps) in enumerate(sorted(grid.items()), 1)]
    result = catalog.aggregate(rows)
    assert result["unique_plans"] == 181
    assert result["state_anchor_combinations"] == 200
    assert result["median_pipeline_seconds"] == statistics.median(range(1, 182))
    assert result["maximum_pipeline_seconds"] == 181
    assert result["maximum_peak_process_working_set_bytes"] == 181000
    for cap in result["anchors"]:
        assert cap["states_validated"] == 50
        assert cap["district_count"] == cap["house_size"]
        assert cap["resident_population"] == 5000
        assert cap["national_outline_gzip_bytes"] == 1000


def test_aggregate_keeps_geographic_policy_and_numerical_flags_separate():
    a = metric_row("01", 2, [435, 574])
    b = metric_row("02", 1, [435, 574], 2)
    b["connectivity_policy"] = "shared_edges_plus_recorded_water_connections"
    b["optimizer"] = {"unsuccessful_inner_pass_count": 3, "outer_iteration_limit_reached": True}
    result = catalog.aggregate([a, b])
    assert result["strict_shared_edge_plans"] == result["recorded_connection_plans"] == 1
    assert result["plans_with_legacy_unsuccessful_inner_passes"] == 1
    assert result["plans_at_outer_iteration_cap"] == 1
    assert result["state_anchor_combinations"] == 4


def test_optimizer_caveats_retain_failed_pass_and_cap_without_claiming_final_failure():
    report = {"status": "complete", "solver": {"centers_converged": False,
              "outer_iteration_limit_reached": True, "outer_iterations": 80},
              "solver_progress": [
                  {"balance_pass": 1, "inner_optimizer": {"success": False, "iterations": 300,
                   "iteration_limit_reached": True, "message": "STOP: LIMIT"}},
                  {"balance_pass": 2, "inner_optimizer": {"success": True, "iterations": 4,
                   "iteration_limit_reached": False}}]}
    result = catalog.optimizer_metrics(report)
    assert result["inner_pass_count"] == 2
    assert result["unsuccessful_inner_pass_count"] == 1
    assert result["inner_iteration_caps"] == 1
    assert result["maximum_inner_iterations"] == 300
    assert result["centers_converged"] is False
    assert report["status"] == "complete"


@pytest.fixture
def normalization_case(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "ROOT", tmp_path)
    monkeypatch.setattr(catalog, "SUITE", tmp_path / "suite")
    monkeypatch.setattr(catalog, "EXPECTED_RESIDENT_POPULATIONS", {"01": 10, "02": 10, "20": 10})
    monkeypatch.setattr(catalog, "EXPECTED_BLOCK_COUNTS", {"01": 4, "02": 4, "20": 4})
    entry = {**candidate(path="suite/saved/benchmark.json"), "plan_id": "01-2", "house_sizes": [435]}
    report = {"status": "complete", "state_fips": "01", "district_count": 2,
              "final_plan": {"district_populations": [4, 6]},
              "maps": {"strict_validation": {"passed": True},
                       "district_outlines": {"national": {"gzip_bytes": 123}, "state": {"gzip_bytes": 456}}},
              "timed_pipeline_wall_seconds": 12, "peak_process_working_set_bytes": 5000}
    return entry, report


def test_normalized_balance_uses_fractional_resident_ideal(normalization_case):
    entry, report = normalization_case
    entry.update(district_count=3, plan_id="01-3")
    report["final_plan"]["district_populations"] = [3, 3, 4]
    row = catalog.normalized_metrics(entry, report, {"status": "validated_saved_plan"})
    assert row["max_deviation_people"] == pytest.approx(2 / 3)
    assert row["max_deviation_percent"] == 20
    assert row["resident_population"] == 10
    assert row["strict_polygon_validation_passed"] is True
    assert row["optimizer"]["centers_converged"] is None


@pytest.mark.parametrize("populations", [None, [10], [4, 5]])
def test_normalized_metrics_reject_missing_wrong_count_or_wrong_total(normalization_case, populations):
    entry, report = normalization_case
    report["final_plan"]["district_populations"] = populations
    with pytest.raises(ValueError):
        catalog.normalized_metrics(entry, report, {})


def test_reused_solver_caveats_survive_correction_only_report(normalization_case):
    entry, report = normalization_case
    entry["numerical_convergence"] = {
        "upstream_solver_reused": True, "inner_pass_count": 81,
        "unsuccessful_inner_passes": [{"pass_number": 1, "success": False}],
        "capped_inner_passes": [1], "max_inner_iterations": 300,
        "centers_converged": False, "outer_iteration_limit_reached": True,
        "outer_iterations": 80, "optimizer_kind": "balanced_power_diagram"}
    row = catalog.normalized_metrics(entry, report, {})
    assert row["optimizer"]["inner_pass_count"] == 81
    assert row["optimizer"]["unsuccessful_inner_pass_count"] == 1
    assert row["optimizer"]["inner_iteration_caps"] == 1
    assert row["optimizer"]["centers_converged"] is False
    assert row["runtime_scope"] == "correction_only_original_solve_reused"
    assert row["pipeline_seconds"] == 12


def test_alaska_distinguishes_physical_from_recorded_connection_connectivity(normalization_case):
    entry, report = normalization_case
    entry.update(state_fips="02", plan_id="02-2")
    report["maps"]["physical_validation"] = {"all_districts_physically_connected": False}
    report["maps"]["connectivity_validation"] = {"passed": True}
    report["maps"]["coordinate_frames"] = {"working": "continuous", "display": "wrapped"}
    report["maps"]["map_payload_summary"] = {"national_gzip_bytes": 123, "state_gzip_bytes": 456}
    row = catalog.normalized_metrics(entry, report, {})
    assert row["strict_polygon_validation_passed"] is False
    assert row["policy_polygon_validation_passed"] is True
    assert row["connectivity_policy"] != "strict_shared_edge"
    assert row["coordinate_handling"]["working"] == "continuous"


def test_kansas_uses_legacy_full_polygon_audit_when_explicit_strict_flag_absent(normalization_case):
    entry, report = normalization_case
    entry.update(state_fips="20", plan_id="20-2")
    report["maps"].pop("strict_validation")
    report["maps"]["quality"] = {"dissolved_geometries_valid": True,
        "districts": {"0": {"polygon_components": 1}, "1": {"polygon_components": 1}}}
    row = catalog.normalized_metrics(entry, report, {})
    assert row["strict_polygon_validation_passed"] is True
    report["maps"]["quality"]["districts"]["1"]["polygon_components"] = 2
    assert catalog.normalized_metrics(entry, report, {})["strict_polygon_validation_passed"] is False


def test_markdown_can_publish_all_failed_inventory_without_fabricated_metrics():
    data = {"status": "validation_failed", "plans": [], "aggregate": catalog.aggregate([]),
            "generated_at": "synthetic", "audit_wall_seconds": 1,
            "errors": [{"plan_id": "01-2", "error": "source checksum mismatch"}]}
    text = catalog.markdown(data)
    assert "Final verification is incomplete" in text
    assert "All four anchors are covered" not in text
    assert "source checksum mismatch" in text
    assert "MISSING" in text


@pytest.fixture
def main_case(tmp_path, monkeypatch):
    root = tmp_path
    suite = root / "suite"
    saved = suite / "states/01/districts-2/benchmark.json"
    saved.parent.mkdir(parents=True)
    report = {"status": "complete", "state_fips": "01", "district_count": 2,
              "final_plan": {"district_populations": [4, 6]},
              "maps": {"strict_validation": {"passed": True}},
              "timed_pipeline_wall_seconds": 1, "peak_process_working_set_bytes": 1000}
    saved.write_text(json.dumps(report), encoding="utf-8")
    entry = candidate(path=saved.relative_to(root).as_posix())
    entry["report_sha256"] = catalog.sha(saved)
    baseline = root / "baseline.json"
    baseline.write_text(json.dumps({"entries": [entry]}), encoding="utf-8")
    policies = root / "policies.json"
    policies.write_text('{"entries": []}', encoding="utf-8")
    (root / "prompts").mkdir()
    monkeypatch.setattr(catalog, "ROOT", root)
    monkeypatch.setattr(catalog, "SUITE", suite)
    monkeypatch.setattr(catalog, "EXPECTED_RESIDENT_POPULATIONS", {"01": 10})
    monkeypatch.setattr(catalog, "EXPECTED_BLOCK_COUNTS", {"01": 4})
    monkeypatch.setattr(catalog, "expected_grid", lambda: {("01", 2): list(catalog.CAPS)})
    monkeypatch.setattr(catalog, "write_page", lambda output: (output / "index.html").write_text("synthetic"))
    output = suite / "final-anchors-v1"
    monkeypatch.setattr(sys, "argv", ["catalog", "--baseline", str(baseline), "--policies", str(policies), "--output", str(output)])
    return saved, entry, baseline, policies, output


def test_main_preserves_sources_and_passes_expected_identity_to_validator(main_case, monkeypatch):
    saved, entry, baseline, policies, output = main_case
    snapshots = {p: p.read_bytes() for p in (saved, baseline, policies)}
    calls = []
    def verify(path, **kwargs):
        calls.append((path, kwargs))
        return {"status": "validated_saved_plan"}
    monkeypatch.setattr(validator, "validate_plan", verify)
    catalog.main()
    data = catalog.read(output / "catalog.json")
    assert data["status"] == "complete"
    assert data["aggregate"]["unique_plans"] == 1
    assert data["aggregate"]["state_anchor_combinations"] == 4
    assert calls[0][0] == saved
    assert calls[0][1]["expected_state_fips"] == "01"
    assert calls[0][1]["expected_district_count"] == 2
    assert calls[0][1]["expected_report_sha256"] == entry["report_sha256"]
    assert all(p.read_bytes() == b for p, b in snapshots.items())


@pytest.mark.parametrize("message", ["report identity mismatch", "failed saved status", "source checksum mismatch", "disconnected full polygons"])
def test_main_records_validation_failure_and_never_counts_it_as_accepted(main_case, monkeypatch, message):
    saved, _, _, _, output = main_case
    before = saved.read_bytes()
    def fail(*args, **kwargs):
        raise ValueError(message)
    monkeypatch.setattr(validator, "validate_plan", fail)
    catalog.main()
    data = catalog.read(output / "catalog.json")
    assert data["status"] == "validation_failed"
    assert data["plans"] == []
    assert data["aggregate"]["unique_plans"] == 0
    assert message in data["errors"][0]["error"]
    assert (output / "validation/01-2.failed.json").is_file()
    assert not (output / "validation/01-2.json").exists()
    assert catalog.read(output / "progress.json")["status"] == "validation_failed"
    assert "Final verification is incomplete" in (output / "report.md").read_text()
    assert saved.read_bytes() == before


def test_changed_report_hash_fails_before_validation(main_case, monkeypatch):
    saved, _, _, _, output = main_case
    saved.write_text(saved.read_text() + "\n", encoding="utf-8")
    monkeypatch.setattr(validator, "validate_plan", lambda *a, **kw: pytest.fail("must not validate changed selection"))
    catalog.main()
    data = catalog.read(output / "catalog.json")
    assert data["status"] == "validation_failed"
    assert "hash changed" in data["errors"][0]["error"]


def test_changed_report_during_validation_cannot_be_published(main_case, monkeypatch):
    saved, _, _, _, output = main_case
    def mutate(*args, **kwargs):
        saved.write_text(saved.read_text() + "\n", encoding="utf-8")
        return {"status": "validated_saved_plan"}
    monkeypatch.setattr(validator, "validate_plan", mutate)
    catalog.main()
    data = catalog.read(output / "catalog.json")
    assert data["status"] == "validation_failed"
    assert "changed during validation" in data["errors"][0]["error"]


def test_changed_evidence_refuses_publication_before_creating_output(main_case, monkeypatch):
    _, entry, baseline, _, output = main_case
    entry["evidence"] = [{"path": entry["report_path"], "sha256": "0" * 64}]
    baseline.write_text(json.dumps({"entries": [entry]}), encoding="utf-8")
    monkeypatch.setattr(validator, "validate_plan", lambda *a, **kw: pytest.fail("evidence failed"))
    with pytest.raises(ValueError, match="evidence hash mismatch"):
        catalog.main()
    assert not output.exists()
