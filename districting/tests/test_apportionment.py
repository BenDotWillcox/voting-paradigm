"""
Tests for Method of Equal Proportions apportionment.

The headline test is `test_2020_apportionment_reproduces_actual_outcome`:
running our algorithm on the 2020 census apportionment populations with
cap=435 must reproduce the seat distribution that the US Census Bureau
actually published. If that fails, the algorithm is wrong.
"""

from __future__ import annotations

import math

import pytest

from districting import (
    InvalidApportionmentError,
    US_2020_APPORTIONMENT_POPULATIONS,
    US_2020_KNOWN_APPORTIONMENT,
    apportion,
    apportion_us_2020,
    priority_value,
)


# ----------------------------------------------------------------------
# The headline regression test
# ----------------------------------------------------------------------


class TestRegression2020Apportionment:
    """The defining acceptance test for step 1."""

    def test_2020_apportionment_reproduces_actual_outcome(self):
        """
        Running our algorithm on 2020 populations at cap=435 must produce
        the actual 2020 apportionment, state by state.
        """
        result = apportion_us_2020(total_seats=435)
        assert result == US_2020_KNOWN_APPORTIONMENT

    def test_2020_total_population_known_value(self):
        """Sanity check on the population data file itself."""
        from districting import US_2020_TOTAL_APPORTIONMENT_POPULATION

        # Census Bureau's published total for the 50-state apportionment
        # population. If this drifts, our population data has been edited.
        assert US_2020_TOTAL_APPORTIONMENT_POPULATION == 331_108_434

    def test_2020_known_apportionment_sums_to_435(self):
        """Sanity check on the regression target itself."""
        assert sum(US_2020_KNOWN_APPORTIONMENT.values()) == 435


# ----------------------------------------------------------------------
# Core invariants
# ----------------------------------------------------------------------


class TestInvariants:
    def test_seats_sum_to_total(self):
        """Sum of seats equals the requested total, for any valid cap."""
        for cap in [50, 100, 435, 575, 692, 1000, 5000, 11037]:
            result = apportion_us_2020(total_seats=cap)
            assert sum(result.values()) == cap, f"Failed at cap={cap}"

    def test_every_state_gets_at_least_one_seat(self):
        """Constitutional minimum is honored at all valid caps."""
        for cap in [50, 100, 435, 11037]:
            result = apportion_us_2020(total_seats=cap)
            for fips, seats in result.items():
                assert seats >= 1, f"State {fips} got {seats} seats at cap={cap}"

    def test_result_covers_every_input_state(self):
        """Output keys exactly match input keys."""
        result = apportion_us_2020(total_seats=435)
        assert set(result.keys()) == set(US_2020_APPORTIONMENT_POPULATIONS.keys())

    def test_input_dict_not_mutated(self):
        """`apportion` must not mutate the caller's input mapping."""
        snapshot = dict(US_2020_APPORTIONMENT_POPULATIONS)
        apportion(US_2020_APPORTIONMENT_POPULATIONS, total_seats=435)
        assert dict(US_2020_APPORTIONMENT_POPULATIONS) == snapshot

    def test_determinism_same_input_same_output(self):
        """Repeated calls produce byte-identical results."""
        a = apportion_us_2020(total_seats=600)
        b = apportion_us_2020(total_seats=600)
        c = apportion_us_2020(total_seats=600)
        assert a == b == c


# ----------------------------------------------------------------------
# Method of Equal Proportions properties
# ----------------------------------------------------------------------


class TestMethodOfEqualProportionsProperties:
    """
    Properties that justify the choice of Method of Equal Proportions
    over alternatives (Hamilton, Jefferson, Adams, Webster).
    """

    def test_no_alabama_paradox(self):
        """
        Adding a seat to the total never causes any state to lose a seat.

        This is the property the Hamilton method famously violates and
        Method of Equal Proportions was chosen to avoid. A strong
        algorithm-correctness signal.
        """
        prev = apportion_us_2020(total_seats=435)
        for cap in range(436, 460):
            curr = apportion_us_2020(total_seats=cap)
            for fips in prev:
                assert curr[fips] >= prev[fips], (
                    f"Alabama paradox: state {fips} dropped from "
                    f"{prev[fips]} to {curr[fips]} when cap went from "
                    f"{cap - 1} to {cap}"
                )
            prev = curr

    def test_increment_assigns_exactly_one_more_seat(self):
        """Going from cap=N to cap=N+1 adds exactly one seat to one state."""
        for cap in [435, 500, 700, 1000, 5000]:
            a = apportion_us_2020(total_seats=cap)
            b = apportion_us_2020(total_seats=cap + 1)
            diffs = {fips: b[fips] - a[fips] for fips in a}
            gains = [fips for fips, d in diffs.items() if d == 1]
            unchanged = [fips for fips, d in diffs.items() if d == 0]
            assert len(gains) == 1, f"Expected 1 gainer at cap={cap}, got {gains}"
            assert len(unchanged) == len(a) - 1
            # No state ever loses
            assert all(d >= 0 for d in diffs.values())

    def test_more_populous_state_gets_at_least_as_many_seats(self):
        """
        A larger-population state always has at least as many seats as a
        smaller one, at any cap. (Method of Equal Proportions guarantees
        this; some other methods can violate it under edge conditions.)
        """
        states_by_pop = sorted(
            US_2020_APPORTIONMENT_POPULATIONS.items(),
            key=lambda kv: kv[1],
        )
        for cap in [435, 575, 1000, 11037]:
            seats = apportion_us_2020(total_seats=cap)
            prev_seats = -1
            for fips, _pop in states_by_pop:
                assert seats[fips] >= prev_seats, (
                    f"At cap={cap}, less-populous state {fips} has more "
                    f"seats ({seats[fips]}) than a more-populous predecessor"
                )
                prev_seats = seats[fips]


