"""Target-count population policy must be checked without rewriting K52 evidence."""
from __future__ import annotations

import copy
import json

import pytest
from shapely.geometry import box

from districting.part_connectivity import PartGraph
from scripts import california_anchor_links as wrapper
from scripts import california_recorded_links as base
from scripts.hawaii_population_links import select_population_aware_forest
from scripts.tests import test_california_recorded_links as frozen_fixture


def _fixture(tmp_path, monkeypatch):
    """Expand the frozen real-shapefile fixture to permit K120, keeping six gaps."""
    source, old_geoids, old_pops, _, diagnostic, old_geoms = frozen_fixture._fixture(tmp_path, monkeypatch)
    main_count, extra = 120, 68
    xs = [-121 + i * .01 for i in range(main_count + 1)]
    geoids = (*old_geoids[:52], *(f"06001000100{i:04d}" for i in range(1000, 1000 + extra)), *old_geoids[52:])
    pops = (100,) * main_count + old_pops[52:]
    geoms = [*old_geoms[:52], *(box(xs[i], 36, xs[i + 1], 36.01) for i in range(52, main_count)), *old_geoms[52:]]
    frozen_fixture._write_source(source, geoms, geoids, pops)
    rows = [tuple(j for j in (i - 1, i + 1) if 0 <= j < main_count) for i in range(main_count)] + [()] * 6
    graph = PartGraph(tuple(rows), tuple(range(main_count + 6)))
    data = json.loads((diagnostic / "diagnosis.json").read_text())
    for candidate in data["links"]:
        for endpoint in candidate["endpoints"]:
            if endpoint["part_node"] >= 52:
                endpoint["part_node"] += extra
    data.update(part_count=126, block_count=126, total_population=sum(pops))
    data["components"][0].update(population=12000, part_count=120, block_count=120)
    data["source"]["extracted_file_sha256"] = frozen_fixture._source_hashes(source)
    (diagnostic / "candidate-links.json").write_text(json.dumps(data["links"]))
    _write_plans(data)
    (diagnostic / "diagnosis.json").write_text(json.dumps(data))
    frozen_fixture._repin(diagnostic, monkeypatch)
    return source, geoids, pops, graph, diagnostic, geoms


def _write_plans(data):
    populations = [row["population"] for row in data["components"]]
    candidates = [row for row in data["links"] if row["eligible_positive_gap"]]
    data["plans"] = []
    for k in (52, 69, 83, 120):
        selection = select_population_aware_forest(populations, candidates, k, population_tolerance=.01)
        data["plans"].append({"district_count": k, "actual_district_plan_generated": False,
                              "selected_link_ids": selection["selected_link_ids"], "augmented_component_count": len(selection["groups"]),
                              "policy": selection, "policy_population_bound": selection["population_bound"]})


def _build(args, k):
    return wrapper.build_california_anchor_connections(*args[:4], district_count=k, diagnostic_dir=args[4])


@pytest.mark.parametrize("k", [69, 83, 120])
def test_actual_target_threshold_and_quota_with_identical_links_and_source(tmp_path, monkeypatch, k):
    args = _fixture(tmp_path, monkeypatch)
    base_graph, base_records, base_audit = base.build_california_connections(*args[:4], district_count=52, diagnostic_dir=args[4])
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    graph_before = args[3].adjacency
    augmented, records, audit = _build(args, k)
    assert augmented == base_graph
    assert args[3].adjacency == graph_before
    assert json.dumps(records, sort_keys=True, separators=(",", ":")) == json.dumps(base_records, sort_keys=True, separators=(",", ":"))
    assert audit["district_count"] == k
    assert audit["groups"][0]["district_count"] == k
    selection = audit["population_selection"]
    assert selection["district_count"] == k
    assert selection["ideal_population"] == sum(args[2]) / k
    assert selection["minimum_root_population"] == pytest.approx(.99 * sum(args[2]) / k)
    assert selection["minimum_root_population"] != base_audit["population_selection"]["minimum_root_population"]
    assert selection["eligible_root_component_ids"] == [0]
    assert selection["selected_link_ids"] == list(base.AUTHORIZED_CANDIDATE_IDS)
    assert audit["provenance"] == base_audit["provenance"]
    assert audit["wrapper_provenance"]["target_district_count"] == k
    assert audit["wrapper_provenance"]["base_builder_sha256"] == wrapper.PINNED_BASE_MODULE_SHA256
    assert audit["base_verification_district_count"] == 52
    assert audit["connection_records_reused_unchanged"] is True
    assert audit["elapsed_seconds"] >= audit["base_verification_elapsed_seconds"]
    assert before == {path: path.read_bytes() for path in before}


