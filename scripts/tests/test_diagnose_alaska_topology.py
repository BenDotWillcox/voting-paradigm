"""Alaska single-group policy is a bounded-search specialization, not a new rule."""
from contextlib import nullcontext

import pytest

from scripts import diagnose_alaska_topology as diagnosis
from scripts.hawaii_population_links import select_population_aware_forest


def _edge(a, b, distance=1.0, identifier=None):
    return {"id": identifier or f"edge-{a}-{b}", "component_ids": [a, b], "distance_m": distance}


@pytest.mark.parametrize("populations,k", [
    ([100], 1),
    ([100], 2),
    ([60, 40], 1),
    ([98, 1, 1], 2),
    ([99, 1, 0], 1),
    ([99, 1, 0, 0], 1),
    ([30, 30, 40, 0], 1),
])
def test_single_group_matches_existing_population_policy(populations, k):
    links = [_edge(a, b, 1 + a * len(populations) + b)
             for a in range(len(populations)) for b in range(a + 1, len(populations))]
    actual = diagnosis.single_group_forest(populations, links, k)
    expected = select_population_aware_forest(populations, links, k)
    assert actual["policy"] == expected["policy"]
    assert actual["eligible_root_component_ids"] == expected["eligible_root_component_ids"]
    assert actual["no_individual_root_fallback"] == expected["no_individual_root_fallback"]
    assert actual["selected_link_ids"] == expected["selected_link_ids"]
    assert actual["selected_total_distance_m"] == expected["selected_total_distance_m"]
    assert actual["population_bound"] == expected["population_bound"]
    assert len(actual["groups"]) == len(expected["groups"]) == 1
    assert actual["groups"][0]["component_ids"] == expected["groups"][0]["component_ids"]
    assert actual["groups"][0]["district_count"] == expected["groups"][0]["district_count"]
    assert actual["is_constructed_plan"] is False


def test_single_component_requires_no_candidate_link():
    actual = diagnosis.single_group_forest([500], [], 1)
    assert actual["selected_link_ids"] == []
    assert actual["selected_total_distance_m"] == 0
    assert actual["groups"] == [{"component_ids": [0], "population": 500, "district_count": 1}]


@pytest.mark.parametrize("populations,k", [([900] + [1] * 9, 2), ([1] * 10, 1)])
def test_more_than_eight_populated_components_do_not_require_enumeration(populations, k):
    links = [_edge(i, i + 1, i + 1) for i in range(len(populations) - 1)]
    actual = diagnosis.single_group_forest(populations, links, k)
    assert actual["selected_link_ids"] == [link["id"] for link in links]
    assert actual["groups"][0]["component_ids"] == list(range(len(populations)))
    assert actual["groups"][0]["population"] == sum(populations)
    assert actual["population_bound"]["deviation_fraction"] == [0, 1]
    assert actual["no_individual_root_fallback"] is (k == 1)


def test_root_eligibility_includes_exact_one_percent_boundary():
    # K2 ideal=50,000; first component is exactly99% of ideal.
    actual = diagnosis.single_group_forest([49500, 30000, 20500], [_edge(0, 1), _edge(1, 2)], 2)
    assert actual["eligible_root_component_ids"] == [0]


def test_multiple_eligible_roots_require_general_search():
    with pytest.raises(ValueError, match="Multiple eligible roots"):
        diagnosis.single_group_forest([50, 50], [_edge(0, 1)], 2)


@pytest.mark.parametrize("links", [
    [_edge(0, 1), _edge(0, 1, 2, "duplicate-pair")],
    [_edge(0, 1), _edge(1, 0, 2, "reversed-pair")],
    [_edge(0, 1, identifier="duplicate-id"), _edge(1, 2, identifier="duplicate-id")],
    [_edge(0, 0)],
    [_edge(0, 3)],
    [_edge(-1, 0)],
    [_edge(0, 1, 0)],
    [_edge(0, 1, -1)],
    [_edge(0, 1, float("nan"))],
    [_edge(0, 1, float("inf"))],
])
def test_invalid_or_duplicate_edges_fail_closed(links):
    with pytest.raises(ValueError, match="Invalid/duplicate candidate"):
        diagnosis.single_group_forest([90, 5, 5], links, 1)


@pytest.mark.parametrize("links", [[], [_edge(0, 1)], [_edge(1, 2)]])
def test_missing_connecting_edges_cannot_drop_an_island(links):
    with pytest.raises(ValueError, match="cannot connect all coverage"):
        diagnosis.single_group_forest([90, 5, 5], links, 1)