# ----------------------------------------------------------------------
# Edge cases
# ----------------------------------------------------------------------


class TestEdgeCases:
    def test_total_equal_to_n_states_gives_each_one_seat(self):
        result = apportion_us_2020(total_seats=50)
        assert all(v == 1 for v in result.values())
        assert sum(result.values()) == 50

    def test_total_below_n_states_raises(self):
        with pytest.raises(InvalidApportionmentError):
            apportion_us_2020(total_seats=49)

    def test_zero_min_floor_with_total_below_n_states(self):
        """With min_per_state=0 you can request fewer seats than states."""
        result = apportion(
            US_2020_APPORTIONMENT_POPULATIONS,
            total_seats=10,
            min_per_state=0,
        )
        assert sum(result.values()) == 10
        # Tiny states should get zero; the very largest should get most
        assert result["56"] == 0  # Wyoming
        assert result["06"] > result["48"]  # CA > TX

    def test_empty_input_with_zero_total(self):
        assert apportion({}, total_seats=0) == {}

    def test_empty_input_with_positive_total_raises(self):
        with pytest.raises(InvalidApportionmentError):
            apportion({}, total_seats=10)

    def test_negative_population_raises(self):
        with pytest.raises(InvalidApportionmentError):
            apportion({"01": -1, "02": 1000}, total_seats=10)

    def test_zero_population_raises(self):
        with pytest.raises(InvalidApportionmentError):
            apportion({"01": 0, "02": 1000}, total_seats=10)

    def test_negative_min_per_state_raises(self):
        with pytest.raises(InvalidApportionmentError):
            apportion(
                {"01": 1000},
                total_seats=10,
                min_per_state=-1,
            )

    def test_minimal_two_state_case(self):
        """Tiny synthetic case where the answer is hand-checkable."""
        # State A: 90,000 people. State B: 10,000.
        # 2 seats, min 1 each -> {A:1, B:1}
        # 3 seats: priorities at floor are 90000/sqrt(2)=63640 and
        # 10000/sqrt(2)=7071, so A gets seat 3 -> {A:2, B:1}
        # 4 seats: now A's priority is 90000/sqrt(6)=36742, B's still 7071,
        # so A gets seat 4 -> {A:3, B:1}
        pops = {"A": 90_000, "B": 10_000}
        assert apportion(pops, total_seats=2) == {"A": 1, "B": 1}
        assert apportion(pops, total_seats=3) == {"A": 2, "B": 1}
        assert apportion(pops, total_seats=4) == {"A": 3, "B": 1}


# ----------------------------------------------------------------------
# priority_value helper
# ----------------------------------------------------------------------


class TestPriorityValue:
    def test_priority_at_zero_seats_is_infinity(self):
        """
        With min_per_state=0 a state with no seats has infinite priority
        for receiving its first seat. This guarantees the floor is
        respected even without a special case in the loop.
        """
        assert priority_value(1_000_000, 0) == float("inf")

    def test_priority_formula(self):
        """Spot-check the formula value."""
        # 1,000,000 / sqrt(1*2) = 707106.78...
        p = priority_value(1_000_000, 1)
        assert math.isclose(p, 1_000_000 / math.sqrt(2))

    def test_priority_decreases_with_more_seats(self):
        """A state's marginal priority drops as it accumulates seats."""
        pop = 5_000_000
        p1 = priority_value(pop, 1)
        p5 = priority_value(pop, 5)
        p20 = priority_value(pop, 20)
        assert p1 > p5 > p20

    def test_priority_negative_seats_raises(self):
        with pytest.raises(InvalidApportionmentError):
            priority_value(1_000_000, -1)

    def test_priority_non_positive_population_raises(self):
        with pytest.raises(InvalidApportionmentError):
            priority_value(0, 1)
        with pytest.raises(InvalidApportionmentError):
            priority_value(-1, 1)
