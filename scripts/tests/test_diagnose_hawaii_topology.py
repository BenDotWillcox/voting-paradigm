import math

import pytest

from scripts.diagnose_hawaii_topology import EARTH_RADIUS_M, great_circle_m, population_allocation_bound, rooted_forest


def test_great_circle_handles_antimeridian_and_identical_points():
    assert great_circle_m([179,0],[-179,0]) == pytest.approx(EARTH_RADIUS_M*math.radians(2))
    assert great_circle_m([-157,21],[-157,21]) == 0


def test_near_equal_groups_need_integer_seats():
    result = population_allocation_bound([680,320],3)
    assert result['seat_counts'] == [2,1]
    assert result['best_max_deviation_pct'] == pytest.approx(4)
    assert result['within_one_percent_necessary_test'] is False


def test_one_group_bound_zero_does_not_claim_achieved_plan():
    result = population_allocation_bound([1_455_271],4)
    assert result['seat_counts'] == [4]
    assert result['best_max_deviation_pct'] == 0
    assert result['is_constructed_plan'] is False


def test_too_many_groups_and_zero_population_coverage():
    assert population_allocation_bound([100,0],1)['feasible_seat_allocation'] is False
    assert population_allocation_bound([100,0],2)['best_max_deviation_pct'] == 100


def test_root_forest_allows_small_island_chain_but_no_root_merger():
    links = [{'id':name,'component_ids':pair,'distance_m':distance} for name,pair,distance in
             [('roots',[0,1],1),('chain',[2,3],2),('attach',[1,3],3),('other',[0,2],4)]]
    result = rooted_forest([1000,500,20,10],links,100)
    assert result['root_component_ids'] == [0,1]
    assert result['selected_link_ids'] == ['chain','attach']
    assert result['groups'] == [{'root_component_id':0,'component_ids':[0],'population':1000},
                                {'root_component_id':1,'component_ids':[1,2,3],'population':530}]


def test_policy_rejects_no_eligible_root():
    with pytest.raises(ValueError, match='No eligible'):
        rooted_forest([50,50],[],100)


def test_no_zero_gap_connections():
    with pytest.raises(ValueError, match='cannot reach'):
        rooted_forest([100,1],[{'id':'corner','component_ids':[0,1],'distance_m':0}],50)