def test_base_verification_count_is_explicit_and_returned_objects_are_not_mutated(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    original = base.build_california_connections
    saved = {}
    def observe(*a, **kw):
        assert kw["district_count"] == 52
        result = original(*a, **kw)
        saved["result"] = result
        saved["before"] = copy.deepcopy(result[1:])
        return result
    monkeypatch.setattr(base, "build_california_connections", observe)
    graph, records, audit = _build(args, 83)
    assert graph is saved["result"][0]
    assert records is saved["result"][1]
    assert saved["result"][1:] == saved["before"]
    assert audit is not saved["result"][2]


@pytest.mark.parametrize("k", [True, False, 52, 68, 84, 1000, 11037, 69.0])
def test_unsupported_target_count_fails_before_base_verification(tmp_path, monkeypatch, k):
    args = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(base, "build_california_connections", lambda *a, **kw: pytest.fail("Base verification must not run."))
    with pytest.raises(ValueError, match="69, 83, and 120 only"):
        _build(args, k)


def test_target_requires_enough_whole_blocks_before_base_verification(tmp_path, monkeypatch):
    args = frozen_fixture._fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(base, "build_california_connections", lambda *a, **kw: pytest.fail("Base verification must not run."))
    with pytest.raises(ValueError, match="at least one whole block per district"):
        _build(args, 69)


def test_changed_frozen_adapter_is_rejected(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(wrapper, "PINNED_BASE_MODULE_SHA256", "0" * 64)
    monkeypatch.setattr(base, "build_california_connections", lambda *a, **kw: pytest.fail("Base verification must not run."))
    with pytest.raises(ValueError, match="frozen California K52 adapter changed"):
        _build(args, 69)


def test_base_hash_is_checked_again_after_full_verification(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    original = base.build_california_connections
    def changed_during_base(*a, **kw):
        result = original(*a, **kw)
        monkeypatch.setattr(wrapper, "PINNED_BASE_MODULE_SHA256", "0" * 64)
        return result
    monkeypatch.setattr(base, "build_california_connections", changed_during_base)
    with pytest.raises(ValueError, match="frozen California K52 adapter changed"):
        _build(args, 69)


@pytest.mark.parametrize("change", ["missing", "duplicate", "group_quota", "threshold", "edges"])
def test_target_selection_must_match_its_own_pinned_plan(tmp_path, monkeypatch, change):
    args = _fixture(tmp_path, monkeypatch)
    path = args[4] / "diagnosis.json"
    data = json.loads(path.read_text())
    target = next(row for row in data["plans"] if row["district_count"] == 83)
    if change == "missing":
        data["plans"].remove(target)
    elif change == "duplicate":
        data["plans"].append(copy.deepcopy(target))
    elif change == "group_quota":
        target["policy"]["groups"][0]["district_count"] = 52
    elif change == "threshold":
        target["policy"]["minimum_root_population"] += 1
    else:
        target["selected_link_ids"].pop()
    path.write_text(json.dumps(data))
    frozen_fixture._repin(args[4], monkeypatch)
    with pytest.raises(ValueError, match="pinned diagnosis"):
        _build(args, 83)


def test_island_that_becomes_a_root_at_higher_k_is_not_silently_attached(tmp_path, monkeypatch):
    args = list(_fixture(tmp_path, monkeypatch))
    # 150 residents is below the K52 root threshold but above the K120 threshold.
    # The K52 adapter accepts its original one-root forest; the target wrapper must not.
    pops = list(args[2])
    pops[121] = 150
    args[2] = tuple(pops)
    frozen_fixture._write_source(args[0], args[5], args[1], args[2])
    path = args[4] / "diagnosis.json"
    data = json.loads(path.read_text())
    data["source"]["extracted_file_sha256"] = frozen_fixture._source_hashes(args[0])
    data["components"][2]["population"] = 150
    data["total_population"] = sum(pops)
    _write_plans(data)
    path.write_text(json.dumps(data))
    frozen_fixture._repin(args[4], monkeypatch)
    with pytest.raises(ValueError, match="mainland root"):
        _build(args, 120)


@pytest.mark.parametrize("change", ["edges", "root", "groups"])
def test_unexpected_target_selector_result_is_rejected(tmp_path, monkeypatch, change):
    args = _fixture(tmp_path, monkeypatch)
    original = wrapper.select_population_aware_forest
    def changed_selector(*a, **kw):
        result = original(*a, **kw)
        if change == "edges":
            result["selected_link_ids"].reverse()
        elif change == "root":
            result["eligible_root_component_ids"] = [1]
        else:
            result["groups"].append(copy.deepcopy(result["groups"][0]))
        return result
    monkeypatch.setattr(wrapper, "select_population_aware_forest", changed_selector)
    with pytest.raises(ValueError, match="Target-count selection changed"):
        _build(args, 69)


@pytest.mark.parametrize("change", ["extra_edge", "record_endpoint", "record_kind", "base_count"])
def test_unexpected_base_result_does_not_escape_reuse_checks(tmp_path, monkeypatch, change):
    args = _fixture(tmp_path, monkeypatch)
    original = base.build_california_connections
    def changed_base(*a, **kw):
        graph, records, audit = original(*a, **kw)
        if change == "extra_edge":
            rows = [set(row) for row in graph.adjacency]
            rows[0].add(2)
            rows[2].add(0)
            graph = PartGraph(tuple(tuple(sorted(row)) for row in rows), graph.part_to_unit)
        elif change == "record_endpoint":
            records[0]["endpoints"][0]["part_node"] = 1
        elif change == "record_kind":
            records[0]["kind"] = "recorded-exclave-connection"
        else:
            audit["district_count"] = 69
        return graph, records, audit
    monkeypatch.setattr(base, "build_california_connections", changed_base)
    with pytest.raises(ValueError, match="authorized|candidate|source verification"):
        _build(args, 69)


def test_diagnostic_change_during_base_call_is_detected(tmp_path, monkeypatch):
    args = _fixture(tmp_path, monkeypatch)
    original = base.build_california_connections
    def changed_after_verification(*a, **kw):
        result = original(*a, **kw)
        with (args[4] / "diagnosis.json").open("a") as stream:
            stream.write("\n")
        return result
    monkeypatch.setattr(base, "build_california_connections", changed_after_verification)
    with pytest.raises(ValueError, match="evidence changed between"):
        _build(args, 69)