def test_reversed_endpoint_order_preserves_existing_tie_breaks():
    links = [_edge(1, 0, identifier="a"), _edge(2, 0, identifier="b"), _edge(1, 2, identifier="c")]
    actual = diagnosis.single_group_forest([98, 1, 1], links, 2)
    expected = select_population_aware_forest([98, 1, 1], links, 2)
    assert actual["selected_link_ids"] == expected["selected_link_ids"]


def test_boolean_population_is_rejected_like_existing_selector():
    with pytest.raises(ValueError):
        diagnosis.single_group_forest([True, 9], [_edge(0, 1)], 1)


def test_boolean_distance_is_rejected_like_existing_selector():
    with pytest.raises(ValueError):
        diagnosis.single_group_forest([1, 9], [_edge(0, 1, True)], 1)


@pytest.mark.parametrize("populations,k", [([],1),([0],1),([-1,2],1),([1.5,2],1),(["1",2],1),([1,2],True),([1,2],1.5),([1,2],0)])
def test_invalid_population_or_count_is_rejected(populations, k):
    with pytest.raises(ValueError, match="Invalid population"):
        diagnosis.single_group_forest(populations, [_edge(0,1)], k)


@pytest.mark.parametrize("link", [
    None, {}, {"id":"edge","component_ids":[0],"distance_m":1},
    {"id":"edge","component_ids":[0,True],"distance_m":1},
    {"id":"edge","component_ids":[0,1.5],"distance_m":1},
    {"id":"edge","component_ids":[0,1],"distance_m":"1"},
    {"id":None,"component_ids":[0,1],"distance_m":1},
])
def test_malformed_edge_is_rejected_before_sorting(link):
    with pytest.raises(ValueError, match="Invalid/duplicate candidate"):
        diagnosis.single_group_forest([1,9], [link], 1)


def test_population_reconciliation_retains_positive_spanning_block_once():
    records=[{"geoid":"a","population":80},{"geoid":"b","population":20}]
    components=[{"population":80,"block_count":1},{"population":0,"block_count":0}]
    spanning=[{"geoid":"b","population":20,"component_ids":[0,1]}]
    audit=diagnosis.source_population_accounting(records,components,spanning)
    assert audit["source_total_population"] == 100
    assert audit["component_attributed_population"] == 80
    assert audit["unattributed_spanning_block_population"] == 20
    assert audit["component_population_totals_complete"] is False
    assert audit["whole_block_population_counted_once"] is True


def test_zero_population_spanning_block_still_blocks_component_allocation():
    audit=diagnosis.source_population_accounting(
        [{"geoid":"a","population":100},{"geoid":"b","population":0}],
        [{"population":100,"block_count":1}],
        [{"geoid":"b","population":0,"component_ids":[0,1]}])
    assert audit["source_total_population"] == 100
    assert audit["component_population_totals_complete"] is False


@pytest.mark.parametrize("component_population,spanning_population", [(79,20),(80,21)])
def test_population_reconciliation_rejects_missing_or_changed_people(component_population,spanning_population):
    with pytest.raises(ValueError):
        diagnosis.source_population_accounting(
            [{"geoid":"a","population":80},{"geoid":"b","population":20}],
            [{"population":component_population,"block_count":1}],
            [{"geoid":"b","population":spanning_population,"component_ids":[0,1]}])


def test_inspection_owns_alaska_state_lock(monkeypatch):
    states = []
    monkeypatch.setattr(diagnosis, "state_execution_lock", lambda state: states.append(state) or nullcontext())
    monkeypatch.setattr(diagnosis, "_run", lambda: {"diagnostic": True})
    assert diagnosis.run() == {"diagnostic": True}
    assert states == ["02"]


def test_existing_diagnosis_is_not_overwritten(tmp_path, monkeypatch):
    existing = tmp_path / "alaska"
    existing.mkdir()
    prior = existing / "diagnosis.json"
    prior.write_bytes(b'{"preserve":"earlier result"}')
    monkeypatch.setattr(diagnosis, "OUTPUT", existing)
    monkeypatch.setattr(diagnosis, "inventory", lambda: pytest.fail("Refuse before any source inspection"))
    with pytest.raises(FileExistsError, match="existing Alaska diagnosis"):
        diagnosis._run()
    assert prior.read_bytes() == b'{"preserve":"earlier result"}'
